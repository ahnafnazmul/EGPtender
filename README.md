# eGP Tender Bot (eprocure.gov.bd → Telegram)

## যেভাবে সেটআপ করবে

1. এই ফোল্ডারের সবকিছু একটা নতুন প্রাইভেট GitHub repo তে পুশ করো।
2. Telegram এ [@BotFather](https://t.me/BotFather) দিয়ে একটা বট বানাও, `TELEGRAM_BOT_TOKEN` পাবে।
3. তোমার চ্যাট/গ্রুপের `chat_id` বের করো (বটকে চ্যাটে/গ্রুপে অ্যাড করে
   `https://api.telegram.org/bot<TOKEN>/getUpdates` খুলে দেখো)।
4. Repo → Settings → Secrets and variables → Actions এ গিয়ে যোগ করো:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
5. Actions ট্যাব থেকে "eGP Tender Scanner" workflow ম্যানুয়ালি একবার
   ("Run workflow" বাটন দিয়ে) চালাও — cron শিডিউলের জন্য অপেক্ষা করা লাগবে না।

## ⚠️ খুব গুরুত্বপূর্ণ — প্রথমে অবশ্যই পড়ো

আমি (Claude) এই sandbox থেকে সরাসরি `eprocure.gov.bd` তে ব্রাউজার দিয়ে ঢুকে
আসল টেবিলের HTML গঠন দেখতে পারিনি — এই sandbox-এর নেটওয়ার্ক শুধু কিছু
নির্দিষ্ট প্যাকেজ রেজিস্ট্রি (pypi, npm, github...) এক্সেস করতে পারে,
সরকারি সাইট না। আমার আগের প্লেইন `web_fetch` টেস্টে দেখা গেছে টেবিলটা
JavaScript/AJAX দিয়ে রেন্ডার হয় (হেডার আছে, ডাটা রো খালি) — তাই
`scraper.py` তে Playwright ব্যবহার করেছি, কিন্তু **`extract_tender_rows()`
এবং `extract_detail_info()` ফাংশনের selector গুলো অনুমানভিত্তিক (generic
heuristic), ১০০% নিশ্চিত না।**

তাই প্রথমবার এভাবে টেস্ট করো:

1. Workflow ফাইলে সাময়িকভাবে `DEBUG_MODE: "true"` করে দাও।
2. ম্যানুয়ালি workflow রান করো।
3. রান শেষে "Actions" ট্যাবের সেই রানে গিয়ে নিচে **debug-output** নামের
   Artifact ডাউনলোড করো — এতে `debug_screenshot.png` ও `debug_page.html`
   থাকবে, এটা দেখে আসল সাইটের টেবিল/লিংক কেমন দেখতে সেটা বুঝতে পারবে।
4. লগেও (Actions রান লগ) দেখবে "মোট কত রো পাওয়া গেছে" এবং কোনো ওয়ার্নিং
   আসছে কিনা (যেমন `detail_url পাওয়া যায়নি`)।
5. যদি রো/লিংক ঠিকভাবে না পাওয়া যায়, তাহলে `debug_page.html` ব্রাউজারে
   খুলে টেবিলের actual class/id নাম দেখে আমাকে বলো — আমি selector গুলো
   ঠিক করে দেব। এই ধরনের সাইটে সাধারণত ২-১ বার এভাবে fine-tune করা লাগে।
6. ঠিকমতো কাজ করলে `DEBUG_MODE` আবার `"false"` করে দাও (নাহলে প্রতি রানে
   অপ্রয়োজনীয় artifact জমবে)।

### সম্ভাব্য যে সমস্যাগুলো হতে পারে (এবং কীভাবে বুঝবে)

- **GitHub Actions রানার IP ব্লকড থাকলে:** `page.goto()` টাইমআউট এরর দেবে
  বা খালি/এরর পেজ আসবে। সমাধান: self-hosted runner অথবা প্রক্সি।
- **টেন্ডার আইডি বের করার regex না মিললে:** "মোট রো পাওয়া গেছে: 0" লগে
  দেখবে। `debug_page.html` থেকে আসল প্যাটার্ন দেখে regex ঠিক করতে হবে।
- **Title লিংক `onclick` দিয়ে কাজ করলে (href না):** বর্তমান কোডে এই
  কেসে `detail_url = None` হয়ে যাবে এবং সেই টেন্ডারের জন্য শুধু লিস্ট
  পেজের তথ্য (Title, ID) পাঠানো হবে, Organization/Date/PDF পাবে না। এটা
  ঠিক করতে হলে আসল `onclick` জাভাস্ক্রিপ্ট ফাংশন দেখে হয় `page.click()`
  দিয়ে সিমুলেট করতে হবে, নয়তো URL প্যাটার্ন বের করে বানাতে হবে।
- **PDF লিংক সরাসরি না থেকে "Save" বাটনে ক্লিক করলে ডাউনলোড ট্রিগার হয়:**
  তাহলে `page.expect_download()` ব্যবহার করে ধরতে হবে — বর্তমান কোডে এই
  কেসটা কভার করা নেই, debug আউটপুট দেখে এটা লাগলে জানিও, আপডেট করে দেব।

সংক্ষেপে: কোডের কাঠামো (state tracking, Telegram sending, GitHub Actions
cron, PDF attach) পুরোপুরি রেডি। শুধু লিস্ট/ডিটেইলস পেজ থেকে ডাটা টানার
selector অংশটা প্রথম রানের ডিবাগ আউটপুট দেখে ১-২ বার টিউন করা লাগবে,
কারণ আমি লাইভ সাইটটা নিজে ব্রাউজ করে দেখতে পারিনি।

## ফাইল গঠন

```
tender-bot/
├── scraper.py                     # মূল স্ক্রিপ্ট
├── requirements.txt
├── state.json                     # আগে পাঠানো Tender ID এর লিস্ট (অটো-আপডেট হয়)
├── README.md
└── .github/workflows/scan.yml     # প্রতি ৪ ঘণ্টা পরপর cron
```
