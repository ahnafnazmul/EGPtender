// eprocure.gov.bd থেকে ই-টেন্ডার নোটিশ স্ক্র্যাপ করে AllJobs ডিজাইনে HD ব্যানার তৈরি করে Telegram এ পাঠায়

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
  if (!text) return text || "";
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

// সংখ্যাকে বাংলায় কথায় রূপান্তর করার ফাংশন
function numberToBanglaWords(amountStr) {
  if (!amountStr || isNaN(amountStr) || amountStr === "N/A") return "";
  let num = parseInt(amountStr, 10);
  if (num === 0) return "";

  const ones = ["", "এক", "দুই", "তিন", "চার", "পাঁচ", "ছয়", "সাত", "আট", "নয়", "দশ", 
                "এগারো", "বারো", "তেরো", "চৌদ্দ", "পোনেরো", "ষোল", "সতেরো", "১৮", "উনিশ", "বিশ", 
                "একুশ", "বাইশ", "তেইশ", "চব্বিশ", "পঁচিশ", "ছাব্বিশ", "সাতাশ", "আটাশ", "উনত্রিশ", "ত্রিশ", 
                "একত্রিশ", "বত্রিশ", "তেরিশ", "চৌত্রিশ", "পঁয়ত্রিশ", "ছত্রিশ", "সাইত্রিশ", "আটত্রিশ", "উনচল্লিশ", "চল্লিশ", 
                "একচল্লিশ", "বায়াল্লিশ", "তেতাল্লিশ", "চৌয়াল্লিশ", "পঁয়তাল্লিশ", "ছেচল্লিশ", "সাতচল্লিশ", "আটচল্লিশ", "উনপঞ্চাশ", "পঞ্চাশ", 
                "একান্ন", "বায়ান্ন", "তিরিপান্ন", "চৌয়ান্ন", "পঁচান্ন", "ছাপ্পান্ন", "সাতান্ন", "আটান্ন", "উনষাট", "ষাট", 
                "একষট্টি", "বাষট্টি", "তেষট্টি", "চৌষট্টি", "পঁয়ষট্টি", "ছেষট্টি", "সাতষট্টি", "আটষট্টি", "উনসত্তর", "সত্তর", 
                "একাত্তর", "বাহাত্তর", "তিয়াত্তর", "চৌহাত্তর", "পঁচাত্তর", "ছিয়াত্তর", "সাতাত্তর", "আটাত্তর", "উনাশি", "আশি", 
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

// ---------- e-GP স্ক্র্যাপিং (Puppeteer দিয়ে) ----------

async function fetchTendersAndDetails(browser) {
  console.log("e-GP পোর্টাল লোড করা হচ্ছে...");
  const page = await browser.newPage();
  
  await page.setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36");

  try {
    await page.goto(TARGET_URL, { waitUntil: 'networkidle2', timeout: 60000 });
    await page.waitForSelector('table', { timeout: 20000 });

    const basicList = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('table tr')).filter(r => r.querySelectorAll('td').length >= 5);
      const data = [];

      rows.slice(0, 10).forEach((row, index) => {
        const cols = row.querySelectorAll('td');
        if (cols.length < 5) return;

        const col1Text = cols[1].innerText.trim();
        const col2Text = cols[2].innerText.trim();

        const idMatch = col1Text.match(/\d+/);
        const tenderId = idMatch ? idMatch[0] : "";

        if (tenderId) {
          data.push({
            rowIndex: index,
            id: tenderId,
            title: col2Text.replace(/\n/g, ' '),
            orgName: "N/A",
            district: "N/A",
            appId: "N/A",
            nature: "N/A",
            docPrice: "N/A",
            securityAmount: "N/A",
            pubDate: "N/A",
            lastDate: "N/A"
          });
        }
      });

      return data;
    });

    const sentIds = loadSentIds();
    const newTenders = basicList.filter(t => !sentIds.has(t.id));

    if (newTenders.length === 0) {
      await page.close();
      return { newTenders: [], sentIds };
    }

    console.log(`${newTenders.length}টি নতুন টেন্ডারের ডিটেইলস সংগৃহীত হচ্ছে...`);

    for (const tender of newTenders) {
      try {
        const titleLinks = await page.$$('table tr td:nth-child(3) a');
        if (titleLinks[tender.rowIndex]) {
          
          const newTargetPromise = browser.waitForTarget(target => target.opener() === page.target(), { timeout: 15000 });
          await titleLinks[tender.rowIndex].click();
          const newTarget = await newTargetPromise;
          const detailPage = await newTarget.page();

          if (detailPage) {
            await detailPage.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {});
            
            await new Promise(r => setTimeout(r, 1000));

            const details = await detailPage.evaluate(() => {
              let orgName = "N/A";
              let district = "N/A";
              let appId = "N/A";
              let nature = "N/A";
              let docPrice = "N/A";
              let securityAmount = "N/A";
              let pubDate = "N/A";
              let lastDate = "N/A";

              const allCells = Array.from(document.querySelectorAll('td, th'));

              for (let i = 0; i < allCells.length; i++) {
                const text = allCells[i].innerText.replace(/\s+/g, ' ').trim();

                // Organization
                if (text.includes("Organization :") || text === "Organization") {
                  if (allCells[i + 1]) orgName = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim();
                }

                // Procuring Entity District
                if (text.includes("Procuring Entity District") || text.includes("District :")) {
                  if (allCells[i + 1]) district = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim();
                }

                // APP ID
                if (text.includes("APP ID") || text.includes("App ID")) {
                  if (allCells[i + 1]) appId = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim();
                }

                // Procurement Nature
                if (text.includes("Procurement Nature")) {
                  if (allCells[i + 1]) nature = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim();
                }

                // Document Price
                if (text.includes("Tender/Proposal Document Price")) {
                  if (allCells[i + 1]) docPrice = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim().replace(/,/g, '');
                }

                // Scheduled Tender/Proposal Publication Date and Time
                if (text.includes("Scheduled Tender/Proposal Publication")) {
                  if (allCells[i + 1]) pubDate = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim();
                }

                // Last Date and Time for Tender/Proposal Security Submission
                if (text.includes("Last Date and Time for Tender/Proposal Security")) {
                  if (allCells[i + 1]) lastDate = allCells[i + 1].innerText.replace(/\s+/g, ' ').trim();
                }
              }

              // Security Amount (Lot Table)
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

              return { orgName, district, appId, nature, docPrice, securityAmount, pubDate, lastDate };
            });

            tender.orgName = details.orgName;
            tender.district = details.district;
            tender.appId = details.appId;
            tender.nature = details.nature;
            tender.docPrice = details.docPrice;
            tender.securityAmount = details.securityAmount;
            tender.pubDate = details.pubDate;
            tender.lastDate = details.lastDate;

            await detailPage.close();
          }
        }
      } catch (err) {
        console.error(`ID ${tender.id} এর ডিটেইলস নিতে সমস্যা:`, err.message);
      }
    }

    await page.close();
    return { newTenders, sentIds };

  } catch (err) {
    console.error("প্রধান পেজ স্ক্র্যাপিংয়ে সমস্যা:", err.message);
    await page.close();
    return { newTenders: [], sentIds: loadSentIds() };
  }
}

