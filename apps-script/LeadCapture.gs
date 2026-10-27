/**
 * CRO Accelerate — Lead capture (Google Apps Script web app)
 * Website forms  ->  this script  ->  Google Sheet "Leads" (+ email + Telegram alert)
 *
 * SETUP (once):
 *  1. Create a Google Sheet "CRO Accelerate — Leads". Extensions → Apps Script → paste this file.
 *  2. Project Settings → Script properties:
 *       OWNER_EMAIL   = your email for alerts
 *       TG_BOT_TOKEN  = (optional) Telegram bot token
 *       TG_CHAT_ID    = (optional) your chat id
 *       AUTO_REPLY    = "yes" to send a short confirmation to the lead (optional)
 *  3. Run setup() once (authorise).
 *  4. Deploy → New deployment → Web app → Execute as: Me, Who has access: Anyone → copy the /exec URL
 *     into GitHub → Settings → Secrets and variables → Actions → Variables → LEAD_ENDPOINT, then re-run Deploy.
 *  5. After editing this script: Deploy → Manage deployments → Edit → Version: New version (URL stays the same).
 */

var SHEET_LEADS = 'Leads';
var SHEET_STATS = 'Stats';
var HEADERS = [
  'Received', 'Status', 'ICP fit', 'Region', 'Form', 'Lead type', 'Name', 'Email', 'Company', 'Role', 'Company size',
  'Country', 'Interest', 'Message', 'Score', 'Score by dimension', 'Answers',
  'Page', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'gclid', 'li_fat_id',
  'First source', 'First medium', 'First campaign', 'Landing page', 'Referrer', 'Timezone', 'Language',
  'Next step', 'Notes', 'Roadmap draft (agent)', 'Deal value', 'Lead ID'
];
var TARGET_COUNTRIES = /(germany|deutschland|austria|switzerland|netherlands|belgium|france|uk|united kingdom|england|ireland|poland|czech|sweden|denmark|norway|finland|spain|italy|portugal|usa|united states|us|america|canada|estonia|latvia|lithuania)/i;

function setup() {
  var ss = SpreadsheetApp.getActive();
  var sh = ss.getSheetByName(SHEET_LEADS) || ss.insertSheet(SHEET_LEADS);
  sh.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight('bold').setBackground('#0f1a30').setFontColor('#ffffff');
  sh.setFrozenRows(1);
  sh.setColumnWidths(1, HEADERS.length, 140);
  var status = SpreadsheetApp.newDataValidation().requireValueInList(['New', 'Contacted', 'Call booked', 'Proposal', 'Won', 'Lost', 'Spam'], true).build();
  sh.getRange(2, 2, 2000, 1).setDataValidation(status);
  var st = ss.getSheetByName(SHEET_STATS) || ss.insertSheet(SHEET_STATS);
  st.clear();
  st.getRange('A1').setValue('Leads by month (excl. spam)').setFontWeight('bold');
  st.getRange('A2').setFormula('=QUERY(Leads!A:G,"select year(A), month(A)+1, count(G) where A is not null and B != \'Spam\' group by year(A), month(A)+1 label year(A) \'Year\', month(A)+1 \'Month\', count(G) \'Leads\'",1)');
  st.getRange('E1').setValue('Leads by first-touch source').setFontWeight('bold');
  st.getRange('E2').setFormula('=QUERY(Leads!A:Z,"select Z, count(G) where A is not null and B != \'Spam\' group by Z order by count(G) desc label Z \'First source\', count(G) \'Leads\'",1)');
  st.getRange('A30').setValue('By status').setFontWeight('bold');
  st.getRange('A31').setFormula('=QUERY(Leads!A:B,"select B, count(A) where A is not null group by B",1)');
  st.getRange('D30').setValue('By ICP fit').setFontWeight('bold');
  st.getRange('D31').setFormula('=QUERY(Leads!A:C,"select C, count(A) where A is not null group by C",1)');
}

