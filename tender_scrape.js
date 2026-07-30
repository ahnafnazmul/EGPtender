// eprocure.gov.bd থেকে ই-টেন্ডার নোটিশ স্ক্র্যাপ করে HD বাংলা ব্যানার তৈরি করে Telegram এ পাঠায়

const fs = require("fs");
const path = require("path");
const axios = require("axios");
const puppeteer = require("puppeteer");
const FormData = require("form-data");

const TARGET_URL = "https://www.eprocure.gov.bd/resources/common/StdTenderSearch.jsp?h=t";
const VIEW_URL_PREFIX = "https://www.eprocure.gov.bd/resources/common/ViewTender.jsp?id=";
const SENT_FILE = path.join(__dirname, "sent_tenders.json");

const COLOR_THEMES = [
  { primary: "#0a3c22", accent: "#059669", watermark: "#0a3c22", bgCard: "#f0fdf4" }, // Forest Green
  { primary: "#0f2b48", accent: "#2563eb", watermark: "#0f2b48", bgCard: "#eff6ff" }, // Navy Blue
  { primary: "#4c1d95", accent: "#d97706", watermark: "#4c1d95", bgCard: "#fef3c7" }  // Violet Amber
];

// ---------- ইউটিলিটি ও অনুবাদ ফাংশন ----------

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

// ইংরেজি ডিজিট ও মাস বাংলায় রূপান্তর
function convertToBanglaDigitsAndMonths(text) {
  if (!text || text === "undefined" || text === "N/A") return text || "N/A";
  const digits = { '0': '০', '1': '১', '2': '২', '3': '৩', '4': '৪', '5': '৫', '6': '৬', '7': '৭', '8': '৮', '9': '৯' };
  const months = {
    'Jan': 'জানুয়ারি', 'Feb': 'ফেব্রুয়ারি', 'Mar': 'মার্চ', 'Apr': 'এপ্রিল',
    'May': 'মে', 'Jun': 'জুন', 'Jul': 'জুলাই', 'Aug': 'আগস্ট',
    'Sep': 'সেপ্টেম্বর', 'Oct': 'অক্টোবর', 'Nov': 'নভেম্বর', 'Dec': 'ডিসেম্বর'
  };

  let str = String(text);
  Object.keys(months).forEach(enM => {
    const reg = new RegExp(enM, 'gi');
    str = str.replace(reg, months[enM]);
  });
  return str.replace(/[0-9]/g, w => digits[w]);
}

// সংক্ষেপ রূপ অনুবাদক
function preCleanEnglishText(text) {
  if (!text) return "";
  return text
    .replace(/\bDev\.\b/gi, "Development")
    .replace(/\bDev\b/gi, "Development")
    .replace(/\bConst\.\b/gi, "Construction")
    .replace(/\bConst\b/gi, "Construction")
    .replace(/\bImp\.\b/gi, "Improvement")
    .replace(/\bImp\b/gi, "Improvement")
    .replace(/^(Works|Goods|Services|Service)\s*,\s*/i, "")
    .trim();
}

function getProcurementNatureBn(natureStr) {
  if (!natureStr || natureStr === "N/A") return "N/A";
  const clean = natureStr.trim().toLowerCase();
  if (clean.includes("works")) return "কার্য বা নির্মাণ কাজ (Works)";
  if (clean.includes("goods")) return "পণ্য বা মালামাল ক্রয় (Goods)";
  if (clean.includes("services") || clean.includes("service")) return "সেবা কাজ (Services)";
  return natureStr;
}

