"""Local RaktSetu web server with role-based API authorization."""
import json, mimetypes, threading, webbrowser
from datetime import date, datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
from . import alerts, auth, db, dispatch, donors as dn, inventory as inv, seed
from .compat import GROUPS, SHELF_LIFE_DAYS, donors_for

WEB = Path(__file__).parent.parent / "frontend"
PAGE, DONOR_PAGE, BANK_PAGE, LOGIN_PAGE = (WEB / x for x in ("index.html", "donor.html", "bank.html", "login.html"))


def state(conn):
    inv.sweep(conn); dispatch.release_holds(conn); alerts.tick(conn)
    banks = [dict(r) for r in conn.execute("SELECT id,name FROM banks ORDER BY id")]
    stock = {}
    for comp in SHELF_LIFE_DAYS:
        m = inv.stock_matrix(conn, comp)
        stock[comp] = {g: {b["id"]: m.get((b["id"], g), 0) for b in banks} for g in GROUPS}
    return {"today": date.today().isoformat(), "banks": banks, "groups": GROUPS,
            "hospitals": [dict(r) for r in conn.execute("SELECT id,name,verified FROM hospitals")], "stock": stock,
            "receive_from": {c: {g: donors_for(g, c) for g in GROUPS} for c in SHELF_LIFE_DAYS},
            "expiring": [dict(r) for r in inv.expiring(conn, 3)],
            "audit": [dict(r) for r in conn.execute("SELECT ts,action,detail FROM audit_log ORDER BY id DESC LIMIT 10")],
            "calls": alerts.list_calls(conn), "wave_timeout_min": alerts.WAVE_TIMEOUT_MIN, "waves": len(alerts.WAVES)}