function doGet() {
  return ContentService.createTextOutput(JSON.stringify({ ok: true, service: 'cra-leads' })).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
    var d = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (d.website) return ok_(); // honeypot
    if (!d.email && d.lead_type !== 'call_booked') return ok_();

    var ft = safeJson_(d.first_touch), lt = safeJson_(d.last_touch);
    var region = regionFromTz_(d.tz, d.country);
    var fit = icpFit_(d, region);
    var id = Utilities.getUuid().slice(0, 8);
    var status = looksLikeSpam_(d) ? 'Spam' : (d.lead_type === 'call_booked' ? 'Call booked' : 'New');

    var row = [
      new Date(), status, fit, region, d.form_name || '', d.lead_type || '', d.name || '', d.email || '', d.company || '', d.role || '', d.company_size || '',
      d.country || '', d.interest || '', d.message || '', d.score_total || '', d.score_dims || '', d.answers || '',
      d.page || '', lt.utm_source || '', lt.utm_medium || '', lt.utm_campaign || '', lt.utm_term || '', lt.utm_content || '', lt.gclid || ft.gclid || '', lt.li_fat_id || ft.li_fat_id || '',
      ft.utm_source || (ft.referrer && ft.referrer !== '(direct)' ? hostOf_(ft.referrer) : '(direct)'), ft.utm_medium || (ft.referrer && ft.referrer !== '(direct)' ? 'referral' : ''), ft.utm_campaign || '',
      ft.landing_page || '', ft.referrer || '', d.tz || '', d.lang || '', '', '', '', '', id
    ];
    var sh = SpreadsheetApp.getActive().getSheetByName(SHEET_LEADS);
    sh.appendRow(row.map(clean_));

    if (status !== 'Spam') notify_(d, fit, region, id, ft, lt);
    if (status !== 'Spam' && d.email && prop_('AUTO_REPLY') === 'yes') autoReply_(d);
    return ok_();
  } catch (err) {
    console.error(err);
    return ContentService.createTextOutput(JSON.stringify({ ok: false })).setMimeType(ContentService.MimeType.JSON);
  } finally {
    lock.releaseLock();
  }
}

