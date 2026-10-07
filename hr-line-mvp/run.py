"""本機與雲端部署入口；使用 Waitress，無自動重載與除錯控制台。"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hr_app import create_app
from waitress import serve


def load_env(path):
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep and key.strip().replace("_", "").isalnum():
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


app = create_app()

if __name__ == "__main__":
    load_env(BASE_DIR / ".env")

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "10000"))

    print(f"HR 員工服務中心：http://{host}:{port}", flush=True)
    print(f"HR 後台：http://{host}:{port}/admin", flush=True)
    print("本機 MVP：請使用測試資料；員工編號尚未完成身分驗證。", flush=True)

    serve(app, host=host, port=port, threads=8)