def network(conn):
    now = datetime.now().isoformat(timespec="seconds")
    open_alerts = {}
    for r in conn.execute("""SELECT a.donor_id, c.id call_id, c.blood_group, c.component, c.status, a.wave, a.km
                             FROM call_alerts a JOIN donor_calls c ON c.id=a.call_id
                             WHERE c.status='open' AND a.response IS NULL"""):
        open_alerts.setdefault(r["donor_id"], []).append({"call_id": r["call_id"], "group": r["blood_group"], "component": r["component"], "wave": r["wave"], "km": r["km"]})
    donors = []
    for d in conn.execute("SELECT * FROM donors WHERE lat IS NOT NULL AND lon IS NOT NULL ORDER BY id"):
        rb, pl = dn.eligibility(d, "RBC"), dn.eligibility(d, "PLT")
        alerts_for = open_alerts.get(d["id"], [])
        donors.append({"id": d["id"], "name": d["name"], "blood_group": d["blood_group"], "lat": d["lat"], "lon": d["lon"], "last_seen": d["last_seen"],
                       "status": "alerted" if alerts_for else "available" if rb["eligible"] or pl["eligible"] else "resting",
                       "eligible": {"RBC": rb["eligible"], "PLT": pl["eligible"]}, "alerts": alerts_for})
    banks = [dict(r) for r in conn.execute("SELECT id,name,lat,lon,open_24x7 FROM banks ORDER BY id")]
    hospitals = [dict(r) for r in conn.execute("SELECT id,name,lat,lon,verified FROM hospitals ORDER BY id")]
    return {"updated_at": now, "center": [21.1458, 79.0882], "donors": donors, "banks": banks, "hospitals": hospitals,
            "calls": alerts.list_calls(conn), "critical_threshold": alerts.LOW_STOCK}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def _token(self):
        h = self.headers.get("Authorization", "")
        return h[7:] if h.startswith("Bearer ") else ""
    def _user(self, conn, *roles): return auth.require(conn, self._token(), *roles)
    def _json(self): return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/manus-routes.json": self._send(200, (WEB / "manus-routes.json").read_bytes(), "application/json; charset=utf-8"); return
        if path.startswith("/assets/"):
            target = (WEB / "assets" / path.removeprefix("/assets/")).resolve(); root = (WEB / "assets").resolve()
            if target.is_file() and root in target.parents:
                self._send(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            else: self._send(404, {"error":"asset not found"})
            return
        if path == "/login": self._send(200, LOGIN_PAGE.read_bytes(), "text/html; charset=utf-8"); return
        if path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8"); return
        if path in ("/donor", "/donor/"):
            self._send(200, DONOR_PAGE.read_bytes(), "text/html; charset=utf-8"); return
        if path in ("/bank", "/bank/"):
            self._send(200, BANK_PAGE.read_bytes(), "text/html; charset=utf-8"); return
        conn = db.connect()
        try:
            if path == "/api/auth/me": self._send(200, auth.public_user(self._user(conn))); return
            if path == "/api/state": self._user(conn, "admin", "hospital", "bank"); self._send(200, state(conn)); return
            if path == "/api/network": self._user(conn, "admin", "hospital", "bank"); self._send(200, network(conn)); return
            if path == "/api/donor/me":
                alerts.tick(conn); did = dn.session_donor(conn, self._token())
                self._send(200, {**dn.profile(conn, did), "calls": alerts.calls_for_donor(conn, did), "wave_timeout_min": alerts.WAVE_TIMEOUT_MIN}); return
            if path == "/api/donor/demo" and dn.OTP_MOCK:
                self._send(200, [dict(r) for r in conn.execute("SELECT name,blood_group,phone FROM donors WHERE phone IS NOT NULL ORDER BY id LIMIT 20")]); return
            if path == "/api/bank/queue":
                user=self._user(conn,"admin","bank")
                q=dn.pending_donations(conn)
                if user["role"]=="bank": q=[x for x in q if x.get("bank")==conn.execute("SELECT name FROM banks WHERE id=?",(user["bank_id"],)).fetchone()[0]]
                self._send(200, {"queue":q,"summary":dn.donation_summary(conn)}); return
            self._send(404, {"error":"not found"})
        except auth.AuthError as e: self._send(401,{"error":str(e)})
        except auth.ForbiddenError as e: self._send(403,{"error":str(e)})
        finally: conn.close()

    def do_POST(self):
        conn = db.connect()
        try:
            d=self._json(); p=self.path
            if p == "/api/auth/login": self._send(200, auth.login(conn, str(d.get("username","")), str(d.get("password","")))); return
            if p == "/api/auth/logout": auth.logout(conn,self._token()); self._send(200,{"ok":True}); return
            if p == "/api/add":
                u=self._user(conn,"admin","bank"); bank_id=int(d["bank_id"])
                if u["role"]=="bank" and u["bank_id"]!=bank_id: raise auth.ForbiddenError("You can only manage your assigned blood bank.")
                qty=int(d["qty"])
                if not 1<=qty<=50: raise ValueError("Quantity must be between 1 and 50.")
                bank=conn.execute("SELECT id,name FROM banks WHERE id=?",(bank_id,)).fetchone()
                if not bank: raise ValueError("Unknown blood bank.")
                exp=inv.add_units(conn,bank_id,d["group"],d["component"],qty); self._send(200,{"ok":True,"bank":bank["name"],"expires":exp.isoformat()}); return
            if p == "/api/request":
                u=self._user(conn,"admin","hospital"); hid=int(d["hospital_id"])
                if u["role"]=="hospital" and u["hospital_id"]!=hid: raise auth.ForbiddenError("A hospital account can only create requests for its own hospital.")
                qty=int(d["qty"])
                if not 1<=qty<=10: raise ValueError("Request between 1 and 10 units.")
                self._send(200,dispatch.create_request(conn,hid,d["group"],d["component"],qty)); return
            if p in ("/api/request/issue","/api/request/cancel"):
                u=self._user(conn,"admin","bank"); rid=int(d["request_id"])
                req=conn.execute("SELECT bank_id FROM requests WHERE id=?",(rid,)).fetchone()
                if not req: raise ValueError("Unknown request.")
                if u["role"]=="bank" and req["bank_id"] not in (None,u["bank_id"]): raise auth.ForbiddenError("This request is assigned to another bank.")
                fn=dispatch.issue if p.endswith("issue") else dispatch.cancel; self._send(200,{"ok":True,"units":fn(conn,rid)}); return
            if p == "/api/race": self._user(conn,"admin"); self._send(200,dispatch.race(d["group"],d["component"],6)); return
            if p == "/api/donor/otp/send": self._send(200,dn.send_otp(conn,d["phone"])); return
            if p == "/api/donor/otp/verify": self._send(200,dn.verify_otp(conn,d["phone"],d["otp"])); return
            if p == "/api/donor/presence":
                donor_id=dn.session_donor(conn,self._token()); lat,lon=float(d["lat"]),float(d["lon"])
                if not(-90<=lat<=90 and -180<=lon<=180): raise ValueError("Invalid location coordinates.")
                conn.execute("UPDATE donors SET lat=?,lon=?,last_seen=? WHERE id=?",(lat,lon,datetime.now().isoformat(timespec="seconds"),donor_id)); conn.commit(); self._send(200,{"ok":True,"donor_id":donor_id}); return
            if p in ("/api/donor/accept","/api/donor/decline"):
                did=dn.session_donor(conn,self._token()); cid=int(d["call_id"]); self._send(200,alerts.accept(conn,cid,did) if p.endswith("accept") else {"ok":True,"declined":alerts.decline(conn,cid,did)}); return
            if p == "/api/calls/scan": self._user(conn,"admin","bank"); self._send(200,{"opened":[{"call_id":o["call_id"],"blood_group":o["blood_group"],"alerted":len(o["alerted"])} for o in alerts.scan_low_stock(conn)]}); return
            if p == "/api/calls/tick": self._user(conn,"admin","bank"); self._send(200,{"moved":alerts.tick(conn,force=bool(d.get("force")))}); return
            if p == "/api/calls/race": self._user(conn,"admin"); self._send(200,alerts.race_accept(int(d["call_id"]))); return
            if p == "/api/broadcast":
                u=self._user(conn,"admin","hospital","bank"); hid=int(d["hospital_id"])
                if u["role"]=="hospital" and u["hospital_id"]!=hid: raise auth.ForbiddenError("You can only broadcast for your own hospital.")
                group,component=d.get("group"),d.get("component","RBC"); slots=int(d.get("slots",1))
                if slots<1 or slots>20: raise ValueError("Broadcast slots must be between 1 and 20.")
                hospital=conn.execute("SELECT * FROM hospitals WHERE id=?",(hid,)).fetchone()
                if not hospital or not hospital["verified"]: raise ValueError("Only verified hospitals can broadcast emergencies.")
                message=str(d.get("message","")).strip()[:240]; reason=message or f"Emergency broadcast: {slots} x {group} {component} needed at {hospital['name']}."
                result=alerts.open_call(conn,group,component,slots,lat=hospital["lat"],lon=hospital["lon"],exact_only=False,reason=reason,actor=f"{u['role']}:{u['id']}")
                self._send(200,{"ok":True,"call_id":result["call_id"],"existing":result["existing"],"alerted":len(result.get("alerted",[])),"recipients":result.get("alerted",[]),"bank":result.get("bank"),"slots":result["slots"],"message":reason}); return
            if p == "/api/bank/verify":
                u=self._user(conn,"admin","bank"); donation_id=int(d["donation_id"])
                donation=conn.execute("SELECT bank_id FROM donations WHERE id=?",(donation_id,)).fetchone()
                if not donation: raise ValueError("Unknown donation.")
                if u["role"]=="bank" and donation["bank_id"] not in (None,u["bank_id"]): raise auth.ForbiddenError("You can only verify donations assigned to your bank.")
                dn.verify_donation(conn,donation_id,actor=f"{u['role']}:{u['id']}"); self._send(200,{"ok":True,"donation_id":donation_id}); return
            self._send(404,{"error":"not found"})
        except auth.AuthError as e: self._send(401,{"error":str(e)})
        except auth.ForbiddenError as e: self._send(403,{"error":str(e)})
        except dn.AuthError as e: self._send(401,{"error":str(e)})
        except (ValueError,KeyError,TypeError,dispatch.Blocked) as e: self._send(400,{"error":str(e) or "Invalid request."})
        finally: conn.close()


def run(port=8000,open_browser=True):
    conn=db.connect()
    if not conn.execute("SELECT 1 FROM banks").fetchone() or not conn.execute("SELECT 1 FROM users").fetchone(): seed.seed(conn)
    conn.close(); srv=ThreadingHTTPServer(("127.0.0.1",port),Handler); url=f"http://127.0.0.1:{port}"
    print(f"RaktSetu running at {url}  (Ctrl+C to stop)")
    if open_browser: threading.Timer(0.6,lambda:webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")
