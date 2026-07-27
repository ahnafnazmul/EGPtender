import os
import json
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup

BASE_URL = "https://www.eprocure.gov.bd"
# সরাসরি ই-জিপির ইন্টারনাল ডাটা সোর্স ইউআরএল ব্যবহার করা হচ্ছে
DATA_URL = f"{BASE_URL}/resources/common/StdTenderSearchGrid.jsp"

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

def parse_detail_page(tender_id):
    """সরাসরি ডিটেইলস পেজে হিট করে ডাটা স্ক্র্যাপ করার ফাংশন"""
    detail_url = f"{BASE_URL}/resources/common/TenderDetails.jsp?id={tender_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": BASE_URL
    }
    
    details = {
        "org": "N/A",
        "publish_date": "N/A",
        "closing_date": "N/A",
        "price": "N/A",
        "security": "N/A"
    }
    
    try:
        response = requests.get(detail_url, headers=headers, timeout=30)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            
            # অর্গানাইজেশন
            org_td = soup.find(string=lambda text: text and "Organization :" in text)
            if org_td:
                try: details["org"] = org_td.find_next('td').text.strip()
                except: pass
                
            # প্রচারের তারিখ
            pub_td = soup.find(string=lambda text: text and "Publication" in text and "Date and Time" in text)
            if pub_td:
                try: details["publish_date"] = pub_td.find_next('td').text.strip()
                except: pass
                
            # শেষ হবার তারিখ
            close_td = soup.find(string=lambda text: text and "Closing" in text and "Date and Time" in text)
            if close_td:
                try: details["closing_date"] = close_td.find_next('td').text.strip()
                except: pass
                
            # টেন্ডার শিডিউল দাম
            price_td = soup.find(string=lambda text: text and "Document Price" in text)
            if price_td:
                try: details["price"] = price_td.find_next('td').text.strip()
                except: pass
                
            # টেন্ডার সিকিউরিটি
            security_th = soup.find(string=lambda text: text and "security" in text and "Amount" in text)
            if security_th:
                try:
                    row = security_th.find_parent('table').find_all('tr')[1]
                    details["security"] = row.find_all('td')[3].text.strip()
                except: pass
    except Exception as e:
        print(f"❌ ডিটেইলস পেজ রিকোয়েস্টে ভুল হয়েছে ({tender_id}): {e}")
        
    return details

def main():
    processed_list = load_processed_tenders()
    seen_ids = set(processed_list)

    # জেনুইন ব্রাউজার রিকোয়েস্ট হেডার্স
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/resources/common/StdTenderSearch.jsp?h=t"
    }

    # ই-জিপির ডাটা গ্রিড লোড করার প্রয়োজনীয় ডাটা প্যারামিটার
    payload = {
        "rows": "50",      # একবারে ৫০টি টেন্ডার টানবে
        "page": "1",
        "sidx": "1",
        "sord": "desc"
    }

    print("📡 ই-জিপি ডাটা সার্ভার থেকে সরাসরি টেন্ডার লিস্ট আনা হচ্ছে...")
    try:
        response = requests.post(DATA_URL, headers=headers, data=payload, timeout=30)
        if response.status_code != 200:
            print(f"❌ ই-জিপি সার্ভার রেসপন্স করেনি। স্ট্যাটাস কোড: {response.status_code}")
            return
            
        soup = BeautifulSoup(response.text, "html.parser")
        trs = soup.find_all("tr")[1:] # হেডার বাদ দিয়ে
    except Exception as e:
        print(f"❌ ডাটা রিকোয়েস্ট পাঠাতে সমস্যা হয়েছে: {e}")
        return

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
        print(f"🔗 ডিটেইলস ডাটা সংগ্রহ করা হচ্ছে: Tender ID {t_id}")
        
        # সরাসরি আইডি দিয়ে ডিটেইলস স্ক্র্যাপ করা হচ্ছে
        extra_info = parse_detail_page(t_id)

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

    save_processed_tenders(processed_list)
    print("✅ সফলভাবে রান শেষ হয়েছে এবং processed_tenders.json আপডেট করা হয়েছে।")

if __name__ == "__main__":
    main()
