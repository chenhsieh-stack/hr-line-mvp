/* ============================================================
   HR 員工服務中心 — Google Apps Script 後端
   ============================================================ */

var ADMIN_USER = 'hr';
var ADMIN_PASS = 'HR-demo-2026!';

var STATUSES = ['新案件', '處理中', '待員工回覆', '已結案'];
var CATEGORIES = ['人事問題', '薪資福利', '出勤與請假', '制度查詢', '工作環境', '管理建議', '職場霸凌', '性騷擾', '不法侵害', '其他敏感事件', '其他'];
var SENSITIVE_CATEGORIES = ['職場霸凌', '性騷擾', '不法侵害', '其他敏感事件'];
var KINDS = {feedback: '意見反映', complaint: '安心申訴', human: '真人HR'};

var PAGE_MAP = {
  'home':       'Home',
  'faq':        'Faq',
  'form':       'Form',
  'my-cases':   'MyCases',
  'receipt':    'Receipt',
  'login':      'Login',
  'admin':      'Admin',
  'admin-case': 'AdminCase'
};

// ── Routing ──────────────────────────────────────────────────
function doGet(e) {
  var page = (e && e.parameter && e.parameter.page) ? e.parameter.page : 'home';
  var fileName = PAGE_MAP[page];
  if (!fileName) { page = 'home'; fileName = 'Home'; }

  try {
    var tmpl = HtmlService.createTemplateFromFile(fileName);
    tmpl.page = page;
    tmpl.baseUrl = ScriptApp.getService().getUrl();
    tmpl.params = e ? e.parameter : {};

    return tmpl.evaluate()
      .setTitle('HR 員工服務中心')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1')
      .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  } catch(err) {
    return HtmlService.createHtmlOutput('<h2>頁面錯誤</h2><p>' + err.message + '</p>')
      .setTitle('HR 員工服務中心');
  }
}

// ── Template helpers ─────────────────────────────────────────
function include(filename) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}

// ── SVG Icon helper ───────────────────────────────────────────
function icon_(name) {
  var paths = {
    person:  '<circle cx="12" cy="8" r="3.5"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/>',
    wallet:  '<path d="M4 6h15v14H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h13v2"/><path d="M19 11h-5v5h5"/><path d="M16 13.5h.1"/>',
    book:    '<path d="M12 5v16M3 4c4-1 6 0 9 1 3-1 5-2 9-1v15c-4-1-6 0-9 2-3-2-5-3-9-2Z"/>',
    message: '<path d="M21 12a9 9 0 0 1-9 9 10 10 0 0 1-4-1l-5 1 1-5a10 10 0 0 1-1-4 9 9 0 0 1 18 0Z"/><path d="M8 9h8M8 13h5"/>',
    shield:  '<path d="m12 2 8 4v6c0 5-5 8-8 10-3-2-8-5-8-10V6Z"/><path d="m8 12 3 3 5-6"/>',
    headset: '<path d="M4 14v-3a8 8 0 0 1 16 0v6c0 3-2 4-5 4"/><rect x="2" y="11" width="4" height="7" rx="2"/><rect x="18" y="11" width="4" height="7" rx="2"/><path d="M12 21h3"/>',
    folder:  '<path d="M3 6h7l2 3h9v12H3Z"/><path d="M3 6V3h7l2 3h8v3"/>',
    search:  '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    arrow:   '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    check:   '<path d="m5 12 4 4L19 6"/>',
    lock:    '<rect x="4" y="10" width="16" height="12" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 5v2"/>',
    home:    '<path d="m2 10 10-8 10 8M5 8v13h14V8M10 21v-7h4v7"/>',
    clock:   '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'
  };
  return '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (paths[name] || '') + '</svg>';
}

// ── Status helpers ────────────────────────────────────────────
function statusClass_(s) {
  if (s === '新案件')     return 'new';
  if (s === '處理中')     return 'working';
  if (s === '待員工回覆') return 'waiting';
  if (s === '已結案')     return 'closed';
  return 'new';
}

function displayTime_(v) {
  if (!v) return '—';
  try {
    var d = new Date(v);
    if (isNaN(d.getTime())) return String(v);
    var y = d.getFullYear();
    var m = ('0' + (d.getMonth()+1)).slice(-2);
    var dd = ('0' + d.getDate()).slice(-2);
    var hh = ('0' + d.getHours()).slice(-2);
    var mm = ('0' + d.getMinutes()).slice(-2);
    return y + '-' + m + '-' + dd + ' ' + hh + ':' + mm;
  } catch(e) { return String(v); }
}

