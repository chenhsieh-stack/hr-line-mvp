"""選用 LINE 接口：原始 body 驗簽、固定 FAQ 回覆、敏感事件人工導流。"""
import base64
import hashlib
import hmac
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Blueprint, current_app, jsonify, request

from .db import get_db, now

line_bp = Blueprint("line", __name__)


def reply_text(text):
    base = current_app.config["PUBLIC_APP_URL"]
    sensitive_words = ("申訴", "霸凌", "性騷擾", "不法侵害", "騷擾")
    if any(word in text for word in sensitive_words):
        answer = "敏感事件由 HR 人工受理，系統不判定是否成立。請前往安心申訴填寫表單。"
        return answer + ("\n" + base + "/forms/complaint" if base else "")
    links = {"意見反映": "/forms/feedback", "真人HR": "/forms/human", "我的案件": "/my-cases"}
    if text in links:
        return "請開啟員工服務中心辦理「{}」。".format(text) + ("\n" + base + links[text] if base else "")
    if text in ("人事問題", "薪資福利", "制度查詢"):
        questions = [item["question"] for item in current_app.config["FAQS"] if item["category"] == text]
        return "{}\n{}".format(text, "\n".join("• " + q for q in questions)) + ("\n" + base + "/faq" if base else "")
    matches = current_app.config["SEARCH_FAQS"](text)
    if matches:
        return "{}\n\n{}".format(matches[0]["question"], matches[0]["answer"])
    return "歡迎使用 HR 員工服務中心。可輸入「請假」「特休」「薪資」，或選擇意見反映、安心申訴、真人HR。" + ("\n" + base if base else "")


def send_reply(token, text):
    payload = json.dumps({"replyToken": token, "messages": [{"type": "text", "text": text}]}, ensure_ascii=False).encode("utf-8")
    req = Request("https://api.line.me/v2/bot/message/reply", data=payload, method="POST", headers={
        "Authorization": "Bearer " + current_app.config["LINE_CHANNEL_ACCESS_TOKEN"],
        "Content-Type": "application/json"})
    with urlopen(req, timeout=5) as response:
        return response.status


@line_bp.post("/api/line/webhook")
def webhook():
    secret = current_app.config["LINE_CHANNEL_SECRET"]
    if not secret:
        return jsonify(error="尚未設定 LINE_CHANNEL_SECRET"), 503
    body = request.get_data()
    expected = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    supplied = request.headers.get("X-Line-Signature", "")
    if not hmac.compare_digest(expected.encode(), supplied.encode()):
        return jsonify(error="Webhook 簽章不正確"), 401
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return jsonify(error="JSON 格式不正確"), 400
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        return jsonify(error="缺少 events 陣列"), 400
    if len(payload["events"]) > 100:
        return jsonify(error="事件數量過多"), 400
    handled = 0
    for event in payload["events"]:
        if not isinstance(event, dict):
            return jsonify(error="事件格式不正確"), 400
        message = event.get("message")
        if event.get("type") != "message" or not isinstance(message, dict) or message.get("type") != "text":
            continue
        if not current_app.config["LINE_CHANNEL_ACCESS_TOKEN"]:
            return jsonify(error="文字回覆需設定 LINE_CHANNEL_ACCESS_TOKEN"), 503
        event_id, token, text = event.get("webhookEventId"), event.get("replyToken"), message.get("text")
        if not all(isinstance(value, str) and value for value in (event_id, token, text)):
            return jsonify(error="文字事件欄位不完整"), 400
        db = get_db()
        # 本機 MVP 以 SQLite transaction 避免同時重送重複回覆。
        # 正式流量應改為非同步 outbox，避免外部 API 呼叫期間占用寫入鎖。
        db.execute("BEGIN IMMEDIATE")
        try:
            if db.execute("SELECT 1 FROM webhook_events WHERE event_id = ?", (event_id,)).fetchone():
                db.commit()
                continue
            send_reply(token, reply_text(text.strip()))
            db.execute("INSERT INTO webhook_events VALUES (?, ?)", (event_id, now()))
            db.commit()
            handled += 1
        except (HTTPError, URLError, TimeoutError, OSError):
            db.rollback()
            current_app.logger.warning("LINE 回覆失敗，未儲存訊息內容或 token；請檢查 API 設定與網路。")
            return jsonify(error="LINE 回覆失敗，請稍後重試"), 502
        except Exception:
            db.rollback()
            raise
    return jsonify(ok=True, handled=handled)
