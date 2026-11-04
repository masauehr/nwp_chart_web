#!/usr/bin/env python
# coding: utf-8
"""ECMWF/GFS天気図ビューア用の簡易サーバー（ローカル用。公開は build_site.py で作る静的サイトを使う）（標準ライブラリのみ）。

  /          → web/ の静的ファイル
  /output/   → output/（make_charts.py が作成したPNGとmanifest.json）
  POST /api/update  → 最新データを取得して作図（update_latest.py を裏で実行。ローカルからのみ）
  GET  /api/status  → 更新ジョブの状態とログ末尾

使用例:
  python server.py                 # http://127.0.0.1:8790/
  python server.py --port 9000
外部公開はしない設計（127.0.0.1 固定）。LAN内の別端末から見る場合のみ --host 0.0.0.0 を明示する。
"""
import argparse
import json
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_FILE = ROOT / "logs" / "update_ui.log"

# 画面の「最新を取得」ボタンから起動する更新ジョブの状態（サーバープロセス内で1つだけ）
_job = {"proc": None, "started": None, "rc": None}
_job_lock = threading.Lock()


def start_update():
    """update_latest.py を裏で起動する。実行中なら起動せず False。"""
    with _job_lock:
        p = _job["proc"]
        if p is not None and p.poll() is None:
            return False
        LOG_FILE.parent.mkdir(exist_ok=True)
        f = open(LOG_FILE, "w", encoding="utf-8")  # 毎回上書き（最新の1回分だけ見せる）
        _job["proc"] = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "update_latest.py"), "--jobs", "3"],
            cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
        _job["started"] = __import__("time").time()
        _job["rc"] = None
        return True


def job_status():
    with _job_lock:
        p = _job["proc"]
        running = p is not None and p.poll() is None
        if p is not None and not running:
            _job["rc"] = p.returncode
        tail = []
        if LOG_FILE.exists():
            tail = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-6:]
        return {"running": running, "started": _job["started"], "rc": _job["rc"], "log": tail}


class Handler(SimpleHTTPRequestHandler):
    """/output/ を output/ ディレクトリへ振り分け、manifest.json はキャッシュさせない。"""

    def translate_path(self, path):
        p = path.split("?", 1)[0].split("#", 1)[0]
        if p.startswith("/output/"):
            rel = Path(p[len("/output/"):])
            target = (ROOT / "output" / rel).resolve()
            # ディレクトリトラバーサル対策: output/ の外へ出さない
            if (ROOT / "output").resolve() not in target.parents and target != (ROOT / "output").resolve():
                return str(ROOT / "output" / "__forbidden__")
            return str(target)
        return super().translate_path(path)

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _local_only(self):
        """更新APIは自分のPC（ループバック）からだけ許可。LAN公開時に他端末から叩かれないようにする。"""
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self._json(403, {"error": "ローカルからのみ実行できます"})
            return False
        return True

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/api/status":
            if self._local_only():
                self._json(200, job_status())
            return
        super().do_GET()

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/update":
            self._json(404, {"error": "not found"})
            return
        if not self._local_only():
            return
        # 他サイトのページからの送信（CSRF）対策: Origin があれば同一ホストのものだけ許可
        origin = self.headers.get("Origin")
        if origin and origin.split("://", 1)[-1] != self.headers.get("Host"):
            self._json(403, {"error": "不正なOriginです"})
            return
        started = start_update()
        self._json(200, {"started": started, **job_status()})

    def end_headers(self):
        if self.path.split("?", 1)[0].endswith((".json", ".html", ".js", ".css", "/")):
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "max-age=600")  # PNGは初期値ごとに別ファイル名のため短期キャッシュ可
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # アクセスログは出さない


def main():
    p = argparse.ArgumentParser(description="ECMWF/GFS天気図ビューアのサーバー")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8790)
    if any(a in sys.argv[1:] for a in ("?", "-?", "--?")):
        p.print_help()
        return
    a = p.parse_args()
    handler = partial(Handler, directory=str(ROOT / "web"))
    srv = ThreadingHTTPServer((a.host, a.port), handler)
    print(f"http://{a.host}:{a.port}/ で公開中（Ctrl+C で停止）")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
