"""
eGP (eprocure.gov.bd) Tender Notification Bot
------------------------------------------------
- StdTenderSearch.jsp?h=t পেজ থেকে টেন্ডার লিস্ট স্ক্র্যাপ করে (Playwright দিয়ে)
- state.json এ আগে পাঠানো Tender ID গুলো রাখা হয়, নতুন পাওয়া গেলে সেগুলোই পাঠানো হবে
- প্রতিটা নতুন টেন্ডারের ডিটেইলস পেজে (ViewTender.jsp) গিয়ে Document Price ও
  Security Amount বের করা হয়
- সবশেষে Telegram এ সম্পূর্ণ বাংলা ফরম্যাটে মেসেজ পাঠানো হয়
- v4: PDF অংশ বাদ দেওয়া হয়েছে, মেসেজ বাংলায়, wait-strategy শক্ত করা হয়েছে
"""

import os
import json
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

BASE_URL = "https://www.eprocure.gov.bd"
LIST_URL = f"{BASE_URL}/resources/common/StdTenderSearch.jsp?h=t"
VIEW_TENDER_URL = f"{BASE_URL}/resources/common/ViewTender.jsp"

STATE_FILE = Path(__file__).parent / "state.json"
MAX_SEEN_IDS = 5000

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DEBUG_MODE = os.environ.get("DEBUG_MODE", "false").lower() == "true"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# লিস্ট পেজ থেকে রো এক্সট্র্যাকশন
# ---------------------------------------------------------------------------
def extract_tender_rows(page):
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="resultTable")
    rows_data = []

    if table is None:
        print("⚠️ #resultTable পাওয়া যায়নি।")
        return rows_data

    trs = table.find_all("tr")
    for tr in trs:
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue

        sl_no = tds[0].get_text(strip=True)

        id_cell_lines = [x.strip() for x in tds[1].get_text(separator="|").split("|") if x.strip()]
        tender_id = id_cell_lines[0] if id_cell_lines else None

        title_cell_lines = [x.strip() for x in tds[2].get_text(separator="|").split("|") if x.strip()]
        title_text = title_cell_lines[-1] if len(title_cell_lines) > 1 else (title_cell_lines[0] if title_cell_lines else "N/A")

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
                "title": title_text,
                "organization": organization,
                "pub_date": pub_date,
                "close_date": close_date,
            }
        )

    return rows_data


# ---------------------------------------------------------------------------
# ডিটেইলস পেজ (ViewTender.jsp) থেকে Document Price ও Security Amount বের করা
# ---------------------------------------------------------------------------
def fetch_detail_html(context, tender_id):
    try:
        resp = context.request.post(
            VIEW_TENDER_URL,
            form={"id": tender_id, "h": "t"},
            timeout=60000,
        )
        if not resp.ok:
            print(f"⚠️ ViewTender.jsp POST ব্যর্থ ({tender_id}): status {resp.status}")
            return None
        return resp.text()
    except Exception as e:
        print(f"⚠️ ViewTender.jsp POST এক্সেপশন ({tender_id}): {e}")
        return None


def extract_price_fields(detail_html):
    """Document Price এবং Security Amount বের করে। দুটোই না পেলে 'N/A'।"""
    result = {"doc_price": "N/A", "security": "N/A"}
    if not detail_html:
        return result

    soup = BeautifulSoup(detail_html, "html.parser")

    # ১. Document Price: label:value টাইপ ফিল্ড (td পেয়ারে থাকে সাধারণত)
    for td in soup.find_all("td"):
        label = td.get_text(strip=True)
        if "Document Price" in label:
            sib = td.find_next_sibling("td")
            if sib:
                val = sib.get_text(strip=True)
                if val:
                    result["doc_price"] = val
            break

    # ২. Security Amount: সাধারণত "Lot" টেবিলের একটা কলামে থাকে
    lot_table = None
    for table in soup.find_all("table"):
        header_text = table.get_text()
        if "security" in header_text.lower() and ("Lot" in header_text or "Identification" in header_text):
            lot_table = table
            break

    if lot_table:
        trs = lot_table.find_all("tr")
        if trs:
            header_cells = [c.get_text(strip=True) for c in trs[0].find_all(["th", "td"])]
            sec_idx = None
            for i, h in enumerate(header_cells):
                if "security" in h.lower():
                    sec_idx = i
                    break
            if sec_idx is not None:
                values = []
                for tr in trs[1:]:
                    tds = tr.find_all("td")
                    if len(tds) > sec_idx:
                        v = tds[sec_idx].get_text(strip=True)
                        if v:
                            values.append(v)
                if values:
                    result["security"] = ", ".join(values)

    return result


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