/* ---------- scoring ---------- */
function icpFit_(d, region) {
  var s = 0;
  if (/50–200|200–500|500\+/.test(d.company_size || '')) s += 2;
  else if (/20–50/.test(d.company_size || '')) s += 1;
  if (region === 'EU/UK' || region === 'North America') s += 2;
  if (TARGET_COUNTRIES.test(d.country || '')) s += 1;
  if (/ceo|founder|owner|coo|cfo|cto|director|head|vp|managing|partner/i.test(d.role || '')) s += 2;
  if (d.company) s += 1;
  if (d.interest && d.interest !== 'Not sure yet') s += 1;
  if (Number(d.score_total) > 0 && Number(d.score_total) < 70) s += 1; // room to help
  return s >= 7 ? 'A' : s >= 4 ? 'B' : 'C';
}
function regionFromTz_(tz, country) {
  tz = tz || '';
  if (/^Europe\/(Kiev|Kyiv|Moscow|Minsk|Simferopol)/.test(tz)) return 'UA/CIS';
  if (/^Europe\//.test(tz) || /^Atlantic\/(Reykjavik|Canary|Madeira)/.test(tz)) return 'EU/UK';
  if (/^America\/(New_York|Chicago|Denver|Los_Angeles|Phoenix|Toronto|Vancouver|Detroit|Anchorage|Halifax|Edmonton|Winnipeg)/.test(tz)) return 'North America';
  if (/^America\//.test(tz)) return 'LatAm';
  if (/^Asia\/|^Australia\//.test(tz)) return 'APAC';
  return country ? 'Other' : 'Unknown';
}
function looksLikeSpam_(d) {
  var t = [d.name, d.message, d.company].join(' ');
  return /(seo services|backlinks|crypto|casino|viagra|guest post|rank your website)/i.test(t) || /https?:\/\//.test(d.name || '');
}

/* ---------- notifications ---------- */
function notify_(d, fit, region, id, ft, lt) {
  var src = (lt.utm_source || ft.utm_source || hostOf_(ft.referrer) || 'direct') + ' / ' + (lt.utm_medium || ft.utm_medium || '-');
  var title = '🟢 New lead [' + fit + '] ' + (d.name || '') + (d.company ? ' — ' + d.company : '');
  var body = [
    'Form: ' + (d.form_name || '') + ' (' + (d.lead_type || '') + ')',
    'Email: ' + (d.email || ''), 'Role: ' + (d.role || '-') + ' · Size: ' + (d.company_size || '-') + ' · Country: ' + (d.country || '-'),
    'Region (tz): ' + region + ' · Interest: ' + (d.interest || '-'),
    d.score_total ? 'Scorecard: ' + d.score_total + '/100 ' + (d.score_dims || '') : '',
    'Source: ' + src + (lt.utm_campaign ? ' · ' + lt.utm_campaign : ''), 'Landing: ' + (ft.landing_page || '-') + ' · Page: ' + (d.page || ''),
    d.message ? '\nMessage:\n' + d.message : '', '\nLead ID: ' + id + ' · ' + SpreadsheetApp.getActive().getUrl()
  ].filter(String).join('\n');
  var owner = prop_('OWNER_EMAIL');
  if (owner) MailApp.sendEmail({ to: owner, subject: title, body: body, replyTo: d.email || owner });
  var tok = prop_('TG_BOT_TOKEN'), chat = prop_('TG_CHAT_ID');
  if (tok && chat) {
    UrlFetchApp.fetch('https://api.telegram.org/bot' + tok + '/sendMessage', {
      method: 'post', contentType: 'application/json', muteHttpExceptions: true,
      payload: JSON.stringify({ chat_id: chat, text: title + '\n\n' + body, disable_web_page_preview: true })
    });
  }
}
function autoReply_(d) {
  var first = (d.name || '').split(' ')[0] || 'there';
  var isScore = d.lead_type === 'scorecard';
  var subject = isScore ? 'Your AI Readiness score: ' + d.score_total + '/100' : 'Thanks for reaching out';
  var text = 'Hi ' + first + ',\n\n' +
    (isScore ? 'Thanks for completing the AI Readiness Scorecard — your score is ' + d.score_total + '/100. I\'ll send your personal 90-day roadmap within two business days.\n\n'
             : 'Thanks for your message — I\'ll reply personally within one business day.\n\n') +
    'If you\'d like to talk sooner, pick a time here: https://calendly.com/ioa4/30min\n\nBest regards,\nOleg Ivanov\nFractional Chief Innovation Officer · croaccelerate.com';
  MailApp.sendEmail({ to: d.email, subject: subject, body: text, name: 'Oleg Ivanov' });
}

/* ---------- helpers ---------- */
function ok_() { return ContentService.createTextOutput(JSON.stringify({ ok: true })).setMimeType(ContentService.MimeType.JSON); }
function prop_(k) { return PropertiesService.getScriptProperties().getProperty(k); }
function safeJson_(s) { try { return JSON.parse(s || '{}') || {}; } catch (e) { return {}; } }
function hostOf_(u) { var m = String(u || '').match(/^https?:\/\/([^\/]+)/); return m ? m[1].replace(/^www\./, '') : ''; }
function clean_(v) { v = (v === null || v === undefined) ? '' : v; if (typeof v === 'string') { v = v.slice(0, 5000); if (/^[=+\-@]/.test(v)) v = "'" + v; } return v; }

/* Manual test from the editor: Run → testPost */
function testPost() {
  var e = { postData: { contents: JSON.stringify({ form_name: 'contact', lead_type: 'contact', name: 'Test Lead', email: 'test@example.com', company: 'Acme GmbH', role: 'CEO', company_size: '50–200', country: 'Germany', interest: 'AI Agents', message: 'Test', tz: 'Europe/Berlin', page: '/contact/', first_touch: JSON.stringify({ utm_source: 'linkedin', utm_medium: 'social', landing_page: '/blog/x/' }), last_touch: '{}' }) } };
  Logger.log(doPost(e).getContent());
}
