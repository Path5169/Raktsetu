"""Tiny local web server: serves the UI and a JSON API over the same engine as the CLI."""
import json, threading, webbrowser
from datetime import date
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from . import db, dispatch, inventory as inv, seed
from .compat import GROUPS, SHELF_LIFE_DAYS, donors_for

PAGE = Path(__file__).parent / "web" / "index.html"

def state(conn):
    inv.sweep(conn); dispatch.release_holds(conn)
    banks = [dict(r) for r in conn.execute("SELECT id,name FROM banks ORDER BY id")]
    stock = {}
    for comp in SHELF_LIFE_DAYS:
        m = inv.stock_matrix(conn, comp)
        stock[comp] = {g: {b["id"]: m.get((b["id"], g), 0) for b in banks} for g in GROUPS}
    return {
        "today": date.today().isoformat(), "banks": banks, "groups": GROUPS, "hospitals": [dict(r) for r in conn.execute("SELECT id,name,verified FROM hospitals")], "stock": stock,
        "receive_from": {c: {g: donors_for(g, c) for g in GROUPS} for c in SHELF_LIFE_DAYS},
        "expiring": [dict(r) for r in inv.expiring(conn, 3)],
        "audit": [dict(r) for r in conn.execute("SELECT ts,action,detail FROM audit_log ORDER BY id DESC LIMIT 6")],
    }

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path == "/api/state":
            conn = db.connect(); self._send(200, state(conn)); conn.close()
        elif self.path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, {"error": "not found"})
    def do_POST(self):
        conn = db.connect()
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            p = self.path
            if p == "/api/add":
                qty = int(d["qty"])
                if not 1 <= qty <= 50: raise ValueError("Quantity must be between 1 and 50.")
                bank = conn.execute("SELECT id,name FROM banks WHERE id=?", (int(d["bank_id"]),)).fetchone()
                if not bank: raise ValueError("Unknown blood bank.")
                exp = inv.add_units(conn, bank["id"], d["group"], d["component"], qty)
                self._send(200, {"ok": True, "bank": bank["name"], "expires": exp.isoformat()})
            elif p == "/api/request":
                qty = int(d["qty"])
                if not 1 <= qty <= 10: raise ValueError("Request between 1 and 10 units.")
                self._send(200, dispatch.create_request(conn, int(d["hospital_id"]), d["group"], d["component"], qty))
            elif p in ("/api/request/issue", "/api/request/cancel"):
                fn = dispatch.issue if p.endswith("issue") else dispatch.cancel
                self._send(200, {"ok": True, "units": fn(conn, int(d["request_id"]))})
            elif p == "/api/race":
                self._send(200, dispatch.race(d["group"], d["component"], 6))
            else:
                self._send(404, {"error": "not found"})
        except (ValueError, KeyError, TypeError, dispatch.Blocked) as e:
            self._send(400, {"error": str(e) or "Invalid request."})
        finally:
            conn.close()


def run(port=8000, open_browser=True):
    conn = db.connect()
    if not conn.execute("SELECT 1 FROM banks").fetchone(): seed.seed(conn)
    conn.close()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"RaktSetu running at {url}  (Ctrl+C to stop)")
    if open_browser: threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")
