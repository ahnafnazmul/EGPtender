"""
eGP (eprocure.gov.bd) Tender Notification Bot
------------------------------------------------
- StdTenderSearch.jsp?h=t পেজ থেকে টেন্ডার লিস্ট স্ক্র্যাপ করে (Playwright দিয়ে,
  কারণ টেবিলটা AJAX/JS দিয়ে রেন্ডার হয়, প্লেইন HTTP request কাজ করবে না)
- state.json এ আগে পাঠানো Tender ID গুলো রাখা হয়, নতুন পাওয়া গেলে সেগুলোই পাঠানো হবে
- প্রতিটা নতুন টেন্ডারের ডিটেইলস পেজে গিয়ে PDF ডাউনলোড লিংক খুঁজে PDF ডাউনলোড করা হয়
- সবশেষে Telegram এ মেসেজ + PDF (থাকলে) পাঠানো হয়
- v3: লিস্ট পেজে ০ রো পেলে ৩ বার পর্যন্ত রিট্রাই করবে (সাইটের সাময়িক গ্লিচ সামলাতে)
"""

import os
import re
import json
import sys
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.eprocure.gov.bd"
LIST_URL = f"{BASE_URL}/resources/common/StdTenderSearch.jsp?h=t"
VIEW_TENDER_URL = f"{BASE_URL}/resources/common/ViewTender.jsp"

STATE_FILE = Path(__file__).parent / "state.json"
MAX_SEEN_IDS = 5000  # state ফাইল যেন অসীম বড় না হয়ে যায়

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DEBUG_MODE = os.environ.get("DEBUG_MODE", "false").lower() == "true"

DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"seen_ids": []}
    return {"seen_ids": []}


def save_state(state):
    state["seen_ids"] = state["seen_ids"][-MAX_SEEN_IDS:]
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def extract_tender_rows(page):
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="resultTable")
    rows_data = []

    if table is None:
        print("⚠️ #resultTable পাওয়া যায়নি, সাইটের গঠন বদলে গেছে হয়তো।")
        return rows_data

    trs = table.find_all("tr")
    for tr in trs:
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue

        sl_no = tds[0].get_text(strip=True)

        id_cell_lines = [x.strip() for x in tds[1].get_text(separator="|").split("|") if x.strip()]
        tender_id = id_cell_lines[0] if id_cell_lines else None
        ref_no = id_cell_lines[1] if len(id_cell_lines) > 1 else "N/A"
        status = id_cell_lines[-1] if len(id_cell_lines) > 2 else "N/A"

        title_cell_lines = [x.strip() for x in tds[2].get_text(separator="|").split("|") if x.strip()]
        nature = title_cell_lines[0] if title_cell_lines else "N/A"
        title_text = title_cell_lines[-1] if len(title_cell_lines) > 1 else "N/A"

        org_cell_lines = [x.strip() for x in tds[3].get_text(separator="|").split("|") if x.strip()]
        organization = " > ".join(org_cell_lines) if org_cell_lines else "N/A"

        date_cell_lines = [x.strip() for x in tds[5].get_text(separator="|").split("|") if x.strip()]
        pub_date = date_cell_lines[0] if date_cell_lines else "N/A"
        close_date = date_cell_lines[1] if len(date_cell_lines) > 1 else "N/A"

        if not tender_id or not tender_id.isdigit():
            continue

        rows_data.append(
            {
                "sl_no": sl_no,
                "tender_id": tender_id,
                "ref_no": ref_no,
                "status": status,
                "nature": nature,
                "title": title_text,
                "organization": organization,
                "pub_date": pub_date,
                "close_date": close_date,
            }
        )

    return rows_data


PDF_KEYWORDS = ("pdf", "report", "print", "save", "download", "export")


def fetch_detail_html(context, tender_id):
    resp = context.request.post(
        VIEW_TENDER_URL,
        form={"id": tender_id, "h": "t"},
        timeout=60000,
    )
    if not resp.ok:
        print(f"⚠️ ViewTender.jsp POST ব্যর্থ ({tender_id}): status {resp.status}")
        return None
    return resp.text()


def find_pdf_url(detail_html):
    soup = BeautifulSoup(detail_html, "html.parser")
    candidates = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True).lower()
        if href in ("", "#", "javascript:void(0)", "javascript:void(0);"):
            continue
        if any(k in href.lower() for k in PDF_KEYWORDS) or any(k in text for k in PDF_KEYWORDS):
            candidates.append(href if href.startswith("http") else BASE_URL + href)

    for form in soup.find_all("form", action=True):
        action = form["action"].strip()
        if any(k in action.lower() for k in PDF_KEYWORDS):
            full = action if action.startswith("http") else BASE_URL + action
            if full not in candidates:
                candidates.append(full)

    return candidates


