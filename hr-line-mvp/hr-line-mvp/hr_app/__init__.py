import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .line import line_bp

STATUSES = ("新案件", "處理中", "待員工回覆", "已結案")
CATEGORIES = ("人事問題", "薪資福利", "出勤與請假", "制度查詢", "工作環境", "管理建議", "職場霸凌", "性騷擾", "不法侵害", "其他敏感事件", "其他")
SENSITIVE_CATEGORIES = frozenset(("職場霸凌", "性騷擾", "不法侵害", "其他敏感事件"))
KINDS = {"feedback": "意見反映", "complaint": "安心申訴", "human": "真人HR"}
EMPLOYEE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")


def create_app(test_config=None):
    root = Path(__file__).resolve().parent.parent
    app = Flask(__name__, instance_path=str(root / "instance"))
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or None,
        DATABASE=os.environ.get("DATABASE_PATH") or str(root / "instance" / "hr.sqlite3"),
        ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME", "hr"),
        ADMIN_PASSWORD_HASH=os.environ.get("ADMIN_PASSWORD_HASH") or None,
        DEMO_PASSWORD=not bool(os.environ.get("ADMIN_PASSWORD_HASH")) and os.environ.get("ADMIN_PASSWORD", "HR-demo-2026!") == "HR-demo-2026!",
        MAX_CONTENT_LENGTH=256 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        LINE_LIFF_ID=os.environ.get("LINE_LIFF_ID", ""),
        LINE_CHANNEL_SECRET=os.environ.get("LINE_CHANNEL_SECRET", ""),
        LINE_CHANNEL_ACCESS_TOKEN=os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", ""),
        PUBLIC_APP_URL=os.environ.get("PUBLIC_APP_URL", "").rstrip("/"),
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["ADMIN_PASSWORD_HASH"]:
        # 部分 macOS 內建 Python 沒有 hashlib.scrypt，採可攜的 PBKDF2。
        app.config["ADMIN_PASSWORD_HASH"] = generate_password_hash(
            os.environ.get("ADMIN_PASSWORD") or "HR-demo-2026!", method="pbkdf2:sha256:1000000")
    Path(app.instance_path).mkdir(parents=True, exist_ok=True, mode=0o700)
    if not app.config["SECRET_KEY"]:
        secret_path = Path(app.instance_path) / "local-secret"
        try:
            with secret_path.open("x", encoding="utf-8") as file:
                file.write(secrets.token_hex(32))
            secret_path.chmod(0o600)
        except FileExistsError:
            pass
        app.config["SECRET_KEY"] = secret_path.read_text(encoding="utf-8").strip()
    database_path = Path(app.config["DATABASE"])
    database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if app.config["PUBLIC_APP_URL"] and not app.config["PUBLIC_APP_URL"].startswith("https://"):
        raise ValueError("PUBLIC_APP_URL 必須使用 https://")
    with (Path(__file__).parent / "faqs.json").open(encoding="utf-8") as file:
        app.config["FAQS"] = json.load(file)

    def search_faqs(keyword="", category=""):
        words = keyword.casefold().split()
        return [item for item in app.config["FAQS"]
                if (not category or item["category"] == category)
                and all(word in (item["question"] + item["answer"] + " ".join(item["keywords"])).casefold() for word in words)]

    app.config["SEARCH_FAQS"] = search_faqs
    app.teardown_appcontext(db.close_db)
    with app.app_context():
        db.init_db()
    database_path.chmod(0o600)
    app.register_blueprint(line_bp)
    login_attempts = defaultdict(deque)
    login_lock = threading.Lock()

    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("admin"):
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped

    @app.before_request
    def csrf_protection():
        if request.method == "POST" and request.endpoint != "line.webhook":
            expected, supplied = session.get("csrf"), request.form.get("csrf_token", "")
            if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
                abort(400, description="表單已過期或驗證失敗，請重新開啟頁面後再試。")

    @app.after_request
    def secure_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://static.line-scdn.net; "
            "style-src 'self'; img-src 'self' data:; "
            "connect-src 'self' https://*.line.me https://*.line.biz https://*.line-scdn.net; "
            "frame-src https://access.line.me; frame-ancestors 'self'; base-uri 'self'; form-action 'self'")
        return response

    @app.context_processor
    def common_context():
        return dict(csrf_token=csrf_token, statuses=STATUSES, categories=CATEGORIES, kinds=KINDS,
                    is_admin=bool(session.get("admin")), liff_id=app.config["LINE_LIFF_ID"])

    @app.template_filter("display_time")
    def display_time(value):
        return value[:16].replace("T", " ") if value else "—"

    @app.template_filter("status_class")
    def status_class(value):
        return {"新案件": "new", "處理中": "working", "待員工回覆": "waiting", "已結案": "closed"}.get(value, "new")

    @app.get("/")
    def home():
        return render_template("home.html", page="home")

    @app.get("/faq")
    def faq():
        query = request.args.get("q", "").strip()[:120]
        category = request.args.get("category", "")
        if category not in ("", "人事問題", "薪資福利", "制度查詢"):
            category = ""
        return render_template("faq.html", page="faq", query=query, category=category, faqs=search_faqs(query, category))

    def form_values(kind):
        fields = {"name": (60, "姓名"), "employee_id": (40, "員工編號"), "organization": (120, "品牌／單位／門市"),
                  "title": (120, "主旨"), "description": (6000, "內容"), "category": (40, "分類"),
                  "event_time": (16, "事件時間"), "location": (200, "事件地點"), "people": (300, "涉及人員"),
                  "evidence": (20, "是否有佐證資料"), "evidence_note": (1000, "佐證資料說明")}
        values = {key: request.form.get(key, "").strip() for key in fields}
        errors = {}
        required = {"name", "employee_id", "organization", "title", "description", "category"}
        if kind == "complaint":
            required.update(("event_time", "location", "people", "evidence"))
        for key, (limit, label) in fields.items():
            if key in required and not values[key]:
                errors[key] = "請填寫{}。".format(label)
            elif len(values[key]) > limit:
                errors[key] = "{}最多 {} 個字。".format(label, limit)
        if values["employee_id"] and not EMPLOYEE_RE.fullmatch(values["employee_id"]):
            errors["employee_id"] = "員工編號請使用英文字母、數字、底線或連字號，最多 40 字。"
        values["employee_id"] = values["employee_id"].upper()
        allowed = SENSITIVE_CATEGORIES if kind == "complaint" else set(CATEGORIES)
        if values["category"] not in allowed:
            errors["category"] = "請選擇有效分類。"
        if kind == "complaint":
            if values["evidence"] not in ("有", "無", "尚不確定"):
                errors["evidence"] = "請選擇是否有佐證資料。"
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", values["event_time"]):
                    raise ValueError()
                datetime.fromisoformat(values["event_time"])
            except ValueError:
                errors["event_time"] = "請輸入有效的事件日期與時間。"
        else:
            for field in ("event_time", "location", "people", "evidence", "evidence_note"):
                values[field] = ""
        if request.form.get("consent") != "yes":
            errors["consent"] = "送出前請確認資料使用說明。"
        values["kind"] = kind
        values["sensitive"] = int(kind == "complaint" or values["category"] in SENSITIVE_CATEGORIES)
        return values, errors

    @app.route("/forms/<kind>", methods=["GET", "POST"])
    def case_form(kind):
        if kind not in KINDS:
            abort(404)
        values, errors = {}, {}
        if request.method == "POST":
            token = request.form.get("submission_token", "")
            if token not in session.get("form_tokens", []):
                abort(400, description="送件表單已過期，請重新開啟表單。")
            values, errors = form_values(kind)
            if not errors:
                case = db.insert_case(values, token)
                session["receipt"] = {"number": case["case_number"], "kind": case["kind"], "sensitive": bool(case["sensitive"])}
                return redirect(url_for("receipt"), code=303)
        else:
            token = secrets.token_urlsafe(32)
            session["form_tokens"] = (session.get("form_tokens", []) + [token])[-12:]
        options = [c for c in CATEGORIES if c in SENSITIVE_CATEGORIES] if kind == "complaint" else CATEGORIES
        return render_template("form.html", page="form", kind=kind, values=values, errors=errors,
                               form_categories=options, submission_token=token), (422 if errors else 200)

    @app.get("/receipt")
    def receipt():
        if not session.get("receipt"):
            return redirect(url_for("home"))
        return render_template("receipt.html", page="cases", receipt=session["receipt"])

    @app.route("/my-cases", methods=["GET", "POST"])
    def my_cases():
        cases, error, employee_id = None, "", ""
        if request.method == "POST":
            employee_id = request.form.get("employee_id", "").strip().upper()
            if not EMPLOYEE_RE.fullmatch(employee_id):
                error = "請輸入有效的員工編號（英文字母、數字、底線或連字號）。"
            else:
                # 員編查詢僅供本機測試；刻意不返回姓名、事件內容、HR 備註或涉及人員。
                cases = db.get_db().execute("SELECT case_number, kind, status, sensitive, created_at, updated_at FROM cases WHERE employee_id = ? ORDER BY id DESC", (employee_id,)).fetchall()
        return render_template("my_cases.html", page="cases", cases=cases, error=error, employee_id=employee_id), (422 if error else 200)

    @app.route("/admin/login", methods=["GET", "POST"])
    def login():
        if session.get("admin"):
            return redirect(url_for("admin"))
        error, status = "", 200
        if request.method == "POST":
            address = request.remote_addr or "local"
            stamp = time.monotonic()
            with login_lock:
                attempts = login_attempts[address]
                while attempts and attempts[0] < stamp - 300:
                    attempts.popleft()
                blocked = len(attempts) >= 5
                if not blocked:
                    attempts.append(stamp)
            if blocked:
                error, status = "嘗試次數過多，請於 5 分鐘後再試。", 429
            elif (hmac.compare_digest(request.form.get("username", "").encode(), app.config["ADMIN_USERNAME"].encode())
                  and check_password_hash(app.config["ADMIN_PASSWORD_HASH"], request.form.get("password", "")[:1000])):
                with login_lock:
                    login_attempts.pop(address, None)
                session.clear()
                session["admin"] = app.config["ADMIN_USERNAME"]
                session.permanent = True
                return redirect(url_for("admin"), code=303)
            else:
                error, status = "帳號或密碼不正確。", 401
        return render_template("login.html", page="admin", error=error, demo_password=app.config["DEMO_PASSWORD"], admin_username=app.config["ADMIN_USERNAME"]), status

    @app.post("/admin/logout")
    @admin_required
    def logout():
        session.clear()
        return redirect(url_for("home"), code=303)

    @app.get("/admin")
    @admin_required
    def admin():
        selected_status = request.args.get("status", "")
        selected_category = request.args.get("category", "")
        query = request.args.get("q", "").strip()[:120]
        conditions, parameters = [], []
        if selected_status in STATUSES:
            conditions.append("status = ?")
            parameters.append(selected_status)
        if selected_category in CATEGORIES:
            conditions.append("category = ?")
            parameters.append(selected_category)
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append("(case_number LIKE ? ESCAPE '\\' OR employee_id LIKE ? ESCAPE '\\' OR organization LIKE ? ESCAPE '\\')")
            parameters.extend(["%" + escaped + "%"] * 3)
        database = db.get_db()
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        count = database.execute("SELECT COUNT(*) FROM cases" + where, parameters).fetchone()[0]
        try:
            current_page = max(1, int(request.args.get("p", "1")))
        except ValueError:
            current_page = 1
        pages = max(1, (count + 19) // 20)
        current_page = min(current_page, pages)
        cases = database.execute("SELECT * FROM cases" + where + " ORDER BY id DESC LIMIT 20 OFFSET ?", parameters + [(current_page - 1) * 20]).fetchall()
        counts = {row["status"]: row["total"] for row in database.execute("SELECT status, COUNT(*) AS total FROM cases GROUP BY status")}
        return render_template("admin.html", page="admin", cases=cases, counts=counts, query=query,
                               selected_status=selected_status, selected_category=selected_category,
                               current_page=current_page, pages=pages, count=count)

    @app.route("/admin/cases/<number>", methods=["GET", "POST"])
    @admin_required
    def admin_case(number):
        database = db.get_db()
        case = database.execute("SELECT * FROM cases WHERE case_number = ?", (number,)).fetchone()
        if not case:
            abort(404)
        error, status, values = "", 200, {}
        if request.method == "POST":
            values = {field: request.form.get(field, "").strip() for field in ("category", "status", "assignee", "note")}
            try:
                version = int(request.form.get("version", ""))
            except ValueError:
                version = -1
            if values["category"] not in CATEGORIES or values["status"] not in STATUSES:
                error, status = "請選擇有效的分類與狀態。", 422
            elif len(values["assignee"]) > 80 or len(values["note"]) > 2000:
                error, status = "承辦人最多 80 字，內部備註最多 2,000 字。", 422
            else:
                # 人工標記不可解除，改分類也不會移除原始申訴的敏感性。
                sensitive = int(bool(case["sensitive"]) or values["category"] in SENSITIVE_CATEGORIES)
                stamp = db.now()
                try:
                    database.execute("BEGIN IMMEDIATE")
                    cursor = database.execute("UPDATE cases SET category=?, status=?, assignee=?, sensitive=?, updated_at=?, version=version+1 WHERE id=? AND version=?",
                                              (values["category"], values["status"], values["assignee"], sensitive, stamp, case["id"], version))
                    if cursor.rowcount != 1:
                        database.rollback()
                        error, status = "其他 HR 已更新此案件。下方已載入最新資料，請確認後再儲存。", 409
                    else:
                        action = "狀態：{} → {}；分類：{} → {}；承辦人：{} → {}".format(case["status"], values["status"], case["category"], values["category"], case["assignee"] or "未指派", values["assignee"] or "未指派")
                        database.execute("INSERT INTO case_history (case_id, created_at, actor, action, note) VALUES (?, ?, ?, ?, ?)",
                                         (case["id"], stamp, session["admin"], action, values["note"]))
                        database.commit()
                        flash("案件已更新，處理紀錄已儲存。", "success")
                        return redirect(url_for("admin_case", number=number), code=303)
                except Exception:
                    database.rollback()
                    raise
                case = database.execute("SELECT * FROM cases WHERE id = ?", (case["id"],)).fetchone()
                if status == 409:
                    values = {}
        history = database.execute("SELECT * FROM case_history WHERE case_id=? ORDER BY id DESC", (case["id"],)).fetchall()
        return render_template("admin_case.html", page="admin", case=case, history=history, error=error, values=values), status

    @app.get("/health")
    def health():
        db.get_db().execute("SELECT 1").fetchone()
        return {"ok": True}

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    @app.errorhandler(500)
    def error_page(error):
        messages = {404: "找不到這個頁面。", 413: "送出的內容過大，請縮短文字後再試。", 500: "系統暫時無法處理，請稍後再試。"}
        return render_template("error.html", page="", code=error.code, message=messages.get(error.code, error.description)), error.code

    @app.errorhandler(sqlite3.OperationalError)
    def database_error(_error):
        app.logger.warning("資料庫暫時無法處理，請檢查檔案權限或忙碌狀態。")
        return render_template("error.html", page="", code=503, message="資料儲存暫時無法使用，請稍後重試。"), 503

    return app
