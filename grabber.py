import os
import json
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.eprocure.gov.bd"
LIST_URL = f"{BASE_URL}/resources/common/StdTenderSearch.jsp?h=t"

DATA_FILE = Path(__file__).parent / "processed_tenders.json"
MAX_SEEN_IDS = 5000 

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def load_processed_tenders():
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except:
            return []
    return []

def save_processed_tenders(tenders_list):
    tenders_list = tenders_list[-MAX_SEEN_IDS:]
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(tenders_list, f, ensure_ascii=False, indent=2)

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: 
        print("⚠️ Telegram Token/Chat ID missing!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=30)
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

def parse_detail_page(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    details = {
        "org": "N/A",
        "publish_date": "N/A",
        "closing_date": "N/A",
        "price": "N/A",
        "security": "N/A"
    }
    
    org_td = soup.find(string=lambda text: text and "Organization :" in text)
    if org_td:
        try: details["org"] = org_td.find_next('td').text.strip()
        except: pass
        
    pub_td = soup.find(string=lambda text: text and "Publication" in text and "Date and Time" in text)
    if pub_td:
        try: details["publish_date"] = pub_td.find_next('td').text.strip()
        except: pass
        
    close_td = soup.find(string=lambda text: text and "Closing" in text and "Date and Time" in text)
    if close_td:
        try: details["closing_date"] = close_td.find_next('td').text.strip()
        except: pass
        
    price_td = soup.find(string=lambda text: text and "Document Price" in text)
    if price_td:
        try: details["price"] = price_td.find_next('td').text.strip()
        except: pass
        
    security_th = soup.find(string=lambda text: text and "security" in text and "Amount" in text)
    if security_th:
        try:
            row = security_th.find_parent('table').find_all('tr')[1]
            details["security"] = row.find_all('td')[3].text.strip()
        except: pass
            
    return details

def main():
    processed_list = load_processed_tenders()
    seen_ids = set(processed_list)

    with sync_playwright() as p:
        # রিয়েল ব্রাউজারের মতো ছদ্মবেশ ধারণ করার জন্য আর্গুমেন্ট
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        
        # জেনুইন ইউজার ওভাররাইড মেকানিজম
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="Asia/Dhaka"
        )
        
        # ওয়েবড্রাইভার ডিটেকশন পুরোপুরি বন্ধ করা
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print("📡 মেইন লিস্ট পেজ লোড করা হচ্ছে...")
        try:
            # পেজটি ওপেন করে নেটওয়ার্ক সম্পূর্ণ শান্ত হওয়া পর্যন্ত অপেক্ষা করবে
            page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
            
            # ই-জিপি সার্ভার স্লো হলেও যেন ডাটা মিস না হয়, তাই টেবিল রেন্ডার হতে সর্বোচ্চ ৩০ সেকেন্ড পর্যন্ত অপেক্ষা করবে
            print("⏳ টেবিল ও ডাটা রেন্ডার হওয়ার জন্য অপেক্ষা করছি...")
            page.wait_for_selector("table#resultTable tr[id]", timeout=30000)
            
            # ডাটা প্রসেস করার আগে সেফটির জন্য আরও অতিরিক্ত ৩ সেকেন্ড বিরতি
            time.sleep(3)
        except Exception as e:
            print(f"❌ ই-জিপির মেইন টেবিলের ডাটা লোড করা সম্ভব হয়নি: {e}")
            browser.close()
            return

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", id="resultTable")
        
        # শুধুমাত্র যেসব tr-এর নির্দিষ্ট আইডি আছে (আসল টেন্ডার রো) সেগুলো ফিল্টার করা
        trs = table.find_all("tr", id=True) if table else []

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

        for item in tenders_to_process:
            t_id = item["tender_id"]
            print(f"🔗 ডিটেইলস পেজে ঢুকছি: Tender ID {t_id}")
            
            try:
                # মেইন পেজে ওই নির্দিষ্ট Row এর লিংকে ক্লিক করা
                link_locator = page.locator(f"table#resultTable tr[id] >> text={t_id}").locator("xpath=../..").locator("td:nth-child(3) a")
                
                if link_locator.count() > 0:
                    with context.expect_page() as new_page_info:
                        link_locator.first.click()
                    
                    detail_page = new_page_info.value
                    detail_page.wait_for_load_state("networkidle")
                    time.sleep(3) 
                    
                    detail_html = detail_page.content()
                    extra_info = parse_detail_page(detail_html)
                    detail_page.close()
                else:
                    print(f"⚠️ টেন্ডার {t_id} এর লিংক মেইন পেজে লোকেট করা যায়নি।")
                    extra_info = {"org": "N/A", "publish_date": "N/A", "closing_date": "N/A", "price": "N/A", "security": "N/A"}
            
            except Exception as e:
                print(f"❌ স্ক্র্যাপ করতে সমস্যা হয়েছে ({t_id}): {e}")
                extra_info = {"org": "N/A", "publish_date": "N/A", "closing_date": "N/A", "price": "N/A", "security": "N/A"}

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
            processed_list.append(t_id)
            time.sleep(2) 

        browser.close()

    save_processed_tenders(processed_list)
    print("✅ সফলভাবে রান শেষ হয়েছে এবং processed_tenders.json আপডেট করা হয়েছে।")

if __name__ == "__main__":
    main()