def build_message(sl_no, tender_id, title, org, pub_date, close_date, doc_price, security):
    return (
        f"🆕 <b>নতুন টেন্ডার বিজ্ঞপ্তি</b>\n\n"
        f"<b>সিরিয়াল নম্বরঃ</b> {sl_no}\n"
        f"<b>টেন্ডার আইডিঃ</b> {tender_id}\n"
        f"<b>টাইটেলঃ</b> {title}\n"
        f"<b>অর্গানাইজেশনঃ</b> {org}\n"
        f"<b>প্রচারের তারিখঃ</b> {pub_date}\n"
        f"<b>শেষ হবার তারিখঃ</b> {close_date}\n"
        f"<b>টেন্ডার শিডিউল দামঃ</b> {doc_price}\n"
        f"<b>টেন্ডার সিকিউরিটিঃ</b> {security}\n\n"
        f"🔗 <a href='{LIST_URL}'>লিস্ট পেজে দেখো</a>"
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
            ),
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        page = context.new_page()

        MAX_ATTEMPTS = 3
        rows = []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            print(f"📡 লিস্ট পেজ লোড হচ্ছে (attempt {attempt}/{MAX_ATTEMPTS}): {LIST_URL}")
            try:
                page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
                # সরাসরি টেবিলের জন্য অপেক্ষা করা, networkidle এর বদলে
                # (কিছু পার্সিস্টেন্ট JS পোলার থাকলে networkidle কখনো নাও আসতে পারে)
                page.wait_for_selector("table#resultTable tr", timeout=30000)
                time.sleep(2)  # শেষ কিছু AJAX আপডেটের জন্য বাড়তি সময়
            except PWTimeoutError:
                print("⚠️ #resultTable এর জন্য টাইমআউট — সাইট ধীরে সাড়া দিচ্ছে বা ব্লক করছে হয়তো।")

            rows = extract_tender_rows(page)
            print(f"📋 attempt {attempt}: মোট {len(rows)} টা রো পাওয়া গেছে।")

            if DEBUG_MODE:
                try:
                    page.screenshot(path=f"debug_screenshot_attempt{attempt}.png", full_page=True)
                    Path(f"debug_page_attempt{attempt}.html").write_text(page.content(), encoding="utf-8")
                except Exception as e:
                    print(f"⚠️ debug ফাইল সেভ করতে সমস্যা: {e}")

            if rows:
                break

            if attempt < MAX_ATTEMPTS:
                print("⚠️ ০ রো পাওয়া গেছে, কিছুক্ষণ পর আবার চেষ্টা করা হচ্ছে...")
                time.sleep(15)

        print(f"📋 চূড়ান্ত ফলাফল: মোট {len(rows)} টা রো পাওয়া গেছে (লিস্ট পেজ থেকে)।")

        new_rows = [r for r in rows if r["tender_id"] not in seen_ids]
        print(f"🆕 নতুন টেন্ডার: {len(new_rows)} টা।")

        for n, row in enumerate(new_rows, start=1):
            tender_id = row["tender_id"]
            doc_price = "N/A"
            security = "N/A"

            detail_html = fetch_detail_html(context, tender_id)
            if DEBUG_MODE and n == 1 and detail_html:
                Path("debug_detail_page.html").write_text(detail_html, encoding="utf-8")
                print("🐞 DEBUG_MODE: debug_detail_page.html সেভ হয়েছে।")

            if detail_html:
                fields = extract_price_fields(detail_html)
                doc_price = fields["doc_price"]
                security = fields["security"]

            msg = build_message(
                sl_no=row["sl_no"],
                tender_id=tender_id,
                title=row["title"],
                org=row["organization"],
                pub_date=row["pub_date"],
                close_date=row["close_date"],
                doc_price=doc_price,
                security=security,
            )

            send_telegram_message(msg)
            seen_ids.add(tender_id)
            time.sleep(1)  # Telegram rate limit এড়াতে

        browser.close()

    state["seen_ids"] = list(seen_ids)
    save_state(state)
    print("✅ শেষ। state.json আপডেট করা হয়েছে।")


if __name__ == "__main__":
    main()
