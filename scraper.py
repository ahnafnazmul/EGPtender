"""
eGP (eprocure.gov.bd) Tender Notification Bot
------------------------------------------------
- StdTenderSearch.jsp?h=t পেজ থেকে টেন্ডার লিস্ট স্ক্র্যাপ করে (Playwright দিয়ে,
  কারণ টেবিলটা AJAX/JS দিয়ে রেন্ডার হয়, প্লেইন HTTP request কাজ করবে না)
- state.json এ আগে পাঠানো Tender ID গুলো রাখা হয়, নতুন পাওয়া গেলে সেগুলোই পাঠানো হবে
- প্রতিটা নতুন টেন্ডারের ডিটেইলস পেজে গিয়ে Organization/Publishing/Closing Date বের করা হয়
  এবং "Save"/PDF ডাউনলোড লিংক খুঁজে PDF ডাউনলোড করা হয়
- সবশেষে Telegram এ মেসেজ + PDF (থাকলে) পাঠানো হয়

⚠️ গুরুত্বপূর্ণ নোট (README.md এ বিস্তারিত):
এই সাইটের JS-রেন্ডারড টেবিলের আসল CSS selector/HTML গঠন আমি সরাসরি
(browser দিয়ে) দেখতে পারিনি — sandbox থেকে eprocure.gov.bd এ নেটওয়ার্ক এক্সেস নেই।
তাই নিচের selector গুলো header টেক্সট ম্যাচ করে জেনেরিকভাবে লেখা হয়েছে।
প্রথম রান DEBUG_MODE=true দিয়ে চালিয়ে debug_page.html / debug_screenshot.png
আউটপুট আর্টিফ্যাক্ট থেকে ডাউনলোড করে দেখো, selector না মিললে সেই অনুযায়ী
`extract_tender_rows()` ফাংশনের selector গুলো ঠিক করে দিতে হবে।
"""

import os
import re
import json
import sys
import time
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.eprocure.gov.bd"
LIST_URL = f"{BASE_URL}/resources/common/StdTenderSearch.jsp?h=t"

STATE_FILE = Path(__file__).parent / "state.json"
MAX_SEEN_IDS = 5000  # state ফাইল যেন অসীম বড় না হয়ে যায়

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DEBUG_MODE = os.environ.get("DEBUG_MODE", "false").lower() == "true"

DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# State (আগে পাঠানো Tender ID ট্র্যাক করা)
# ---------------------------------------------------------------------------
def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"seen_ids": []}
    return {"seen_ids": []}


