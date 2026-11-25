# -*- coding: utf-8 -*-
"""盲听投票接收端：127.0.0.1:8812/vote  POST 任意 body 追加到 _ab_votes.jsonl。

用 sendBeacon + text/plain 发送（简单请求，无预检），所以这里不需要复杂 CORS。
"""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OUT = "G:/_setup/_ab_votes.jsonl"


class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8", "replace")
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "path": self.path, "body": body}
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print("got", len(body), "bytes", flush=True)
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("vote sink on http://127.0.0.1:8812/vote ->", OUT, flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8812), H).serve_forever()
