"""Tiny local web server: serves the UI and a JSON API over the same engine as the CLI."""
import json, threading, webbrowser
from datetime import date
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from . import alerts, db, dispatch, donors as dn, inventory as inv, seed
from .compat import GROUPS, SHELF_LIFE_DAYS, donors_for

WEB = Path(__file__).parent / "web"
PAGE = WEB / "index.html"
DONOR_PAGE = WEB / "donor.html"

def state(conn):
    inv.sweep(conn); dispatch.release_holds(conn); alerts.tick(conn)
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
        "calls": alerts.list_calls(conn), "wave_timeout_min": alerts.WAVE_TIMEOUT_MIN, "waves": len(alerts.WAVES),
    }

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def _token(self):
        h = self.headers.get("Authorization", "")
        return h[7:] if h.startswith("Bearer ") else ""
    def do_GET(self):
        if self.path == "/api/state":
            conn = db.connect(); self._send(200, state(conn)); conn.close()
        elif self.path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path in ("/donor", "/donor/"):
            self._send(200, DONOR_PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/donor/me":
            conn = db.connect()
            try:
                alerts.tick(conn)
                did = dn.session_donor(conn, self._token())
                self._send(200, {**dn.profile(conn, did), "calls": alerts.calls_for_donor(conn, did), "wave_timeout_min": alerts.WAVE_TIMEOUT_MIN})
            except dn.AuthError as e:
                self._send(401, {"error": str(e)})
            finally:
                conn.close()
        elif self.path == "/api/donor/demo" and dn.OTP_MOCK:   # demo helper so judges can pick a donor to log in as
            conn = db.connect()
            self._send(200, [dict(r) for r in conn.execute("SELECT name,blood_group,phone FROM donors WHERE phone IS NOT NULL ORDER BY id LIMIT 20")]); conn.close()
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
            elif p == "/api/donor/otp/send":
                self._send(200, dn.send_otp(conn, d["phone"]))
            elif p == "/api/donor/otp/verify":
                self._send(200, dn.verify_otp(conn, d["phone"], d["otp"]))
            elif p in ("/api/donor/accept", "/api/donor/decline"):
                did = dn.session_donor(conn, self._token()); cid = int(d["call_id"])
                self._send(200, alerts.accept(conn, cid, did) if p.endswith("accept") else {"ok": True, "declined": alerts.decline(conn, cid, did)})
            elif p == "/api/calls/scan":
                self._send(200, {"opened": [{"call_id": o["call_id"], "blood_group": o["blood_group"], "alerted": len(o["alerted"])} for o in alerts.scan_low_stock(conn)]})
            elif p == "/api/calls/tick":
                self._send(200, {"moved": alerts.tick(conn, force=bool(d.get("force")))})
            elif p == "/api/calls/race":
                self._send(200, alerts.race_accept(int(d["call_id"])))
            else:
                self._send(404, {"error": "not found"})
        except dn.AuthError as e:
            self._send(401, {"error": str(e)})
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