// ── Sheet helpers ─────────────────────────────────────────────
function getSheetId_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('SHEET_ID');
  if (!id) {
    id = initSheets_();
    props.setProperty('SHEET_ID', id);
  }
  return id;
}

function getSpreadsheet_() {
  return SpreadsheetApp.openById(getSheetId_());
}

function initSheets_() {
  var ss = SpreadsheetApp.create('HR_Demo_Data');

  var casesSheet = ss.getActiveSheet();
  casesSheet.setName('cases');
  casesSheet.appendRow([
    'caseNumber','employeeId','name','organization','kind','category',
    'title','description','status','assignee','sensitive',
    'eventTime','location','people','evidence','evidenceNote',
    'createdAt','updatedAt','version'
  ]);

  var histSheet = ss.insertSheet('case_history');
  histSheet.appendRow(['caseNumber','actor','action','note','createdAt']);

  return ss.getId();
}

function getCasesSheet_() {
  return getSpreadsheet_().getSheetByName('cases');
}

function getHistorySheet_() {
  return getSpreadsheet_().getSheetByName('case_history');
}

// ── Case number generator ─────────────────────────────────────
function generateCaseNumber_() {
  var now = new Date();
  var y = now.getFullYear();
  var m = ('0' + (now.getMonth()+1)).slice(-2);
  var d = ('0' + now.getDate()).slice(-2);
  var rand = ('000' + Math.floor(Math.random() * 9000 + 1000)).slice(-4);
  return 'HR-' + y + m + d + '-' + rand;
}

// ── FAQ data ──────────────────────────────────────────────────
var FAQ_DATA = [
  {id:'attendance',category:'人事問題',question:'出勤或排班紀錄有疑問，如何處理？',answer:'請先確認公司出勤紀錄與當期排班表。如有漏打卡、班別或出勤紀錄差異，請依公司現行補登流程申請；個人或特殊情況可透過「真人HR」提交案件。',keywords:['出勤','排班','打卡','補登']},
  {id:'leave',category:'人事問題',question:'如何申請請假？',answer:'請依公司現行請假制度完成申請及主管核准。病假、事假、家庭照顧假、婚假、喪假等假別的文件與流程，請向主管或 HR 確認。這份示範 FAQ 尚未連接公司的請假系統。',keywords:['請假','病假','事假','家庭照顧假','婚假','喪假']},
  {id:'annual-leave',category:'人事問題',question:'如何查詢特休與剩餘天數？',answer:'特別休假依適用法令、到職年資及公司規定辦理。個人剩餘天數請至公司指定的人事系統查詢；系統名稱待公司確認。如紀錄有疑問，請透過「真人HR」協助核對。',keywords:['特休','年假','剩餘天數']},
  {id:'onboarding',category:'人事問題',question:'到職、離職與人事資料異動要找誰？',answer:'報到文件、離職交接與姓名、聯絡方式等資料異動，請依公司人事流程辦理。若不確定承辦窗口，請透過「真人HR」說明需求，並提供員工編號及品牌／單位／門市。',keywords:['到職','離職','報到','資料異動','交接']},
  {id:'salary',category:'薪資福利',question:'薪資、加班費或扣款有疑問怎麼辦？',answer:'請先確認當期薪資明細與出勤資料。如涉及入帳、加班費、扣款或個人薪資差異，請透過「真人HR」提交問題，由 HR 人工核對。請勿在一般聊天留言提供帳戶密碼或完整金融資料。',keywords:['薪資','薪水','加班費','扣款','入帳']},
  {id:'insurance',category:'薪資福利',question:'如何詢問勞健保、眷屬依附或勞退？',answer:'勞保、健保、勞退及眷屬依附等個別事項，請由 HR 依到職、離職與資料異動情形確認。如需查詢個人加退保或異動進度，請透過「真人HR」提交案件。',keywords:['勞健保','勞保','健保','勞退','眷屬']},
  {id:'benefits',category:'薪資福利',question:'有哪些員工福利與獎金？',answer:'福利項目、資格、申請方式與獎金條件，請以公司最新公告為準。這是固定資料示範，未設定特定金額或福利承諾；正式上線前請由 HR 更新為公司核定內容。',keywords:['福利','獎金','補助','員工優惠']},
  {id:'policies',category:'制度查詢',question:'在哪裡查詢最新公司制度？',answer:'請以公司核定的公告、工作規則與制度文件為準。此 MVP 尚未串接內部文件庫；找不到文件或需要釐清適用範圍時，可透過「真人HR」提出需求。',keywords:['制度','公告','工作規則','規章','文件']},
  {id:'feedback',category:'制度查詢',question:'工作環境或管理建議可以如何反映？',answer:'一般工作環境、管理方式與制度建議可使用「意見反映」表單。涉及職場霸凌、性騷擾、不法侵害或其他敏感事件時，請使用「安心申訴」，由 HR 人工受理。',keywords:['意見','反映','工作環境','建議']},
  {id:'complaint',category:'制度查詢',question:'安心申訴如何處理？',answer:'表單會記錄事件資訊並產生案件編號，供 HR 人工受理與後續聯繫。系統不判定事件是否成立。請依實際情況填寫；如有立即人身安全疑慮，請優先尋求現場緊急協助。',keywords:['申訴','霸凌','性騷擾','不法侵害','敏感','人工處理']},
  {id:'tracking',category:'制度查詢',question:'送出後如何查看案件進度？',answer:'前往「我的案件」輸入送件時的員工編號，即可查看案件編號、類型與處理狀態。本機版僅供測試，員工編號尚未完成身分驗證；正式上線需改用經驗證的員工帳號。',keywords:['進度','案件','狀態','查詢']}
];

