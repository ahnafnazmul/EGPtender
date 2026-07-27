import os
import json
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.eprocure.gov.bd"
LIST_URL = f"{BASE_URL}/resources/common/StdTenderSearch.jsp?h=t"

STATE_FILE = Path(__file__).parent / "state.json"
MAX_SEEN_IDS = 5000 

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"seen_ids": []}
    return {"seen_ids": []}

def save_state(state):
    state["seen_ids"] = state["seen_ids"][-MAX_SEEN_IDS:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: 
        print("⚠️ Telegram Token/Chat ID missing!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=30)

def parse_detail_page(html_content):
    """ডিটেইলস পেজের HTML থেকে প্রয়োজনীয় সব তথ্য বের করার ফাংশন"""
    soup = BeautifulSoup(html_content, "html.parser")
    details = {
        "org": "N/A",
        "publish_date": "N/A",
        "closing_date": "N/A",
        "price": "N/A",
        "security": "N/A"
    }
    
    # অর্গানাইজেশন
    org_td = soup.find(string=lambda text: text and "Organization :" in text)
    if org_td:
        try: details["org"] = org_td.find_next('td').text.strip()
        except: pass
        
    # প্রচারের তারিখ (Scheduled Tender/Proposal Publication Date and Time)
    pub_td = soup.find(string=lambda text: text and "Publication" in text and "Date and Time" in text)
    if pub_td:
        try: details["publish_date"] = pub_td.find_next('td').text.strip()
        except: pass
        
    # শেষ হবার তারিখ (Tender/Proposal Closing Date and Time)
    close_td = soup.find(string=lambda text: text and "Closing" in text and "Date and Time" in text)
    if close_td:
        try: details["closing_date"] = close_td.find_next('td').text.strip()
        except: pass
        
    # টেন্ডার শিডিউল দাম (Tender/Proposal Document Price)
    price_td = soup.find(string=lambda text: text and "Document Price" in text)
    if price_td:
        try: details["price"] = price_td.find_next('td').text.strip()
        except: pass
        
    # টেন্ডার সিকিউরিটি (Tender/Proposal security Amount)
    security_th = soup.find(string=lambda text: text and "security" in text and "Amount" in text)
    if security_th:
        try:
            row = security_th.find_parent('table').find_all('tr')[1]
            details["security"] = row.find_all('td')[3].text.strip()
        except:
            pass
            
    return details

def main():
    state = load_state()
    seen_ids = set(state.get("seen_ids", []))

    with sync_playwright() as p:
        # ব্রাউজার লঞ্চ করা
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()

        MAX_ATTEMPTS = 3
        table_found = False
        
        for attempt in range(1, MAX_ATTEMPTS + 1):
            print(f"📡 মেইন লিস্ট পেজ লোড হচ্ছে (Attempt {attempt}/{MAX_ATTEMPTS})")
            page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
            time.sleep(5) # টেবিল রেন্ডার হওয়ার জন্য একটু অতিরিক্ত সময় দেওয়া
            
            if page.locator("table#resultTable").count() > 0:
                table_found = True
                break
            print("⚠️ টেবিল পাওয়া যায়নি, আবার চেষ্টা করা হচ্ছে...")
            time.sleep(5)

        if not table_found:
            print("❌ ই-জিপি মেইন টেবিল লোড করা সম্ভব হয়নি।")
            browser.close()
            return

        # মেইন পেজের HTML থেকে রো-গুলো বের করা
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", id="resultTable")
        trs = table.find_all("tr")[1:] # হেডার বাদ দিয়ে

        # প্রথমে নতুন টেন্ডারগুলো ফিল্টার করে নেওয়া
        tenders_to_process = []
        for tr in trs:
            tds = tr.find_all("td")
            if len(tds) < 6: continue
            
            id_cell_lines = [x.strip() for x in tds[1].get_text(separator="|").split("|") if x.strip()]
            tender_id = id_cell_lines[0] if id_cell_lines else None
            
            if tender_id and tender_id.isdigit() and tender_id not in seen_ids:
                sl_no = tds[0].get_text(strip=True)
                title_cell_lines = [x.strip() for x in tds[2].get_text(separator="|").split("|") if x.strip()]
                title_text = title_cell_lines[-1] if len(title_cell_lines) > 1 else "N/A"
                
                tenders_to_process.append({
                    "sl_no": sl_no,
                    "tender_id": tender_id,
                    "title": title_text
                })

        print(f"🆕 প্রসেস করার মতো নতুন টেন্ডার পাওয়া গেছে: {len(tenders_to_process)} টি।")

        # এবার প্রতিটা নতুন টেন্ডারের লিংকে ক্লিক করে ভেতরে ঢুকবে
        for item in tenders_to_process:
            t_id = item["tender_id"]
            print(f"🔗 ডিটেইলস পেজে ঢুকছি: Tender ID {t_id}")
            
            try:
                # মেইন পেজে ওই নির্দিষ্ট Tender ID এর সারির Title লিকে লোকেটর তৈরি করা
                # Procurement Nature, Title সাধারণত ৩ নম্বর কলাম (index 2), সেখানে থাকা 'a' ট্যাগ
                link_locator = page.locator(f"//table[@id='resultTable']//tr[td[1][text()='{item['sl_no']}'] or td[2][contains(text(),'{t_id}')]]/td[3]/a")
                
                if link_locator.count() > 0:
                    # ক্লিক করলে যেহেতু নিউ ট্যাব ওপেন হয়, তাই নিউ পেজ ইভেন্ট এক্সপেক্ট করা হচ্ছে
                    with context.expect_page() as new_page_info:
                        link_locator.first.click()
                    
                    detail_page = new_page_info.value
                    detail_page.wait_until_穩able = "networkidle"
                    time.sleep(3) # পেজের ডাটা পুরোপুরি লোড হতে সময় দেওয়া
                    
                    # ডিটেইলস পেজের ডাটা স্ক্র্যাপ করা
                    detail_html = detail_page.content()
                    extra_info = parse_detail_page(detail_html)
                    
                    # কাজ শেষ, নতুন ট্যাবটি বন্ধ করে দেওয়া
                    detail_page.close()
                else:
                    print(f"⚠️ টেন্ডার {t_id} এর লিংক ক্লিক করার জন্য খুঁজে পাওয়া যায়নি।")
                    extra_info = {"org": "N/A", "publish_date": "N/A", "closing_date": "N/A", "price": "N/A", "security": "N/A"}
            
            except Exception as e:
                print(f"❌ ডিটেইলস পেজে ঢুকে স্ক্র্যাপ করতে সমস্যা হয়েছে ({t_id}): {e}")
                extra_info = {"org": "N/A", "publish_date": "N/A", "closing_date": "N/A", "price": "N/A", "security": "N/A"}

            # সম্পূর্ণ বাংলা ফরম্যাটে মেসেজ তৈরি
            msg = (
                f"<b>সিরিয়াল নম্বরঃ</b> {item['sl_no']}\n"
                f"<b>টেন্ডার আইডিঃ</b> {t_id}\n"
                f"<b>টাইটেলঃ</b> {item['title']}\n"
                f"<b>অর্গানাইজেশনঃ</b> {extra_info['org']}\n"
                f"<b>প্রচারের তারিখঃ</b> {extra_info['publish_date']}\n"
                f"<b>শেষ হবার তারিখঃ</b> {extra_info['closing_date']}\n"
                f"<b>টেন্ডার শিডিউল দামঃ</b> {extra_info['price']}\n"
                f"<b>টেন্ডার সিকিউরিটিঃ</b> {extra_info['security']}\n"
            )

            send_telegram_message(msg)
            seen_ids.add(t_id)
            time.sleep(2) # টেলিগ্রাম রেট লিমিট এড়াতে বিরতি

        browser.close()

    # স্টেট ফাইল আপডেট
    state["seen_ids"] = list(seen_ids)
    save_state(state)
    print("✅ সফলভাবে রান শেষ হয়েছে এবং state.json আপডেট করা হয়েছে।")

if __name__ == "__main__":
    main()
