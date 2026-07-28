// eprocure.gov.bd থেকে নতুন ১০টি ই-টেন্ডার নোটিশ স্ক্র্যাপ করে HD ব্যানার তৈরি করে Telegram এ পাঠায়

const fs = require("fs");
const path = require("path");
const axios = require("axios");
const puppeteer = require("puppeteer");
const FormData = require("form-data");

const TARGET_URL = "https://www.eprocure.gov.bd/resources/common/StdTenderSearch.jsp?h=t";
const SENT_FILE = path.join(__dirname, "sent_tenders.json");

// কালার থিম কালেকশন
const COLOR_THEMES = [
  { primary: "#0a3c22", watermark: "#10b981" }, // Deep Forest Green
  { primary: "#0f2b48", watermark: "#3b82f6" }, // Deep Navy Blue
  { primary: "#4c1d95", watermark: "#f59e0b" }  // Deep Violet
];

// ---------- ইউটিলিটি ----------

function loadSentIds() {
  try {
    const raw = fs.readFileSync(SENT_FILE, "utf-8");
    return new Set(JSON.parse(raw));
  } catch (e) {
    return new Set();
  }
}

function saveSentIds(set) {
  const arr = Array.from(set).slice(-500);
  fs.writeFileSync(SENT_FILE, JSON.stringify(arr, null, 2), "utf-8");
}

function convertToBanglaDigitsAndMonths(text) {
  if (!text) return text;
  const digits = { '0': '০', '1': '১', '2': '২', '3': '৩', '4': '৪', '5': '৫', '6': '৬', '7': '৭', '8': '৮', '9': '৯' };
  const months = {
    'Jan': 'জানুয়ারি', 'Feb': 'ফেব্রুয়ারি', 'Mar': 'মার্চ', 'Apr': 'এপ্রিল',
    'May': 'মে', 'Jun': 'জুন', 'Jul': 'জুলাই', 'Aug': 'আগস্ট',
    'Sep': 'সেপ্টেম্বর', 'Oct': 'অক্টোবর', 'Nov': 'নভেম্বর', 'Dec': 'ডিসেম্বর'
  };

  let str = text;
  Object.keys(months).forEach(enM => {
    const reg = new RegExp(enM, 'gi');
    str = str.replace(reg, months[enM]);
  });
  return str.replace(/[0-9]/g, w => digits[w]);
}

// ---------- e-GP স্ক্র্যাপিং (Puppeteer দিয়ে) ----------

async function fetchTenders(browser) {
  console.log("e-GP পোর্টাল লোড করা হচ্ছে...");
  const page = await browser.newPage();
  
  try {
    await page.goto(TARGET_URL, { waitUntil: 'networkidle2', timeout: 60000 });
    await page.waitForSelector('table', { timeout: 20000 });

    const tenders = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('table tr')).filter(r => r.querySelectorAll('td').length >= 5);
      const data = [];

      rows.slice(0, 10).forEach(row => {
        const cols = row.querySelectorAll('td');
        if (cols.length < 5) return;

        const col1Text = cols[1].innerText.trim(); // ID & Ref
        const col2Text = cols[2].innerText.trim(); // Title & Nature
        const col3Text = cols[3].innerText.trim(); // PE / Ministry
        const col4Text = cols[4].innerText.trim(); // Type / Method
        const col5Text = cols[5] ? cols[5].innerText.trim() : ""; // Dates

        const idMatch = col1Text.match(/\d+/);
        const tenderId = idMatch ? idMatch[0] : "";

        if (tenderId) {
          data.push({
            id: tenderId,
            refNo: col1Text.replace(/\n/g, ' '),
            title: col2Text.replace(/\n/g, ' '),
            peName: col3Text.replace(/\n/g, ' '),
            method: col4Text.replace(/\n/g, ' '),
            dates: col5Text.replace(/\n/g, ' ')
          });
        }
      });

      return data;
    });

    await page.close();
    return tenders;
  } catch (err) {
    console.error("স্ক্র্যাপিংয়ে সমস্যা:", err.message);
    await page.close();
    return [];
  }
}

// ---------- এইচডি টেন্ডার ব্যানার ইমেজ তৈরি ----------