def save_state(state):
    # সবচেয়ে পুরনো আইডি ছেঁটে ফেলা, ফাইল ছোট রাখার জন্য
    state["seen_ids"] = state["seen_ids"][-MAX_SEEN_IDS:]
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Playwright দিয়ে লিস্ট পেজ থেকে টেন্ডার রো গুলো বের করা
# ---------------------------------------------------------------------------
def extract_tender_rows(page):
    """
    হোমপেজের টেবিল থেকে প্রতিটা রো বের করে dict এ রাখে:
    {sl_no, tender_id, ref_no, status, nature, title, detail_url}

    NOTE: eprocure.gov.bd এর টেবিল সাধারণত এরকম প্যাটার্নে থাকে (অন্যান্য সরকারি
    e-GP পোর্টালে দেখা যায়) — একটা <table> এ header row, এরপর প্রতি টেন্ডারের
    জন্য ২টা করে <tr> (একটা মূল তথ্য, একটা সাব-ডিটেইল)। Title সাধারণত একটা
    <a> ট্যাগ, যেটাতে ক্লিক করলে TenderDetails.jsp জাতীয় পেজ খোলে অথবা
    onclick এ JS ফাংশন কল হয়ে নতুন পেজ/ট্যাব খোলে।

    এই ফাংশনটা robust রাখতে "header টেক্সট দিয়ে টেবিল খোঁজা" পদ্ধতি ব্যবহার
    করে, কিন্তু লাইভ সাইট না দেখে ১০০% নিশ্চিত selector দেওয়া সম্ভব না।
    DEBUG_MODE=true চালিয়ে debug_page.html দেখে এখানে দরকারমতো টিউন করো।
    """
    rows_data = []

    # হেডার টেক্সট ধরে টেবিল খোঁজা
    header_locator = page.locator("text=Tender/Proposal ID").first
    try:
        header_locator.wait_for(timeout=15000)
    except Exception:
        print("⚠️ হেডার টেক্সট পাওয়া যায়নি, পেজ লোড না হওয়ার সম্ভাবনা আছে।")
        return rows_data

    table = page.locator("table").filter(has_text="Tender/Proposal ID").last
    trs = table.locator("tr")
    count = trs.count()

    for i in range(count):
        tr = trs.nth(i)
        row_text = tr.inner_text()

        # Tender ID সাধারণত সংখ্যার প্যাটার্নে থাকে (যেমন 1234567)
        id_match = re.search(r"\b(\d{5,})\b", row_text)
        if not id_match:
            continue  # হেডার রো বা খালি রো স্কিপ

        tender_id = id_match.group(1)

        # Title লিংক খোঁজা (এই রো বা এর পরের রো-তে থাকতে পারে)
        link = tr.locator("a").first
        detail_url = None
        title_text = None
        try:
            if link.count() > 0:
                href = link.get_attribute("href")
                onclick = link.get_attribute("onclick")
                title_text = link.inner_text().strip()
                if href and href.strip() not in ("", "#", "javascript:void(0)"):
                    detail_url = href if href.startswith("http") else BASE_URL + href
                elif onclick:
                    # onclick='someFn("1234567", ...)' প্যাটার্ন থেকে detail URL
                    # বানানো সাইট-নির্ভর, এখানে placeholder রাখা হলো —
                    # আসল onclick ফাংশন দেখে এটা ঠিক করতে হবে
                    detail_url = None
        except Exception:
            pass

        if not title_text:
            continue

        rows_data.append(
            {
                "tender_id": tender_id,
                "title": title_text,
                "detail_url": detail_url,
                "raw_row_text": row_text,
            }
        )

    return rows_data


def extract_detail_info(page):
    """ডিটেইলস পেজ থেকে Organization / Publishing / Closing Date এবং PDF লিংক বের করা।"""
    info = {"organization": "N/A", "publishing_date": "N/A", "closing_date": "N/A"}

    body_text = page.inner_text("body")

    org_match = re.search(r"(Organization|Organisation)[:\s]+(.+)", body_text)
    if org_match:
        info["organization"] = org_match.group(2).splitlines()[0].strip()

    pub_match = re.search(r"Publishing Date[^\d]*([\d/\-.]+\s*[\d:APMapm ]*)", body_text)
    if pub_match:
        info["publishing_date"] = pub_match.group(1).strip()

    close_match = re.search(r"Closing Date[^\d]*([\d/\-.]+\s*[\d:APMapm ]*)", body_text)
    if close_match:
        info["closing_date"] = close_match.group(1).strip()

    # PDF/Save বাটন/লিংক খোঁজা
    pdf_link_el = page.locator(
        "a:has-text('Save'), a:has-text('PDF'), a:has-text('View'), button:has-text('Save')"
    ).first

    pdf_url = None
    if pdf_link_el.count() > 0:
        href = pdf_link_el.get_attribute("href")
        if href and ".pdf" in href.lower():
            pdf_url = href if href.startswith("http") else BASE_URL + href

    info["pdf_url"] = pdf_url
    return info


def download_pdf(page, pdf_url, tender_id):
    """PDF ডাউনলোড করে লোকাল ফাইলে সেভ করে, path রিটার্ন করে (ব্যর্থ হলে None)।"""
    if not pdf_url:
        return None
    try:
        # সরাসরি লিংক হলে request দিয়ে ডাউনলোড করার চেষ্টা
        resp = page.context.request.get(pdf_url)
        if resp.ok:
            out_path = DOWNLOAD_DIR / f"{tender_id}.pdf"
            out_path.write_bytes(resp.body())
            return out_path
    except Exception as e:
        print(f"⚠️ PDF ডাউনলোড ব্যর্থ ({tender_id}): {e}")
    return None


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID সেট করা নেই।")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"⚠️ Telegram মেসেজ পাঠাতে সমস্যা: {resp.status_code} {resp.text}")


