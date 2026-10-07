# 公司內部 HR LINE 員工服務中心

可在本機執行的繁體中文 MVP。採用 **Flask + SQLite + Jinja + 原生 CSS／JavaScript**，不需要 Node.js、前端編譯工具或外部資料庫。介面支援手機、平板與桌面，後續可嵌入 LINE LIFF。

這版供本機功能測試。請使用虛構測試資料；**員工編號只是查詢條件，不是身分驗證**。正式開放員工使用前，需要補上經驗證的員工登入／帳號綁定與 HR 存取權限。所有敏感案件均標示「人工處理」，專案沒有 AI 模型、成立與否判定或自動裁決。

## 本機啟動

需要 Python 3.9 以上與可下載套件的網路。維護或部署新環境建議使用仍受支援的 Python 版本。以下指令在解壓後的 `hr-line-mvp` 專案資料夾內執行。

### macOS / Linux

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

啟動後打開：

- 員工首頁：[http://127.0.0.1:8000](http://127.0.0.1:8000)
- HR 後台：[http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)
- 健康檢查：[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

本機預設 HR 帳號為 `hr`，密碼為 `HR-demo-2026!`。服務使用 Waitress，預設只監聽 `127.0.0.1:8000`，不開啟除錯控制台。按 `Ctrl+C` 停止；下次在同一資料夾執行 `python run.py` 即可，案件會保留。

若連接埠被占用，在 `.env` 設定 `PORT=8001` 後重新啟動。一般 HTTP 本機測試請保持 `COOKIE_SECURE=false`，否則瀏覽器可能不送出登入 cookie。

## 五分鐘操作驗收

1. 首頁六個入口：「人事問題」、「薪資福利」、「制度查詢」、「意見反映」、「安心申訴」、「真人HR」。前三項進入對應的 FAQ 分類。
2. 在常見問題搜尋「特休」或「薪資」，確認顯示固定答案；沒有結果時可轉真人HR。
3. 使用「意見反映」或「安心申訴」，填寫虛構姓名、員編 `DEMO001`、單位與事件／需求內容，勾選資料使用說明後送出。
4. 系統顯示案件編號，例如 `HR-20261007-001`。日期取台灣時間，每日流水號從 001 開始，可超過三位數。
5. 登入 HR 後台，點選案件，查看內容、變更分類、輸入承辦人、將狀態改為「處理中」，儲存。
6. 登出 HR，前往「我的案件」輸入 `DEMO001`，確認狀態已更新。
7. HR 可繼續將案件改為「待員工回覆」或「已結案」。所有更新都會保留操作者、時間、分類／承辦／狀態變更與內部備註。

「真人HR」是人工協助案件表單，並非即時聊天；「待員工回覆」目前需由 HR 另行聯繫，未包含自動通知與員工補件介面。

## 功能與資料

| 功能 | 本版行為 |
| --- | --- |
| FAQ | 11 則固定資料；全文／關鍵字搜尋、分類篩選；沒有 AI 生成答案 |
| 意見反映 | 姓名、員編、品牌／單位／門市、分類、主旨、詳細內容 |
| 安心申訴 | 另含事件時間、地點、涉及人員、事件經過、是否有佐證、佐證說明 |
| 案件編號 | SQLite transaction 原子配置；同時送件不撞號；同一張表單重送不重複建案 |
| 我的案件 | 用員編查詢；只回傳編號、類型、狀態、人工標記與送件／更新時間 |
| HR 後台 | 登入、列表、統計、搜尋、狀態／分類篩選、每頁 20 件、詳情、分類、指派、四種狀態、紀錄 |
| 多人更新 | 使用版本欄位，過期更新回傳 409，避免覆蓋其他人的變更 |
| 敏感案件 | 申訴及敏感分類會永久保留人工處理標記；改分類也不會解除 |
| LINE 選用接口 | LIFF 初始化與顯示名稱；Webhook 驗簽、固定 FAQ／表單導流回覆與事件去重 |

事件時間欄位以台灣時間填寫；若是約略時間，在事件經過說明即可。此版只記錄「是否有佐證」與文字描述，**沒有檔案上傳**，由 HR 另行提供指定管道。FAQ 內容是示範資料，沒有虛構公司薪資、休假天數或福利承諾，使用前請由 HR 核定。

### 檔案結構

```text
hr-line-mvp/
├── run.py                 # 讀取 .env、啟動 Waitress
├── requirements.txt       # Flask、Waitress
├── .env.example           # 設定範本，不含真實金鑰
├── hr_app/
│   ├── __init__.py         # 路由、驗證、HR 登入與案件處理
│   ├── db.py               # SQLite schema、編號、交易
│   ├── line.py             # 選用 Messaging API Webhook
│   ├── faqs.json           # 固定 FAQ，修改後重新啟動
│   ├── templates/          # 繁體中文畫面
│   └── static/             # CSS、JavaScript、路易莎品牌 Logo
├── tests/test_app.py       # 核心流程與安全邊界測試
└── instance/              # 首次啟動自動建立，不納入版本管理
    ├── hr.sqlite3         # 案件、處理歷史與 Webhook 去重 ID
    └── local-secret       # 未指定 SECRET_KEY 時產生的本機 session 金鑰
```

SQLite 啟用外鍵與 WAL。存放於本機的資料庫未加密。備份請使用 SQLite backup API 或在停止服務後複製資料庫與相關檔案；WAL 使用中不要只複製單一 `.sqlite3` 檔。跨主機或較高流量時，將資料層改為 PostgreSQL，新增正式 migration 與集中式工作佇列。

## 設定

將 `.env.example` 複製為 `.env`。`run.py` 自動讀取；部署平台提供的既有環境變數優先。更新後需重新啟動。不要把 `.env`、`instance/` 或資料庫提交到版本庫。

| 變數 | 用途 |
| --- | --- |
| `HOST` / `PORT` | 預設 `127.0.0.1` / `8000` |
| `ADMIN_USERNAME` | 本機單一 HR 管理者帳號 |
| `ADMIN_PASSWORD` | HR 密碼；未設定時使用本機示範密碼 |
| `ADMIN_PASSWORD_HASH` | 可選，優先採用 Werkzeug 密碼雜湊 |
| `SECRET_KEY` | 固定 session 簽章金鑰；未設定則保留自動產生的本機檔案 |
| `DATABASE_PATH` | SQLite 檔案位置；正式服務需持久化磁碟 |
| `COOKIE_SECURE` | HTTPS 下設為 `true`，本機 HTTP 維持 `false` |
| `LINE_LIFF_ID` | 不填則完全不載入 LINE SDK |
| `LINE_CHANNEL_SECRET` | Messaging API Channel Secret，只存於後端 |
| `LINE_CHANNEL_ACCESS_TOKEN` | Messaging API 回覆所需 Token，只存於後端 |
| `PUBLIC_APP_URL` | 對外 HTTPS 網址，供 LINE 回覆連結；不接受 HTTP |

若需要產生密碼雜湊，在虛擬環境內執行以下指令，輸入密碼後將結果填入 `.env` 的 `ADMIN_PASSWORD_HASH`：

```sh
python -c 'import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass.getpass("HR 密碼："), method="pbkdf2:sha256:1000000"))'
```

本機版已提供 CSRF、防止 HTML 注入的模板跳脫、參數化 SQL、HttpOnly／SameSite cookie、登入嘗試限制（每 IP 每 5 分鐘最多 5 次，單一程序記憶體）、內容大小上限與快取禁止。這些功能不能取代員工身分驗證與正式 HR 權限控管。

## 未來串接 LINE LIFF

1. 在 [LINE Developers Console](https://developers.line.biz/console/) 建立 LINE Login Channel，加入 LIFF App。將 App Endpoint URL 設成部署後的 HTTPS 根網址，例如 `https://hr.example.com/`，各功能路徑維持在此網址之下。
2. 若需要顯示名稱，選用 `profile`；若要在後端驗證 ID token，加入 `openid`。在 `.env` 填入 `LINE_LIFF_ID`，重新啟動。
3. `static/app.js` 已會選用載入官方 LIFF SDK、呼叫 `liff.init`，登入後用 `getProfile` 顯示名稱。外部瀏覽器未登入時，提供「登入 LINE」按鈕；每個新頁面都重新初始化。沒有 LIFF 設定時本機流程照常運作。
4. **本版不將 LINE displayName、前端 userId 或自行輸入的員編當成已驗證身分。** 正式加入登入時，前端用 `liff.getIDToken()` 取得原始 ID token，透過 HTTPS POST 送到新增的後端登入端點；後端呼叫 LINE 的 `POST https://api.line.me/oauth2/v2.1/verify`，使用正確 LINE Login Channel ID 驗證 token，取得可信 `sub`。
5. 由公司核准的 SSO、一次性驗證或 HR 管理流程將可信 LINE `sub` 綁定員工帳號。送件時從伺服器 session 填入員編，查詢時只使用登入者的帳號，並移除任意員編查詢入口。LINE 登入本身不代表在職員工資格。
6. 官方帳號圖文選單可指向 LIFF URL，例如 `https://liff.line.me/{LIFF_ID}`，或依官方永久連結方式開啟指定表單。

本版 LIFF 初始化是選用接口，**尚未使用實際 LINE Channel 實測，也沒有 token 驗證／員工綁定登入端點**。正式測試需在測試 Channel 與受限測試環境進行。

官方依據：[LIFF 開發與初始化](https://developers.line.biz/en/docs/liff/developing-liff-apps/)、[LIFF API](https://developers.line.biz/en/reference/liff/)、[安全地在伺服器使用 LINE 使用者資料](https://developers.line.biz/en/docs/liff/using-user-profile/)。

## 未來串接 Messaging API / Webhook

專案包含 `POST /api/line/webhook`，但不設定 Channel 資訊時保持未啟用。

1. 為公司 LINE 官方帳號啟用 Messaging API。將 `LINE_CHANNEL_SECRET` 與 `LINE_CHANNEL_ACCESS_TOKEN` 填入後端環境變數；兩者不會傳到前端。
2. 設定 `PUBLIC_APP_URL=https://你的測試網址`。在 Messaging API 設定中填入 Webhook URL：`https://你的測試網址/api/line/webhook`。
3. 開啟 Webhook，先執行 Console 的 Verify。官方空 `events` 驗證請求在簽章正確時回傳 200。若使用本程式回覆 FAQ，請檢查官方帳號的自動回應設定，避免重複回覆。
4. Webhook 使用**未修改的原始 HTTP body**，以 Channel Secret 計算 HMAC-SHA256，再比對 Base64 `X-Line-Signature`。驗簽失敗時回傳 401，之後才解析 JSON。
5. 文字事件可回覆固定 FAQ，或「意見反映」「安心申訴」「真人HR」等表單連結。包含敏感關鍵字時只導向人工申訴流程，不會自動建案或判定事件成立。
6. 使用 `webhookEventId` 去重，不儲存完整 Webhook 訊息、使用者 profile 或 reply token。API 回覆失敗回傳 502，並保留重試可能性；沒有回覆 token 設定時文字事件回傳 503，避免誤以為已成功回覆。

此 MVP 使用同步回覆與 SQLite transaction，只適合少量測試。正式服務依 [LINE 官方接收 Webhook 建議](https://developers.line.biz/en/docs/messaging-api/receiving-messages/) 改用背景佇列：驗簽 → 去重與持久化工作 → 回傳 200 → worker 回覆，並設計 reply token 有效期、失敗重試與通知策略。外部 API 成功後程序若在資料庫提交前中斷，本版無法保證端到端恰好一次送達；需用 outbox／送達紀錄改善。

官方依據：[Webhook 簽章驗證](https://developers.line.biz/en/docs/messaging-api/verify-webhook-signature/)、[Messaging API 參考](https://developers.line.biz/en/reference/messaging-api/)。目前自動測試以模擬 API 驗證，沒有向真實 LINE 帳號發送訊息。

## 正式部署前要完成的事項

- 員工登入／LINE token 驗證與員編綁定，讓案件只對已驗證的本人開放。送件資料也需由伺服器綁定真實帳號。
- HR 改用個人管理者帳號、角色與敏感案件授權；目前為單一管理者，可看全部案件。
- 公司核定 FAQ、受理窗口、聯繫方式、申訴處理程序、資料保存期限與刪除／備份流程。
- HTTPS、正式密碼與固定 `SECRET_KEY`、`COOKIE_SECURE=true`、環境機密管理、資料庫／備份加密及持久化磁碟。
- 公開入口的限流／濫用防護、集中式登入限制、權限稽核、通知與非同步 Webhook 處理。

完成這些項目後，可由單台應用主機用 Waitress 執行，前面放 HTTPS 反向代理，SQLite 置於持久化磁碟；不要在無持久磁碟的短期容器直接存案件。多實例部署請改 PostgreSQL 與集中式 session／佇列。本次不包含公開部署、真實員工資料匯入或 LINE 憑證設定。

## 測試

在虛擬環境執行，不需要額外測試套件：

```sh
python -m unittest discover -s tests -v
```

22 項測試涵蓋首頁與主要頁面、FAQ 搜尋、收件／持久化、重送去重、同時建案不撞號、申訴欄位／人工標記、伺服器驗證、CSRF、員編查詢資料最小化、HR 登入／登出、四種狀態／分類／指派／處理紀錄、過期更新衝突、HTML 注入、搜尋參數化、登入嘗試限制、Webhook 驗簽／固定回覆／去重／失敗重試與回應安全標頭。測試使用獨立暫存資料庫，不會污染本機案件。

本次也完成瀏覽器人工流程驗證：虛構申訴送件 → 顯示案件編號 → HR 登入／指派／改為處理中 → 登出 → 員工編號查到更新狀態。LINE 實際 Channel 與正式員工身分驗證仍待串接。