async function generateTenderImage(browser, tender) {
  const outputPath = path.join(__dirname, "temp_tender_banner.jpg");
  const page = await browser.newPage();

  await page.setViewport({ width: 800, height: 800, deviceScaleFactor: 2 });

  const tenderIdBn = convertToBanglaDigitsAndMonths(tender.id);
  const datesBn = convertToBanglaDigitsAndMonths(tender.dates);
  const theme = COLOR_THEMES[Math.floor(Math.random() * COLOR_THEMES.length)];

  const htmlContent = `
  <!DOCTYPE html>
  <html lang="bn">
  <head>
    <meta charset="UTF-8">
    <link href="https://fonts.googleapis.com/css2?family=Anek+Bangla:wght@600;700;800;900&family=Hind+Siliguri:wght@600;700;800&family=Poppins:wght@600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
      * { box-sizing: border-box; }
      body {
        width: 800px;
        height: 800px;
        margin: 0;
        padding: 0;
        font-family: 'Anek Bangla', 'Hind Siliguri', sans-serif;
        background: #f8fafc;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        overflow: hidden;
        position: relative;
      }

      .watermark {
        position: absolute;
        top: 48%;
        left: 50%;
        transform: translate(-50%, -50%) rotate(-28deg);
        font-size: 38px;
        font-weight: 800;
        font-family: 'Poppins', sans-serif;
        color: ${theme.watermark};
        opacity: 0.08;
        white-space: nowrap;
        pointer-events: none;
        z-index: 1;
      }

      .header-box {
        background-color: ${theme.primary};
        color: #ffffff;
        text-align: center;
        padding: 18px 20px;
        z-index: 2;
      }
      .header-title-bn {
        font-size: 34px;
        font-weight: 800;
        margin: 0;
      }
      .header-title-sub {
        font-size: 20px;
        font-weight: 700;
        opacity: 0.9;
        margin-top: 4px;
      }

      .content-body {
        padding: 15px 40px;
        flex: 1;
        display: flex;
        flex-direction: column;
        justify-content: center;
        z-index: 2;
      }

      .info-list {
        display: flex;
        flex-direction: column;
        gap: 12px;
      }

      .info-item {
        display: flex;
        align-items: flex-start;
        font-size: 21px;
        color: #0f172a;
        font-weight: 700;
        line-height: 1.3;
      }

      .info-icon {
        font-size: 24px;
        width: 38px;
        text-align: center;
        margin-right: 8px;
        flex-shrink: 0;
      }

      .info-label {
        color: #0f172a;
        margin-right: 6px;
        white-space: nowrap;
        flex-shrink: 0;
      }

      .info-val {
        color: #0f172a;
        font-weight: 800;
        word-break: break-word;
      }

      .footer-container {
        padding: 0 25px 20px 25px;
        z-index: 2;
      }

      .footer-card {
        border: 2px solid ${theme.primary};
        border-radius: 10px;
        overflow: hidden;
        background: #ffffff;
      }

      .footer-top-banner {
        background-color: #ffffff;
        color: ${theme.primary};
        font-size: 20px;
        font-weight: 800;
        padding: 6px 10px;
        text-align: center;
        border-bottom: 2px solid ${theme.primary};
      }

      .footer-main-body {
        background-color: ${theme.primary};
        color: #ffffff;
        padding: 12px 15px 14px 15px;
        text-align: center;
      }

      .brand-title {
        font-size: 34px;
        font-weight: 900;
        margin-bottom: 6px;
        letter-spacing: -0.3px;
        white-space: nowrap;
      }

      .footer-bottom-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 10px;
      }

      .brand-address {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 24px;
        font-weight: 800;
      }

      .phone-section {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 29px;
        font-weight: 800;
      }

      .social-icons {
        display: flex;
        gap: 6px;
        font-size: 26px;
      }

      .fa-whatsapp { color: #25D366; }
      .fa-telegram { color: #24A1DE; }
    </style>
  </head>
  <body>

    <div class="watermark">FNF COMPUTER & ONLINE SERVICES</div>

    <div class="header-box">
      <div class="header-title-bn">নতুন ই-টেন্ডার নোটিশ (e-GP)</div>
      <div class="header-title-sub">Tender ID: ${tender.id}</div>
    </div>

    <div class="content-body">
      <div class="info-list">
        <div class="info-item">
          <span class="info-icon">🆔</span>
          <span class="info-label">টেন্ডার আইডি:</span>
          <span class="info-val">${tenderIdBn}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">🏢</span>
          <span class="info-label">দপ্তর/প্রতিষ্ঠান:</span>
          <span class="info-val">${tender.peName}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">🏗️</span>
          <span class="info-label">কাজের বিবরণ:</span>
          <span class="info-val">${tender.title}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">📌</span>
          <span class="info-label">পদ্ধতি (Method):</span>
          <span class="info-val">${tender.method}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">📅</span>
          <span class="info-label">সময়সূচী:</span>
          <span class="info-val">${datesBn}</span>
        </div>
      </div>
    </div>

    <div class="footer-container">
      <div class="footer-card">
        <div class="footer-top-banner">যেকোন টেন্ডারে অংশগ্রহণে সার্বিক সহায়তায় যোগাযোগ করুন</div>
        <div class="footer-main-body">
          <div class="brand-title">এফ. এন. এফ কম্পিউটার & অনলাইন সার্ভিসেস</div>
          <div class="footer-bottom-row">
            <div class="brand-address">📍 বাংলাবাজার রোড, বরিশাল।</div>
            <div class="phone-section">
              <div class="social-icons">
                <i class="fa-brands fa-whatsapp"></i>
                <i class="fa-brands fa-telegram"></i>
              </div>
              <span>01533199800</span>
            </div>
          </div>
        </div>
      </div>
    </div>

  </body>
  </html>
  `;

  try {
    await page.setContent(htmlContent, { waitUntil: 'networkidle0' });
    await page.screenshot({ path: outputPath, type: 'jpeg', quality: 95 });
    await page.close();
    return outputPath;
  } catch (error) {
    console.error("টেন্ডার ইমেজ তৈরিতে সমস্যা:", error.message);
    await page.close();
    return null;
  }
}

