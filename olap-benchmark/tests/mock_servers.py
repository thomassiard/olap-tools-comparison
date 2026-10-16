"""SAMO ZA TESTIRANJE KODA: lazni ClickHouse/Metabase/Superset posluzitelji. Brojke NISU stvarne i ne smiju u rad."""
import json, threading, time, random
from http.server import BaseHTTPRequestHandler, HTTPServer

def fake_rows(sql, as_dict):
    s = sql.lower()
    tot = 32434489
    if "limit 20" in s:
        data = [(i, 1000 - i) for i in range(1, 21)]; cols = ["product_id", "n"]
    elif "o.order_dow" in s:
        data = [("produce", d, tot // 7 if d < 6 else tot - 6 * (tot // 7)) for d in range(7)]; cols = ["department", "order_dow", "n"]
    elif "group by d.department" in s:
        data = [("produce", tot - 100), ("dairy", 100)]; cols = ["department", "n"]
    elif "count()" in s and "group by" not in s:
        data = [(12345,)]; cols = ["n"]
    else:
        data = [(i, i * 2) for i in range(10)]; cols = ["a", "n"]
    return [dict(zip(cols, r)) for r in data] if as_dict else [list(r) for r in data]

def make_handler(kind, base_delay):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            self._send({"result": "csrf-token"})
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0)); body = self.rfile.read(n).decode()
            time.sleep(base_delay * random.uniform(0.9, 1.3))
            if kind == "clickhouse":
                rows = fake_rows(body, True)
                rows = [{k: (str(v) if k == "n" else v) for k, v in r.items()} for r in rows]
                return self._send({"data": rows, "statistics": {"elapsed": base_delay}})
            if self.path.endswith("/api/session") or self.path.endswith("/security/login"):
                return self._send({"id": "tok", "access_token": "jwt"})
            j = json.loads(body)
            if kind == "metabase":
                return self._send({"status": "completed", "running_time": int(base_delay * 1000), "data": {"rows": fake_rows(j["native"]["query"], False)}})
            return self._send({"status": "success", "data": fake_rows(j["sql"], True)})
    return H

def start(kind, port, delay):
    s = HTTPServer(("127.0.0.1", port), make_handler(kind, delay))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s

if __name__ == "__main__":
    start("clickhouse", 18123, 0.005); start("metabase", 13000, 0.03); start("superset", 18088, 0.06)
    time.sleep(3600)