// ── Server functions ──────────────────────────────────────────

function searchFaqs(keyword, category) {
  var results = FAQ_DATA;
  if (category && category !== '全部') {
    results = results.filter(function(f){ return f.category === category; });
  }
  if (keyword && keyword.trim()) {
    var kw = keyword.trim().toLowerCase();
    results = results.filter(function(f){
      return f.question.toLowerCase().indexOf(kw) >= 0 ||
             f.answer.toLowerCase().indexOf(kw) >= 0 ||
             f.keywords.some(function(k){ return k.toLowerCase().indexOf(kw) >= 0; });
    });
  }
  return results;
}

function submitCase(data) {
  try {
    var sheet = getCasesSheet_();
    var caseNumber = generateCaseNumber_();
    var now = new Date().toISOString();
    var sensitive = SENSITIVE_CATEGORIES.indexOf(data.category) >= 0 ? '1' : '0';
    var kind = data.kind || 'feedback';

    sheet.appendRow([
      caseNumber,
      data.employeeId || '',
      data.name || '',
      data.organization || '',
      kind,
      data.category || '',
      data.title || '',
      data.description || '',
      '新案件',
      '',
      sensitive,
      data.eventTime || '',
      data.location || '',
      data.people || '',
      data.evidence || '',
      data.evidenceNote || '',
      now,
      now,
      '1'
    ]);

    var histSheet = getHistorySheet_();
    histSheet.appendRow([caseNumber, data.name || '員工', '提交案件', '', now]);

    return {ok: true, caseNumber: caseNumber, kind: kind, sensitive: sensitive};
  } catch(e) {
    return {ok: false, error: e.message};
  }
}

function getMyCases(employeeId) {
  try {
    if (!employeeId) return {ok: false, error: '請輸入員工編號'};
    var sheet = getCasesSheet_();
    var data = sheet.getDataRange().getValues();
    var headers = data[0];
    var results = [];
    for (var i = 1; i < data.length; i++) {
      var row = data[i];
      var obj = {};
      headers.forEach(function(h, idx){ obj[h] = row[idx]; });
      if (String(obj.employeeId) === String(employeeId)) {
        results.push(obj);
      }
    }
    results.sort(function(a,b){ return new Date(b.createdAt) - new Date(a.createdAt); });
    return {ok: true, cases: results};
  } catch(e) {
    return {ok: false, error: e.message};
  }
}

function adminLogin(username, password) {
  if (username === ADMIN_USER && password === ADMIN_PASS) {
    var token = Utilities.getUuid();
    CacheService.getScriptCache().put('admin_token_' + token, '1', 28800);
    return {ok: true, token: token};
  }
  return {ok: false, error: '帳號或密碼錯誤'};
}

function verifyAdminToken(token) {
  if (!token) return false;
  var val = CacheService.getScriptCache().get('admin_token_' + token);
  return val === '1';
}

