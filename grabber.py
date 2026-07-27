import os
import json
import requests
from bs4 import BeautifulSoup

# কনফিগারেশন ও এনভায়রনমেন্ট ভ্যারিয়েবল
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DATA_FILE = "processed_tenders.json"

BASE_URL = "https://www.eprocure.gov.bd"
SEARCH_URL = f"{BASE_URL}/resources/common/StdTenderSearch.jsp?h=t"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def load_processed_tenders():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_processed_tenders(tenders):
    with open(DATA_FILE, "w") as f:
        json.dump(tenders, f, indent=4)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending to Telegram: {e}")

def scrape_detail_page(detail_url):
    response = requests.get(detail_url, headers=headers, timeout=15)
    if response.status_code != 200:
        return None
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    details = {
        "org": "N/A",
        "publish_date": "N/A",
        "closing_date": "N/A",
        "price": "N/A",
        "security": "N/A"
    }
    
    # অর্গানাইজেশন খোঁজা
    org_td = soup.find(string="Organization :")
    if org_td:
        details["org"] = org_td.find_next('td').text.strip()
        
    # পাবলিশিং ডেট খোঁজা
    pub_td = soup.find(string="Scheduled Tender/Proposal Publication\nDate and Time :")
    if pub_td:
        details["publish_date"] = pub_td.find_next('td').text.strip()
        
    # ক্লোজিং ডেট খোঁজা
    close_td = soup.find(string="Tender/Proposal Closing\nDate and Time :")
    if close_td:
        details["closing_date"] = close_td.find_next('td').text.strip()
        
    # শিডিউল প্রাইস খোঁজা
    price_td = soup.find(string="Tender/Proposal Document Price (In BDT) :")
    if price_td:
        details["price"] = price_td.find_next('td').text.strip()
        
    # সিকিউরিটি অ্যামাউন্ট খোঁজা (টেবিল থেকে প্রথম লটের সিকিউরিটি)
    security_th = soup.find(string="Tender/Proposal security \n(Amount in BDT)")
    if security_th:
        # টেবিল রো থেকে ভ্যালু নেওয়া
        try:
            row = security_th.find_parent('table').find_all('tr')[1]
            details["security"] = row.find_all('td')[3].text.strip()
        except:
            pass
            
    return details

def main():
    session = requests.Session()
    response = session.get(SEARCH_URL, headers=headers, timeout=15)
    if response.status_code != 200:
        print("Failed to load home page")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table', {'class': 'list_table'}) # ই-জিপির মেইন টেবিল ক্লাস
    if not table:
        print("Tender table not found")
        return

    processed_list = load_processed_tenders()
    new_processed_list = processed_list.copy()
    
    rows = table.find_all('tr')[1:] # হেডার বাদ দিয়ে বাকি রো
    
    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 4:
            continue
            
        sl_no = cols[0].text.strip()
        
        # টেন্ডার আইডি বের করা
        tender_id_text = cols[1].text.strip()
        tender_id = tender_id_text.split('\n')[0].strip() # প্রথম লাইন সাধারণত আইডি হয়
        
        # যদি অলরেডি প্রসেসড হয়ে থাকে, তবে স্কিপ করবে
        if tender_id in processed_list:
            continue
            
        # টাইটেল ও লিংক অপশন (Procurement Nature, Title কলাম থেকে)
        title_td = cols[2]
        title_a = title_td.find('a')
        if not title_a:
            continue
            
        title = title_a.text.strip()
        detail_link = BASE_URL + title_a['href']
        
        print(f"Scraping new tender: {tender_id}")
        
        # ডিটেইলস পেজ স্ক্র্যাপ করা
        detail_info = scrape_detail_page(detail_link)
        if not detail_info:
            continue
            
        # মেসেজ ফরম্যাট (বাংলায়)
        message = (
            f"<b>সিরিয়াল নম্বরঃ</b> {sl_no}\n"
            f"<b>টেন্ডার আইডিঃ</b> {tender_id}\n"
            f"<b>টাইটেলঃ</b> {title}\n"
            f"<b>অর্গানাইজেশনঃ</b> {detail_info['org']}\n"
            f"<b>প্রচারের তারিখঃ</b> {detail_info['publish_date']}\n"
            f"<b>শেষ হবার তারিখ：</b> {detail_info['closing_date']}\n"
            f"<b>টেন্ডার শিডিউল দামঃ</b> {detail_info['price']}\n"
            f"<b>টেন্ডার সিকিউরিটিঃ</b> {detail_info['security']}\n"
        )
        
        send_telegram_message(message)
        new_processed_list.append(tender_id)
        
    # সর্বোচ্চ ১০০টি আইডি ট্র্যাকিং ফাইলে রাখা (ফাইল সাইজ নিয়ন্ত্রণে রাখতে)
    save_processed_tenders(new_processed_list[-100:])

if __name__ == "__main__":
    main()