// ইংরেজি থেকে বাংলা অটোমেটিক ট্রান্সলেটর
async function translateToBangla(text) {
  if (!text || text === "N/A" || text === "undefined") return "N/A";
  const cleaned = preCleanEnglishText(text);
  try {
    const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=bn&dt=t&q=${encodeURIComponent(cleaned)}`;
    const res = await axios.get(url);
    if (res.data && res.data[0]) {
      let result = res.data[0].map(item => item[0]).join('');
      return convertToBanglaDigitsAndMonths(result);
    }
  } catch (err) {
    console.error("অনুবাদে ত্রুটি:", err.message);
  }
  return convertToBanglaDigitsAndMonths(cleaned);
}

// টাকায় কথায় রূপান্তর
function numberToBanglaWords(amountStr) {
  if (!amountStr || isNaN(amountStr) || amountStr === "N/A") return "";
  let num = parseInt(amountStr, 10);
  if (num === 0) return "";

  const ones = ["", "এক", "দুই", "তিন", "চার", "পাঁচ", "ছয়", "সাত", "আট", "নয়", "দশ", 
                "এগারো", "বারো", "তেরো", "চৌদ্দ", "পোনেরো", "ষোল", "সতেরো", "১৮", "উনিশ", "বিশ", 
                "একুশ", "বাইশ", "তেইশ", "চব্বিশ", "পঁচিশ", "ছাব্বিশ", "সাতাশ", "আটাশ", "উনত্রিশ", "ত্রিশ", 
                "একত্রিশ", "বত্রিশ", "তেরিশ", "চৌত্রিশ", "পঁয়তাল্লিশ", "ছত্রিশ", "সাইত্রিশ", "আটত্রিশ", "উনচল্লিশ", "চল্লিশ", 
                "একচল্লিশ", "বায়াল্লিশ", "তেতাল্লিশ", "চৌয়াল্লিশ", "পঁয়তাল্লিশ", "ছেচল্লিশ", "সাতচল্লিশ", "আটচল্লিশ", "উনপঞ্চাশ", "পঞ্চাশ", 
                "একান্ন", "বায়ান্ন", "তিরিপান্ন", "চৌয়ান্ন", "পঁচান্ন", "ছাপ্পান্ন", "সাতান্ন", "আটান্ন", "উনষাট", "ষাট", 
                "একষট্টি", "বাষট্টি", "তেষট্টি", "চৌষট্টি", "পঁয়ষট্টি", "ছেষট্টি", "সাতষট্টি", "আটষট্টি", "উনসত্তর", "সত্তর", 
                "একাত্তর", "বাহাত্তর", "তিয়াত্তর", "চৌহাত্তর", "পঁচাত্তর", "ছিয়াত্তর", "সাতাত্তর", "আটাত্তর", "উনাশি", "আশি", 
                "একাসি", "বিরাশি", "তিরাশি", "চৌরাশি", "পঁচাসি", "ছিয়াশি", "সাতাসি", "আটাসি", "উনানব্বই", "নব্বই", 
                "একানব্বই", "বিরানব্বই", "তিরা নব্বই", "চৌরানব্বই", "পঁচানব্বই", "ছিয়ানব্বই", "সাতানব্বই", "আটানব্বই", "নিরানব্বই"];

  let words = "";

  if (Math.floor(num / 10000000) > 0) {
    words += numberToBanglaWords(Math.floor(num / 10000000).toString()) + " কোটি ";
    num %= 10000000;
  }
  if (Math.floor(num / 100000) > 0) {
    words += ones[Math.floor(num / 100000)] + " লাখ ";
    num %= 100000;
  }
  if (Math.floor(num / 1000) > 0) {
    words += ones[Math.floor(num / 1000)] + " হাজার ";
    num %= 1000;
  }
  if (Math.floor(num / 100) > 0) {
    words += ones[Math.floor(num / 100)] + " শত ";
    num %= 100;
  }
  if (num > 0) {
    words += ones[num] + " ";
  }

  return words.trim() + " টাকা";
}

// ---------- e-GP স্ক্র্যাপিং ----------

async function runScraperTask() {
  console.log("--- e-GP টেন্ডার স্ক্র্যাপ চেক শুরু ---", new Date().toLocaleString("bn-BD"));

  const browser = await puppeteer.launch({
    headless: "new",
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
  });

  const sentIds = loadSentIds();

  try {
    const page = await browser.newPage();
    await page.setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36");
    
    await page.goto(TARGET_URL, { waitUntil: 'networkidle2', timeout: 60000 });
    await page.waitForSelector('table', { timeout: 20000 });

    const basicList = await page.evaluate(() => {
      const allRows = Array.from(document.querySelectorAll('table tr')).filter(r => r.querySelectorAll('td').length >= 5);
      const data = [];

      for (let index = 0; index < allRows.length; index++) {
        const cols = allRows[index].querySelectorAll('td');
        const col1Text = cols[1] ? cols[1].innerText.trim() : "";

        const idMatch = col1Text.match(/\d+/);
        const tenderId = idMatch ? idMatch[0] : "";

        if (tenderId) {
          data.push(tenderId);
        }
        if (data.length === 10) break;
      }
      return data;
    });

    const newTenders = basicList.filter(id => !sentIds.has(id));

    if (newTenders.length === 0) {
      console.log("নতুন কোনো টেন্ডার পাওয়া যায়নি।");
      await page.close();
      await browser.close();
      return;
    }

    console.log(`মোট ১০টির মধ্যে ${newTenders.length}টি নতুন টেন্ডার প্রসেস করা হচ্ছে...`);

    for (const tenderId of newTenders) {
      try {
        const directUrl = VIEW_URL_PREFIX + tenderId;
        await page.goto(directUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await new Promise(r => setTimeout(r, 1500));

        const details = await page.evaluate(() => {
          let orgName = "N/A", district = "N/A", appId = "N/A", nature = "N/A";
          let docPrice = "N/A", securityAmount = "N/A", pubDate = "N/A", lastDate = "N/A", title = "N/A";

          const allCells = Array.from(document.querySelectorAll('td, th'));

          for (let i = 0; i < allCells.length; i++) {
            const text = allCells[i].innerText.replace(/\s+/g, ' ').trim();

            if (text === "Organization :" || text === "Organization") {
              if (allCells[i + 1]) orgName = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim();
            }
            if (text.includes("Procuring Entity District")) {
              if (allCells[i + 1]) district = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim();
            }
            if (text.includes("APP ID") || text.includes("App ID")) {
              if (allCells[i + 1]) {
                const fullApp = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim();
                const appMatch = fullApp.match(/\d+/);
                appId = appMatch ? appMatch[0] : fullApp;
              }
            }
            if (text.includes("Procurement Nature")) {
              if (allCells[i + 1]) nature = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim();
            }
            if (text.includes("Tender/Proposal Package No. and Description")) {
              if (allCells[i + 1]) title = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim();
            }
            if (text.includes("Tender/Proposal Document Price")) {
              if (allCells[i + 1]) docPrice = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim().replace(/,/g, '');
            }
            if (text.includes("Scheduled Tender/Proposal Publication")) {
              if (allCells[i + 1]) pubDate = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim();
            }
            if (text.includes("Last Date and Time for Tender/Proposal Security")) {
              if (allCells[i + 1]) lastDate = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim();
            }
          }

          const securityHeader = allCells.find(cell => {
            const cleanText = cell.innerText.replace(/\s+/g, ' ').trim();
            return cleanText.includes("Tender/Proposal security") || cleanText.includes("Amount in BDT");
          });

          if (securityHeader) {
            const headerRow = securityHeader.closest('tr');
            const table = securityHeader.closest('table');
            if (headerRow && table) {
              const colIdx = Array.from(headerRow.children).indexOf(securityHeader);
              const allRows = Array.from(table.querySelectorAll('tr'));
              const headerRowIdx = allRows.indexOf(headerRow);
              if (headerRowIdx !== -1 && allRows[headerRowIdx + 1]) {
                const dataRow = allRows[headerRowIdx + 1];
                if (dataRow.children[colIdx]) {
                  const val = dataRow.children[colIdx].innerText.replace(/\s+/g, ' ').trim().replace(/,/g, '');
                  if (val) securityAmount = val;
                }
              }
            }
          }

          return { orgName, district, appId, nature, docPrice, securityAmount, pubDate, lastDate, title };
        });

        const tender = {
          id: tenderId,
          appId: details.appId,
          orgNameBn: details.orgName !== "N/A" ? await translateToBangla(details.orgName) : "N/A",
          districtBn: details.district !== "N/A" ? await translateToBangla(details.district) : "N/A",
          titleBn: details.title !== "N/A" ? await translateToBangla(details.title) : "N/A",
          natureBn: getProcurementNatureBn(details.nature),
          docPrice: details.docPrice,
          securityAmount: details.securityAmount,
          pubDate: details.pubDate,
          lastDate: details.lastDate
        };

        const caption = formatTenderMessage(tender);
        const imagePath = await generateTenderImage(browser, tender);

        if (imagePath && fs.existsSync(imagePath)) {
          await sendTelegramPhoto(imagePath, caption);
          try { fs.unlinkSync(imagePath); } catch (e) {}
        }

        sentIds.add(tender.id);
        saveSentIds(sentIds);

      } catch (err) {
        console.error(`ID ${tenderId} প্রসেস করতে সমস্যা:`, err.message);
      }

      await new Promise(r => setTimeout(r, 1500));
    }

    await page.close();

  } catch (err) {
    console.error("প্রধান স্ক্র্যাপিংয়ে সমস্যা:", err.message);
  } finally {
    await browser.close();
  }
}

// ---------- এইচডি টেন্ডার ব্যানার ইমেজ তৈরি (ভিজিবল ওয়াটারমার্ক ভ্যারিয়েন্ট) ----------

async function generateTenderImage(browser, tender) {
  const outputPath = path.join(__dirname, "temp_tender_banner.jpg");
  const page = await browser.newPage();

  await page.setViewport({ width: 1080, height: 1080, deviceScaleFactor: 2 });

  const tenderIdBn = convertToBanglaDigitsAndMonths(tender.id);
  const appIdBn = convertToBanglaDigitsAndMonths(tender.appId);
  const docPriceBn = convertToBanglaDigitsAndMonths(tender.docPrice);
  const securityBn = convertToBanglaDigitsAndMonths(tender.securityAmount);
  const pubDateBn = convertToBanglaDigitsAndMonths(tender.pubDate);
  const lastDateBn = convertToBanglaDigitsAndMonths(tender.lastDate);

  const docPriceWords = numberToBanglaWords(tender.docPrice);
  const securityWords = numberToBanglaWords(tender.securityAmount);

  const docPriceDisplay = docPriceWords ? `${docPriceBn} ৳ (${docPriceWords})` : `${docPriceBn} ৳`;
  const securityDisplay = securityWords ? `${securityBn} ৳ (${securityWords})` : `${securityBn} ৳`;

  const theme = COLOR_THEMES[Math.floor(Math.random() * COLOR_THEMES.length)];

  const htmlContent = `
  <!DOCTYPE html>
  <html lang="bn">
  <head>
    <meta charset="UTF-8">
    <link href="https://fonts.googleapis.com/css2?family=Anek+Bangla:wght@500;600;700;800;900&family=Hind+Siliguri:wght@500;600;700;800&family=Poppins:wght@600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body {
        width: 1080px;
        height: 1080px;
        font-family: 'Anek Bangla', 'Hind Siliguri', sans-serif;
        background: #f1f5f9;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        overflow: hidden;
        position: relative;
      }

      /* ওয়াটারমার্ক z-index: 10 দিয়ে সবার ওপরে আনা হয়েছে */
      .watermark {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%) rotate(-25deg);
        font-size: 50px;
        font-weight: 900;
        font-family: 'Poppins', sans-serif;
        color: ${theme.watermark};
        opacity: 0.12;
        white-space: nowrap;
        pointer-events: none;
        z-index: 10;
        width: 100%;
        text-align: center;
      }

      /* Header Style */
      .header-box {
        background: linear-gradient(135deg, ${theme.primary}, #0f172a);
        color: #ffffff;
        text-align: center;
        padding: 22px 30px 18px 30px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.15);
        z-index: 2;
      }
      .header-badge {
        display: inline-block;
        background: rgba(255, 255, 255, 0.15);
        border: 1px solid rgba(255, 255, 255, 0.3);
        color: #fbbf24;
        padding: 4px 18px;
        border-radius: 20px;
        font-size: 18px;
        font-weight: 700;
        margin-bottom: 8px;
        letter-spacing: 0.5px;
      }
      .header-org-name {
        font-size: 28px;
        font-weight: 800;
        color: #ffffff;
        line-height: 1.3;
      }

      /* Content Area with Cards */
      .content-body {
        padding: 20px 30px;
        flex: 1;
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 12px;
        z-index: 2;
      }

      /* Top Grid Cards */
      .grid-2 {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
      }

      .card {
        background: rgba(255, 255, 255, 0.92); /* সেমি-ট্রান্সপারেন্ট যাতে পেছনের ওয়াটারমার্ক দৃশ্যমান থাকে */
        padding: 12px 16px;
        border-radius: 12px;
        border-left: 5px solid ${theme.primary};
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        display: flex;
        flex-direction: column;
        justify-content: center;
      }

      .card-full {
        grid-column: span 2;
      }

      .card-highlight {
        background: ${theme.bgCard};
        border-left-color: ${theme.accent};
      }

      .card-label {
        font-size: 16px;
        font-weight: 800;
        color: #64748b;
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 2px;
      }

      .card-value {
        font-size: 20px;
        font-weight: 700;
        color: #0f172a;
        line-height: 1.35;
        word-break: break-word;
      }

      .card-value-large {
        font-size: 22px;
        font-weight: 800;
        color: ${theme.primary};
      }

      /* Footer Area */
      .footer-container {
        padding: 0 30px 20px 30px;
        z-index: 2;
      }

      .footer-card {
        border: 2px solid ${theme.primary};
        border-radius: 12px;
        overflow: hidden;
        background: #ffffff;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
      }

      .footer-top-banner {
        background-color: #f8fafc;
        color: ${theme.primary};
        font-size: 16px;
        font-weight: 800;
        padding: 6px 12px;
        text-align: center;
        border-bottom: 2px dashed ${theme.primary};
      }

      .footer-main-body {
        background-color: ${theme.primary};
        color: #ffffff;
        padding: 10px 20px;
        text-align: center;
      }

      .brand-title {
        font-size: 30px;
        font-weight: 900;
        line-height: 1.2;
        margin-bottom: 6px;
      }

      .footer-bottom-row {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 30px;
      }

      .brand-address {
        font-size: 19px;
        font-weight: 700;
        color: #e2e8f0;
      }

      .phone-section {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 22px;
        font-weight: 800;
        background: rgba(255, 255, 255, 0.12);
        padding: 3px 14px;
        border-radius: 8px;
      }

      .social-icons {
        display: flex;
        gap: 8px;
        font-size: 20px;
      }

      .fa-whatsapp { color: #25D366; }
      .fa-telegram { color: #24A1DE; }
    </style>
  </head>
  <body>

    <div class="watermark">FNF COMPUTER & ONLINE SERVICES</div>

    <div class="header-box">
      <div class="header-badge">ই-টেন্ডার নোটিশ (e-GP)</div>
      <div class="header-org-name">${tender.orgNameBn}</div>
    </div>

    <div class="content-body">
      <div class="grid-2">
        <div class="card card-highlight">
          <div class="card-label">🆔 টেন্ডার আইডি</div>
          <div class="card-value card-value-large">${tenderIdBn}</div>
        </div>
        <div class="card">
          <div class="card-label">🔢 এপিপি আইডি (APP ID)</div>
          <div class="card-value">${appIdBn}</div>
        </div>
      </div>

      <div class="grid-2">
        <div class="card">
          <div class="card-label">🏢 দপ্তর / সংস্থা</div>
          <div class="card-value">${tender.orgNameBn}</div>
        </div>
        <div class="card">
          <div class="card-label">📍 জেলা / এলাকা</div>
          <div class="card-value">${tender.districtBn}</div>
        </div>
      </div>

      <div class="card card-full">
        <div class="card-label">🏗️ কাজের বিবরণ</div>
        <div class="card-value">${tender.titleBn}</div>
      </div>

      <div class="card card-full">
        <div class="card-label">📌 কাজের ধরন</div>
        <div class="card-value">${tender.natureBn}</div>
      </div>

      <div class="grid-2">
        <div class="card">
          <div class="card-label">💵 শিডিউল এর দাম</div>
          <div class="card-value">${docPriceDisplay}</div>
        </div>
        <div class="card">
          <div class="card-label">🛡️ সিকিউরিটি এমাউন্ট</div>
          <div class="card-value">${securityDisplay}</div>
        </div>
      </div>

      <div class="grid-2">
        <div class="card">
          <div class="card-label">📅 প্রকাশের তারিখ</div>
          <div class="card-value">${pubDateBn}</div>
        </div>
        <div class="card card-highlight">
          <div class="card-label">⏰ জমাদানের শেষ তারিখ</div>
          <div class="card-value card-value-large" style="color: #dc2626;">${lastDateBn}</div>
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
    console.error("ইমেজ তৈরিতে সমস্যা:", error.message);
    await page.close();
    return null;
  }
}