function getAllCases(token, filters) {
  if (!verifyAdminToken(token)) return {ok: false, error: '請重新登入'};
  try {
    filters = filters || {};
    var sheet = getCasesSheet_();
    var data = sheet.getDataRange().getValues();
    var headers = data[0];
    var rows = [];
    for (var i = 1; i < data.length; i++) {
      var row = data[i];
      var obj = {};
      headers.forEach(function(h, idx){ obj[h] = row[idx]; });
      rows.push(obj);
    }

    var stats = {'新案件': 0, '處理中': 0, '待員工回覆': 0, '已結案': 0};
    rows.forEach(function(r){
      if (stats[r.status] !== undefined) stats[r.status]++;
    });

    if (filters.status) rows = rows.filter(function(r){ return r.status === filters.status; });
    if (filters.category) rows = rows.filter(function(r){ return r.category === filters.category; });
    if (filters.q) {
      var q = filters.q.toLowerCase();
      rows = rows.filter(function(r){
        return String(r.caseNumber).toLowerCase().indexOf(q) >= 0 ||
               String(r.name).toLowerCase().indexOf(q) >= 0 ||
               String(r.employeeId).toLowerCase().indexOf(q) >= 0 ||
               String(r.title).toLowerCase().indexOf(q) >= 0 ||
               String(r.organization).toLowerCase().indexOf(q) >= 0;
      });
    }

    rows.sort(function(a,b){ return new Date(b.createdAt) - new Date(a.createdAt); });

    var pageSize = 20;
    var pageNum = parseInt(filters.page) || 1;
    var total = rows.length;
    var totalPages = Math.max(1, Math.ceil(total / pageSize));
    var start = (pageNum - 1) * pageSize;
    var paged = rows.slice(start, start + pageSize);

    return {ok: true, cases: paged, stats: stats, total: total, page: pageNum, totalPages: totalPages};
  } catch(e) {
    return {ok: false, error: e.message};
  }
}

function getCaseDetail(token, caseNumber) {
  if (!verifyAdminToken(token)) return {ok: false, error: '請重新登入'};
  try {
    var sheet = getCasesSheet_();
    var data = sheet.getDataRange().getValues();
    var headers = data[0];
    var caseObj = null;
    for (var i = 1; i < data.length; i++) {
      var row = data[i];
      var obj = {};
      headers.forEach(function(h, idx){ obj[h] = row[idx]; });
      if (obj.caseNumber === caseNumber) { caseObj = obj; break; }
    }
    if (!caseObj) return {ok: false, error: '案件不存在'};

    var histSheet = getHistorySheet_();
    var histData = histSheet.getDataRange().getValues();
    var histHeaders = histData[0];
    var history = [];
    for (var j = 1; j < histData.length; j++) {
      var hrow = histData[j];
      var hobj = {};
      histHeaders.forEach(function(h, idx){ hobj[h] = hrow[idx]; });
      if (hobj.caseNumber === caseNumber) history.push(hobj);
    }
    history.sort(function(a,b){ return new Date(b.createdAt) - new Date(a.createdAt); });

    return {ok: true, case: caseObj, history: history};
  } catch(e) {
    return {ok: false, error: e.message};
  }
}

function updateCase(token, caseNumber, updateData) {
  if (!verifyAdminToken(token)) return {ok: false, error: '請重新登入'};
  try {
    var sheet = getCasesSheet_();
    var data = sheet.getDataRange().getValues();
    var headers = data[0];
    var rowIndex = -1;
    var oldObj = null;
    for (var i = 1; i < data.length; i++) {
      var row = data[i];
      var obj = {};
      headers.forEach(function(h, idx){ obj[h] = row[idx]; });
      if (obj.caseNumber === caseNumber) { rowIndex = i + 1; oldObj = obj; break; }
    }
    if (rowIndex < 0) return {ok: false, error: '案件不存在'};

    var now = new Date().toISOString();
    var colMap = {};
    headers.forEach(function(h, idx){ colMap[h] = idx + 1; });

    if (updateData.status)   sheet.getRange(rowIndex, colMap['status']).setValue(updateData.status);
    if (updateData.assignee !== undefined) sheet.getRange(rowIndex, colMap['assignee']).setValue(updateData.assignee);
    if (updateData.category) sheet.getRange(rowIndex, colMap['category']).setValue(updateData.category);
    sheet.getRange(rowIndex, colMap['updatedAt']).setValue(now);
    var ver = parseInt(oldObj.version || 1) + 1;
    sheet.getRange(rowIndex, colMap['version']).setValue(String(ver));

    if (updateData.note || updateData.status) {
      var histSheet = getHistorySheet_();
      var action = updateData.status ? ('狀態更新為「' + updateData.status + '」') : '備註';
      histSheet.appendRow([caseNumber, 'HR', action, updateData.note || '', now]);
    }

    return {ok: true};
  } catch(e) {
    return {ok: false, error: e.message};
  }
}