// ---------- এইচডি টেন্ডার ব্যানার ইমেজ তৈরি ----------

async function generateTenderImage(browser, tender) {
  const outputPath = path.join(__dirname, "temp_tender_banner.jpg");
  const page = await browser.newPage();

  await page.setViewport({ width: 800, height: 980, deviceScaleFactor: 2 });

  const tenderIdBn = convertToBanglaDigitsAndMonths(tender.id);
  const appIdBn = convertToBanglaDigitsAndMonths(tender.appId);
  const docPriceBn = convertToBanglaDigitsAndMonths(tender.docPrice);
  const securityBn = convertToBanglaDigitsAndMonths(tender.securityAmount);
  const pubDateBn = convertToBanglaDigitsAndMonths(tender.pubDate);
  const lastDateBn = convertToBanglaDigitsAndMonths(tender.lastDate);

  // টাকায় কথায় বের করা
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
    <link href="https://fonts.googleapis.com/css2?family=Anek+Bangla:wght@600;700;800;900&family=Hind+Siliguri:wght@600;700;800&family=Poppins:wght@600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
      * { box-sizing: border-box; }
      body {
        width: 800px;
        height: 980px;
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
        padding: 16px 20px;
        z-index: 2;
      }
      .header-title-bn {
        font-size: 32px;
        font-weight: 800;
        margin: 0;
      }
      .header-title-sub {
        font-size: 20px;
        font-weight: 700;
        opacity: 0.95;
        margin-top: 4px;
      }
      .header-org-name {
        font-size: 18px;
        font-weight: 700;
        color: #f1f5f9;
        margin-top: 3px;
      }

      .content-body {
        padding: 18px 35px;
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
        line-height: 1.35;
      }

      .info-icon {
        font-size: 22px;
        width: 34px;
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

      /* Compact AllJobs Style Footer */
      .footer-container {
        padding: 0 25px 20px 25px;
        z-index: 2;
      }

      .footer-card {
        border: 2px solid ${theme.primary};
        border-radius: 8px;
        overflow: hidden;
        background: #ffffff;
      }

      .footer-top-banner {
        background-color: #ffffff;
        color: ${theme.primary};
        font-size: 18px;
        font-weight: 800;
        padding: 5px 10px;
        text-align: center;
        border-bottom: 2px solid ${theme.primary};
      }

      .footer-main-body {
        background-color: ${theme.primary};
        color: #ffffff;
        padding: 10px 15px;
        text-align: center;
      }

      .brand-title {
        font-size: 34px;
        font-weight: 900;
        line-height: 1.1;
        margin-bottom: 6px;
        letter-spacing: -0.5px;
        white-space: nowrap;
      }

      .footer-bottom-row {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 30px;
        padding: 0 5px;
      }

      .brand-address {
        display: flex;
        align-items: center;
        gap: 5px;
        font-size: 21px;
        font-weight: 800;
      }

      .phone-section {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 25px;
        font-weight: 800;
      }

      .social-icons {
        display: flex;
        gap: 6px;
        font-size: 22px;
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
      <div class="header-org-name">${tender.orgName}</div>
    </div>

    <div class="content-body">
      <div class="info-list">
        <div class="info-item">
          <span class="info-icon">🆔</span>
          <span class="info-label">টেন্ডার আইডি:</span>
          <span class="info-val">${tenderIdBn}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">🔢</span>
          <span class="info-label">এপপ আইডি (APP ID):</span>
          <span class="info-val">${appIdBn}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">🏢</span>
          <span class="info-label">দপ্তর:</span>
          <span class="info-val">${tender.orgName}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">📍</span>
          <span class="info-label">এলাকা:</span>
          <span class="info-val">${tender.district}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">🏗️</span>
          <span class="info-label">কাজের বিবরন:</span>
          <span class="info-val">${tender.title}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">📌</span>
          <span class="info-label">কাজের ধরন:</span>
          <span class="info-val">${tender.nature}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">💵</span>
          <span class="info-label">শিডিউল এর দাম:</span>
          <span class="info-val">${docPriceDisplay}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">🛡️</span>
          <span class="info-label">সিকিউরিটি এমাউন্ট:</span>
          <span class="info-val">${securityDisplay}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">📅</span>
          <span class="info-label">প্রকাশের তারিখ:</span>
          <span class="info-val">${pubDateBn}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">⏰</span>
          <span class="info-label">জমাদানের শেষ তারিখ:</span>
          <span class="info-val">${lastDateBn}</span>
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
  const docPriceWords = numberToBanglaWords(tender.docPrice);
  const securityWords = numberToBanglaWords(tender.securityAmount);

  const docPriceDisplay = docPriceWords ? `${tender.docPrice} BDT (${docPriceWords})` : `${tender.docPrice} BDT`;
  const securityDisplay = securityWords ? `${tender.securityAmount} BDT (${securityWords})` : `${tender.securityAmount} BDT`;

  return [
    `📢 *নতুন ই-টেন্ডার নোটিশ (e-GP)*`,
    ``,
    `🆔 *টেন্ডার আইডি:* \`${tender.id}\``,
    `🔢 *এপপ আইডি:* ${tender.appId}`,
    `🏢 *দপ্তর:* ${tender.orgName}`,
    `📍 *এলাকা:* ${tender.district}`,
    `🏗️ *কাজের বিবরন:* ${tender.title}`,
    `📌 *কাজের ধরন:* ${tender.nature}`,
    `💵 *শিডিউল এর দাম:* ${docPriceDisplay}`,
    `🛡️ *সিকিউরিটি এমাউন্ট:* ${securityDisplay}`,
    `📅 *প্রকাশের তারিখ:* ${tender.pubDate}`,
    `⏰ *জমাদানের শেষ তারিখ:* ${tender.lastDate}`,
    ``,
    `সার্বিক সহায়তায়:`,
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
    console.error("Telegram এ পাঠাতে ব্যর্থ:", e.message);
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
    const { newTenders, sentIds } = await fetchTendersAndDetails(browser);

    if (newTenders.length === 0) {
      console.log("নতুন কোনো টেন্ডার নেই।");
      await browser.close();
      return;
    }

    for (const tender of newTenders) {
      const caption = formatTenderMessage(tender);
      const imagePath = await generateTenderImage(browser, tender);

      if (imagePath && fs.existsSync(imagePath)) {
        await sendTelegramPhoto(imagePath, caption);
        try { fs.unlinkSync(imagePath); } catch (e) {}
      }

      sentIds.add(tender.id);
      await new Promise(r => setTimeout(r, 2000));
    }

    saveSentIds(sentIds);
    console.log("টেন্ডার প্রসেসিং সম্পূর্ণ ✅");
  } finally {
    await browser.close();
  }
}

main().catch(err => {
  console.error("ফেইলড:", err);
  process.exit(1);
});