// ---------- টেলিগ্রামে পাঠানো ----------

function formatTenderMessage(tender) {
  return [
    `📢 *নতুন ই-টেন্ডার নোটিশ (e-GP)*`,
    ``,
    `🆔 *Tender ID:* \`${tender.id}\``,
    `🏢 *প্রতিষ্ঠান:* ${tender.peName}`,
    `🏗️ *কাজের শিরোনাম:* ${tender.title}`,
    `📌 *পদ্ধতি:* ${tender.method}`,
    `📅 *সময়সূচী:* ${tender.dates}`,
    ``,
    `যোগাযোগ:`,
    `এফ. এন. এফ কম্পিউটার & অনলাইন সার্ভিসেস`,
    `বাংলাবাজার রোড, বরিশাল। 📱 01533199800`
  ].join("\n");
}

async function sendTelegramPhoto(imagePath, caption) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) return false;

  try {
    const formData = new FormData();
    formData.append("chat_id", chatId);
    formData.append("photo", fs.createReadStream(imagePath));
    formData.append("caption", caption);
    formData.append("parse_mode", "Markdown");

    await axios.post(`https://api.telegram.org/bot${token}/sendPhoto`, formData, {
      headers: formData.getHeaders()
    });
    console.log("Telegram এ টেন্ডার ব্যানার পাঠানো হয়েছে ✅");
    return true;
  } catch (e) {
    console.error("Telegram এ টেন্ডার পাঠাতে ব্যর্থ:", e.message);
    return false;
  }
}

// ---------- মেইন এক্সিকিউশন ----------

async function main() {
  console.log("e-GP টেন্ডার স্ক্র্যাপ শুরু...", new Date().toISOString());

  const browser = await puppeteer.launch({
    headless: "new",
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
  });

  try {
    const tenders = await fetchTenders(browser);
    console.log(`মোট ${tenders.length}টি টেন্ডার পাওয়া গেছে`);

    const sentIds = loadSentIds();
    const newTenders = tenders.filter(t => !sentIds.has(t.id));

    if (newTenders.length === 0) {
      console.log("নতুন কোনো টেন্ডার নেই।");
      await browser.close();
      return;
    }

    console.log(`${newTenders.length}টি নতুন টেন্ডার প্রসেস করা হচ্ছে...`);

    for (const tender of newTenders) {
      const caption = formatTenderMessage(tender);
      const imagePath = await generateTenderImage(browser, tender);

      if (imagePath && fs.existsSync(imagePath)) {
        await sendTelegramPhoto(imagePath, caption);
        try { fs.unlinkSync(imagePath); } catch (e) {}
      }

      sentIds.add(tender.id);
      await new Promise(r => setTimeout(r, 3000));
    }

    saveSentIds(sentIds);
    console.log("টেন্ডার প্রসেসিং সম্পন্ন ✅");
  } finally {
    await browser.close();
  }
}

main().catch(err => {
  console.error("ফেইলড:", err);
  process.exit(1);
});