// ---------- টেলিগ্রামে পাঠানো ----------

function formatTenderMessage(tender) {
  const docPriceWords = numberToBanglaWords(tender.docPrice);
  const securityWords = numberToBanglaWords(tender.securityAmount);

  const docPriceDisplay = docPriceWords ? `${tender.docPrice} BDT (${docPriceWords})` : `${tender.docPrice} BDT`;
  const securityDisplay = securityWords ? `${tender.securityAmount} BDT (${securityWords})` : `${tender.securityAmount} BDT`;

  return [
    `📢 *নতুন ই-টেন্ডার নোটিশ (e-GP)*`,
    ``,
    `🏢 *দপ্তর:* ${tender.orgNameBn}`,
    `🆔 *টেন্ডার আইডি:* \`${tender.id}\``,
    `🔢 *এপপ আইডি:* ${tender.appId}`,
    `📍 *এলাকা:* ${tender.districtBn}`,
    `🏗️ *কাজের বিবরণ:* ${tender.titleBn}`,
    `📌 *কাজের ধরন:* ${tender.natureBn}`,
    `💵 *শিডিউল এর দাম:* ${docPriceDisplay}`,
    `🛡️ *সিকিউরিটি এমাউন্ট:* ${securityDisplay}`,
    `📅 *প্রকাশের তারিখ:* ${tender.pubDate}`,
    `⏰ *জমাদানের শেষ তারিখ:* ${tender.lastDate}`,
    ``,
    `যেকোন টেন্ডারে অংশগ্রহণে সার্বিক সহায়তায় যোগাযোগ করুন:`,
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
    console.log("Telegram এ টেন্ডার ব্যানার সফলভাবে পাঠানো হয়েছে ✅");
    return true;
  } catch (e) {
    console.error("Telegram এ পাঠাতে সমস্যা:", e.message);
    return false;
  }
}

// ---------- অটোমেশন রান ও সঠিকভাবে এক্সিট ----------

runScraperTask().then(() => {
  console.log("আজকের পর্বের টেন্ডার প্রসেসিং সম্পূর্ণ এবং সফলভাবে বন্ধ করা হলো ✅");
  process.exit(0);
}).catch((err) => {
  console.error("রান টাইমে এরর:", err);
  process.exit(1);
});