def download_pdf(context, detail_html, tender_id):
    candidates = find_pdf_url(detail_html)
    for url in candidates:
        try:
            resp = context.request.get(url, timeout=60000)
            content_type = resp.headers.get("content-type", "")
            if resp.ok and ("application/pdf" in content_type or url.lower().endswith(".pdf")):
                out_path = DOWNLOAD_DIR / f"{tender_id}.pdf"
                out_path.write_bytes(resp.body())
                return out_path
        except Exception as e:
            print(f"⚠️ PDF candidate ব্যর্থ ({tender_id}, {url}): {e}")
    if candidates:
        print(f"⚠️ {tender_id}: {len(candidates)} টা candidate পাওয়া গেছে কিন্তু কোনোটাই PDF রেসপন্স দেয়নি: {candidates}")
    else:
        print(f"⚠️ {tender_id}: ডিটেইলস পেজে কোনো PDF/Save/Print লিংক পাওয়া যায়নি।")
    return None


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


def build_message(sl_no, tender_id, title, org, pub_date, close_date, has_pdf):
    pdf_line = "নিচে সংযুক্ত ⬇️" if has_pdf else "পাওয়া যায়নি (নিচের লিংকে গিয়ে দেখো)"
    return (
        f"🆕 <b>নতুন টেন্ডার বিজ্ঞপ্তি</b>\n\n"
        f"<b>SL No:</b> {sl_no}\n"
        f"<b>Tender ID:</b> {tender_id}\n"
        f"<b>Title:</b> {title}\n"
        f"<b>Organization:</b> {org}\n"
        f"<b>Publishing Date:</b> {pub_date}\n"
        f"<b>Closing Date:</b> {close_date}\n"
        f"<b>PDF:</b> {pdf_line}\n\n"
        f"🔗 <a href='{LIST_URL}'>লিস্ট পেজে দেখো</a>"
    )


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

        MAX_ATTEMPTS = 3
        rows = []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            print(f"📡 লিস্ট পেজ লোড হচ্ছে (attempt {attempt}/{MAX_ATTEMPTS}): {LIST_URL}")
            page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
            time.sleep(3)

            rows = extract_tender_rows(page)
            print(f"📋 attempt {attempt}: মোট {len(rows)} টা রো পাওয়া গেছে।")

            if DEBUG_MODE:
                page.screenshot(path=f"debug_screenshot_attempt{attempt}.png", full_page=True)
                Path(f"debug_page_attempt{attempt}.html").write_text(page.content(), encoding="utf-8")

            if rows:
                break

            if attempt < MAX_ATTEMPTS:
                print("⚠️ ০ রো পাওয়া গেছে, কিছুক্ষণ পর আবার চেষ্টা করা হচ্ছে...")
                time.sleep(10)

        print(f"📋 চূড়ান্ত ফলাফল: মোট {len(rows)} টা রো পাওয়া গেছে (লিস্ট পেজ থেকে)।")

        new_rows = [r for r in rows if r["tender_id"] not in seen_ids]
        print(f"🆕 নতুন টেন্ডার: {len(new_rows)} টা।")

        for n, row in enumerate(new_rows, start=1):
            tender_id = row["tender_id"]
            pdf_path = None

            try:
                detail_html = fetch_detail_html(context, tender_id)
                if DEBUG_MODE and n == 1 and detail_html:
                    Path("debug_detail_page.html").write_text(detail_html, encoding="utf-8")
                    print("🐞 DEBUG_MODE: debug_detail_page.html সেভ হয়েছে।")
                if detail_html:
                    pdf_path = download_pdf(context, detail_html, tender_id)
            except Exception as e:
                print(f"⚠️ ডিটেইলস/PDF প্রসেস করতে সমস্যা ({tender_id}): {e}")

            msg = build_message(
                sl_no=row["sl_no"],
                tender_id=tender_id,
                title=row["title"],
                org=row["organization"],
                pub_date=row["pub_date"],
                close_date=row["close_date"],
                has_pdf=bool(pdf_path),
            )

            send_telegram_message(msg)
            if pdf_path:
                send_telegram_document(pdf_path, caption=f"Tender ID: {tender_id}")

            seen_ids.add(tender_id)
            time.sleep(1)

        browser.close()

    state["seen_ids"] = list(seen_ids)
    save_state(state)
    print("✅ শেষ। state.json আপডেট করা হয়েছে।")


if __name__ == "__main__":
    main()
