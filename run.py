"""本機入口；使用 Waitress，無自動重載與除錯控制台。"""
import os
from pathlib import Path


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


if __name__ == "__main__":
    load_env(Path(__file__).parent / ".env")
    from hr_app import create_app
    from waitress import serve

    app = create_app()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print("HR 員工服務中心：http://{}:{}".format(host, port), flush=True)
    print("HR 後台：http://{}:{}/admin".format(host, port), flush=True)
    print("本機 MVP：請使用測試資料；員工編號尚未完成身分驗證。", flush=True)
    serve(app, host=host, port=port, threads=8)
