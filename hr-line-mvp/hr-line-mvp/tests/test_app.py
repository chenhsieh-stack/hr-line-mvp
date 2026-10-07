import base64
import hashlib
import hmac
import json
import re
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from werkzeug.security import generate_password_hash

from hr_app import create_app
from hr_app.db import get_db, insert_case


class HRAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = {"TESTING": True, "SECRET_KEY": "test-only-secret", "DATABASE": str(Path(self.temp.name) / "test.sqlite3"),
                       "ADMIN_USERNAME": "hr", "ADMIN_PASSWORD_HASH": generate_password_hash("test-password", method="pbkdf2:sha256:1000"),
                       "LINE_LIFF_ID": "", "LINE_CHANNEL_SECRET": "test-channel-secret", "LINE_CHANNEL_ACCESS_TOKEN": "test-token",
                       "PUBLIC_APP_URL": "https://hr.example.test"}
        self.app = create_app(self.config)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def csrf(self, client=None):
        with (client or self.client).session_transaction() as session:
            return session["csrf"]

    def payload(self, kind="feedback", client=None):
        client = client or self.client
        client.get("/forms/" + kind)
        with client.session_transaction() as session:
            token = session["form_tokens"][-1]
            csrf = session["csrf"]
        values = {"name": "測試員工", "employee_id": "e001", "organization": "測試品牌／測試門市",
                  "title": "工作環境建議", "description": "請協助改善工作環境。", "category": "工作環境", "consent": "yes",
                  "csrf_token": csrf, "submission_token": token}
        if kind == "complaint":
            values.update(category="職場霸凌", title="測試申訴", description="只用於測試的事件經過。",
                          event_time="2026-10-06T10:30", location="測試地點", people="測試涉及人員", evidence="有", evidence_note="測試截圖")
        return values

    def submit(self, kind="feedback", extra=None, client=None):
        client = client or self.client
        data = self.payload(kind, client)
        data.update(extra or {})
        response = client.post("/forms/" + kind, data=data)
        self.assertEqual(response.status_code, 303)
        with client.session_transaction() as session:
            return session["receipt"]["number"]

    def login(self, client=None):
        client = client or self.client
        client.get("/admin/login")
        response = client.post("/admin/login", data={"username": "hr", "password": "test-password", "csrf_token": self.csrf(client)})
        self.assertEqual(response.status_code, 303)
        client.get("/admin")

    def fetch_case(self, number):
        with self.app.app_context():
            return dict(get_db().execute("SELECT * FROM cases WHERE case_number=?", (number,)).fetchone())

    def update(self, number, **changes):
        case = self.fetch_case(number)
        values = {"category": case["category"], "status": "處理中", "assignee": "HR 小林", "note": "已受理", "version": case["version"], "csrf_token": self.csrf()}
        values.update(changes)
        return self.client.post("/admin/cases/" + number, data=values)

    def test_all_core_pages_render_and_six_home_entries(self):
        home = self.client.get("/").get_data(as_text=True)
        self.assertEqual(home.count('class="service-card"'), 6)
        for path in ("/faq", "/faq?category=人事問題", "/forms/feedback", "/forms/complaint", "/forms/human", "/my-cases", "/admin/login", "/health"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get("/forms/unknown").status_code, 404)

    def test_faq_keyword_and_category_filters(self):
        text = self.client.get("/faq?q=特休&category=人事問題").get_data(as_text=True)
        self.assertIn("如何查詢特休與剩餘天數", text)
        self.assertNotIn("有哪些員工福利與獎金", text)
        self.assertIn("目前找不到符合的問題", self.client.get("/faq?q=ZZZZZZZZ").get_data(as_text=True))

    def test_feedback_receipt_and_restart_persistence(self):
        number = self.submit()
        self.assertRegex(number, r"^HR-\d{8}-001$")
        self.assertIn(number, self.client.get("/receipt").get_data(as_text=True))
        case = self.fetch_case(number)
        self.assertEqual((case["employee_id"], case["status"], case["sensitive"]), ("E001", "新案件", 0))
        restarted = create_app(self.config)
        with restarted.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM cases").fetchone()[0], 1)

    def test_repeated_submission_does_not_duplicate_case(self):
        values = self.payload()
        self.assertEqual(self.client.post("/forms/feedback", data=values).status_code, 303)
        self.assertEqual(self.client.post("/forms/feedback", data=values).status_code, 303)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM cases").fetchone()[0], 1)

    def test_concurrent_case_numbers_are_unique(self):
        values = {"kind": "feedback", "name": "並行測試", "employee_id": "C001", "organization": "測試門市", "category": "其他", "title": "並行", "description": "測試", "sensitive": 0}
        def create(index):
            with self.app.app_context():
                return insert_case(values, "concurrent-" + str(index))["case_number"]
        with ThreadPoolExecutor(max_workers=6) as pool:
            numbers = list(pool.map(create, range(18)))
        self.assertEqual(len(set(numbers)), 18)
        self.assertEqual(sorted(int(number.split("-")[-1]) for number in numbers), list(range(1, 19)))

    def test_complaint_fields_persist_and_manual_marker_cannot_be_removed(self):
        number = self.submit("complaint", {"sensitive": "0", "verdict": "成立"})
        case = self.fetch_case(number)
        self.assertEqual(case["sensitive"], 1)
        for field in ("event_time", "location", "people", "description", "evidence", "evidence_note"):
            self.assertTrue(case[field])
        self.assertNotIn("verdict", case)
        self.login()
        self.assertEqual(self.update(number, category="其他").status_code, 303)
        self.assertEqual(self.fetch_case(number)["sensitive"], 1)
        self.assertIn("系統不判定事件是否成立", self.client.get("/admin/cases/" + number).get_data(as_text=True))

    def test_sensitive_feedback_is_also_flagged(self):
        number = self.submit("feedback", {"category": "性騷擾"})
        self.assertEqual(self.fetch_case(number)["sensitive"], 1)

    def test_required_fields_and_date_are_validated_by_server(self):
        data = self.payload("complaint")
        data.update(employee_id="' OR 1=1 --", event_time="2026-99-99T09:00", people="", consent="")
        response = self.client.post("/forms/complaint", data=data)
        self.assertEqual(response.status_code, 422)
        self.assertIn("請確認以下欄位", response.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM cases").fetchone()[0], 0)

    def test_csrf_and_submission_nonce_are_required(self):
        data = self.payload()
        data["csrf_token"] = "wrong"
        self.assertEqual(self.client.post("/forms/feedback", data=data).status_code, 400)
        data["csrf_token"] = self.csrf()
        data["submission_token"] = "invented"
        self.assertEqual(self.client.post("/forms/feedback", data=data).status_code, 400)

    def test_employee_lookup_filters_and_omits_confidential_details(self):
        first = self.submit("complaint")
        second = self.submit("feedback", {"employee_id": "E002"})
        self.client.get("/my-cases")
        response = self.client.post("/my-cases", data={"employee_id": "e001", "csrf_token": self.csrf()})
        text = response.get_data(as_text=True)
        self.assertIn(first, text)
        self.assertNotIn(second, text)
        for secret in ("測試員工", "測試涉及人員", "只用於測試的事件經過", "測試地點", "測試截圖"):
            self.assertNotIn(secret, text)

    def test_admin_requires_login_and_logout_revokes_access(self):
        number = self.submit()
        self.assertEqual(self.client.get("/admin").status_code, 302)
        self.assertEqual(self.client.get("/admin/cases/" + number).status_code, 302)
        self.login()
        self.assertEqual(self.client.get("/admin").status_code, 200)
        self.assertEqual(self.client.post("/admin/logout", data={"csrf_token": self.csrf()}).status_code, 303)
        self.assertEqual(self.client.get("/admin").status_code, 302)

    def test_admin_classification_assignment_all_statuses_and_audit(self):
        number = self.submit("human")
        self.login()
        for status in ("處理中", "待員工回覆", "已結案", "新案件"):
            self.assertEqual(self.update(number, status=status, category="薪資福利").status_code, 303)
            case = self.fetch_case(number)
            self.assertEqual((case["status"], case["category"], case["assignee"]), (status, "薪資福利", "HR 小林"))
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM case_history").fetchone()[0], 5)

    def test_invalid_status_and_stale_version_do_not_overwrite(self):
        number = self.submit()
        self.login()
        self.assertEqual(self.update(number, status="成立").status_code, 422)
        self.assertEqual(self.update(number).status_code, 303)
        self.assertEqual(self.update(number, version=1, status="已結案").status_code, 409)
        self.assertEqual(self.fetch_case(number)["status"], "處理中")

    def test_xss_in_submitted_text_is_escaped(self):
        attack = '<script>alert("xss")</script>'
        number = self.submit(extra={"title": attack, "description": attack})
        self.login()
        text = self.client.get("/admin/cases/" + number).get_data(as_text=True)
        self.assertNotIn(attack, text)
        self.assertIn("&lt;script&gt;", text)

    def test_admin_filters_are_parameterized_and_paginated(self):
        number = self.submit(extra={"employee_id": "E_SPECIAL"})
        self.submit(extra={"employee_id": "E002"})
        self.login()
        text = self.client.get("/admin?q=E_SPECIAL").get_data(as_text=True)
        self.assertIn(number, text)
        self.assertIn("共 1 件", text)
        self.assertIn("共 0 件", self.client.get("/admin?q=%27%20OR%201%3D1").get_data(as_text=True))
        self.assertEqual(self.client.get("/admin?p=bad").status_code, 200)

    def test_login_rate_limit(self):
        self.client.get("/admin/login")
        for _ in range(5):
            self.assertEqual(self.client.post("/admin/login", data={"username": "hr", "password": "wrong", "csrf_token": self.csrf()}).status_code, 401)
        self.assertEqual(self.client.post("/admin/login", data={"username": "hr", "password": "wrong", "csrf_token": self.csrf()}).status_code, 429)

    def signed_webhook(self, payload, body=None):
        body = body if body is not None else json.dumps(payload, ensure_ascii=False).encode()
        signature = base64.b64encode(hmac.new(b"test-channel-secret", body, hashlib.sha256).digest()).decode()
        return self.client.post("/api/line/webhook", data=body, content_type="application/json", headers={"X-Line-Signature": signature})

    def event(self, text="薪資", event_id="event-1"):
        return {"events": [{"type": "message", "webhookEventId": event_id, "replyToken": "test-reply", "message": {"type": "text", "text": text}}]}

    def test_webhook_rejects_unsigned_and_modified_body(self):
        self.assertEqual(self.client.post("/api/line/webhook", json={"events": []}).status_code, 401)
        self.assertEqual(self.client.post("/api/line/webhook", json={"events": []}, headers={"X-Line-Signature": "invalid"}).status_code, 401)
        self.assertEqual(self.signed_webhook(None, body=b"not json").status_code, 400)

    def test_webhook_verify_empty_events_and_missing_settings(self):
        self.assertEqual(self.signed_webhook({"events": []}).status_code, 200)
        self.app.config["LINE_CHANNEL_SECRET"] = ""
        self.assertEqual(self.client.post("/api/line/webhook", json={"events": []}).status_code, 503)

    def test_webhook_faq_and_deduplication(self):
        with patch("hr_app.line.send_reply") as sender:
            self.assertEqual(self.signed_webhook(self.event()).json["handled"], 1)
            self.assertEqual(self.signed_webhook(self.event()).json["handled"], 0)
            self.assertEqual(sender.call_count, 1)
            self.assertIn("人工核對", sender.call_args[0][1])

    def test_webhook_sensitive_text_always_redirects_to_humans(self):
        with patch("hr_app.line.send_reply") as sender:
            self.assertEqual(self.signed_webhook(self.event("我想申訴性騷擾")).status_code, 200)
            answer = sender.call_args[0][1]
            self.assertIn("不判定是否成立", answer)
            self.assertIn("https://hr.example.test/forms/complaint", answer)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM cases").fetchone()[0], 0)

    def test_failed_webhook_reply_can_retry(self):
        with patch("hr_app.line.send_reply", side_effect=URLError("test")):
            self.assertEqual(self.signed_webhook(self.event()).status_code, 502)
        with patch("hr_app.line.send_reply") as sender:
            self.assertEqual(self.signed_webhook(self.event()).json["handled"], 1)
            self.assertEqual(sender.call_count, 1)

    def test_response_headers_and_large_request_limit(self):
        response = self.client.get("/")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
        form_response = self.client.get("/forms/feedback")
        self.assertIn("HttpOnly", form_response.headers.get("Set-Cookie", ""))
        response = self.client.post("/forms/feedback", data=b"x" * (256 * 1024 + 1), content_type="application/x-www-form-urlencoded")
        self.assertEqual(response.status_code, 413)


if __name__ == "__main__":
    unittest.main()