def send_telegram_document(file_path, caption=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    with open(file_path, "rb") as f:
        resp = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption or ""},
            files={"document": f},
            timeout=120,
        )
    if not resp.ok:
        print(f"⚠️ Telegram ফাইল পাঠাতে সমস্যা: {resp.status_code} {resp.text}")


def build_message(sl_no, tender_id, title, org, pub_date, close_date, detail_url, has_pdf):
    return (
        f"🆕 <b>নতুন টেন্ডার বিজ্ঞপ্তি</b>\n\n"
        f"<b>SL No:</b> {sl_no}\n"
        f"<b>Tender ID:</b> {tender_id}\n"
        f"<b>Title:</b> {title}\n"
        f"<b>Organization:</b> {org}\n"
        f"<b>Publishing Date:</b> {pub_date}\n"
        f"<b>Closing Date:</b> {close_date}\n"
        f"<b>PDF:</b> {'নিচে সংযুক্ত ⬇️' if has_pdf else 'পাওয়া যায়নি, নিজে দেখুন 👉 ' + (detail_url or LIST_URL)}\n\n"
        f"🔗 <a href='{detail_url or LIST_URL}'>বিস্তারিত দেখুন</a>"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    state = load_state()
    seen_ids = set(state.get("seen_ids", []))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        )
        page = context.new_page()

        print(f"📡 লিস্ট পেজ লোড হচ্ছে: {LIST_URL}")
        page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
        time.sleep(2)  # কিছু AJAX কলের জন্য বাড়তি সময়

        if DEBUG_MODE:
            page.screenshot(path="debug_screenshot.png", full_page=True)
            Path("debug_page.html").write_text(page.content(), encoding="utf-8")
            print("🐞 DEBUG_MODE: debug_screenshot.png ও debug_page.html সেভ হয়েছে।")

        rows = extract_tender_rows(page)
        print(f"📋 মোট {len(rows)} টা রো পাওয়া গেছে (লিস্ট পেজ থেকে)।")

        new_rows = [r for r in rows if r["tender_id"] not in seen_ids]
        print(f"🆕 নতুন টেন্ডার: {len(new_rows)} টা।")

        for idx, row in enumerate(new_rows, start=1):
            tender_id = row["tender_id"]
            title = row["title"]
            detail_url = row["detail_url"]

            org = pub_date = close_date = "N/A"
            pdf_path = None

            if detail_url:
                try:
                    detail_page = context.new_page()
                    detail_page.goto(detail_url, wait_until="networkidle", timeout=60000)
                    info = extract_detail_info(detail_page)
                    org = info["organization"]
                    pub_date = info["publishing_date"]
                    close_date = info["closing_date"]
                    if info.get("pdf_url"):
                        pdf_path = download_pdf(detail_page, info["pdf_url"], tender_id)
                    detail_page.close()
                except Exception as e:
                    print(f"⚠️ ডিটেইলস পেজ প্রসেস করতে সমস্যা ({tender_id}): {e}")
            else:
                print(f"⚠️ {tender_id} এর জন্য detail_url পাওয়া যায়নি, শুধু লিস্ট থেকে ডাটা পাঠানো হবে।")

            msg = build_message(
                sl_no=idx,
                tender_id=tender_id,
                title=title,
                org=org,
                pub_date=pub_date,
                close_date=close_date,
                detail_url=detail_url,
                has_pdf=bool(pdf_path),
            )

            send_telegram_message(msg)
            if pdf_path:
                send_telegram_document(pdf_path, caption=f"Tender ID: {tender_id}")

            seen_ids.add(tender_id)
            time.sleep(1)  # Telegram rate limit এড়াতে

        browser.close()

    state["seen_ids"] = list(seen_ids)
    save_state(state)
    print("✅ শেষ। state.json আপডেট করা হয়েছে।")


if __name__ == "__main__":
    main()
