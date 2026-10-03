"""Authentication and role-based authorization for the RaktSetu demo."""
import hashlib, hmac, secrets
from datetime import datetime, timedelta
from .db import log

ROLES = {"admin", "hospital", "bank", "donor"}
ROLE_LABELS = {"admin":"Network Admin", "hospital":"Hospital Staff", "bank":"Blood Bank Staff", "donor":"Verified Donor"}
SESSION_HOURS = 12

class AuthError(Exception): pass
class ForbiddenError(Exception): pass

def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 60_000).hex()

def make_password(password):
    salt = secrets.token_bytes(16)
    return salt.hex() + "$" + _hash(password, salt)

def check_password(password, encoded):
    try:
        salt_hex, expected = encoded.split("$", 1)
        actual = _hash(password, bytes.fromhex(salt_hex))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False

def login(conn, username, password):
    row = conn.execute("SELECT * FROM users WHERE username=? AND active=1", (username.strip().lower(),)).fetchone()
    if not row or not check_password(password, row["password_hash"]):
        raise AuthError("Invalid username or password.")
    token = secrets.token_urlsafe(32)
    expires = datetime.now() + timedelta(hours=SESSION_HOURS)
    conn.execute("INSERT INTO user_sessions(token,user_id,expires_at) VALUES(?,?,?)", (token,row["id"],expires.isoformat(timespec="seconds")))
    conn.execute("UPDATE users SET last_login=? WHERE id=?", (datetime.now().isoformat(timespec="seconds"), row["id"]))
    log(conn, f"user:{row['id']}", "LOGIN", row["username"])
    conn.commit()
    return {"token": token, "expires_at": expires.isoformat(timespec="seconds"), **public_user(row)}

def public_user(row):
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"], "role": row["role"], "hospital_id": row["hospital_id"], "bank_id": row["bank_id"]}

def session(conn, token):
    if not token: raise AuthError("Authentication required.")
    row = conn.execute("""SELECT u.* FROM user_sessions s JOIN users u ON u.id=s.user_id
                          WHERE s.token=? AND s.expires_at>? AND u.active=1""", (token, datetime.now().isoformat(timespec="seconds"))).fetchone()
    if not row: raise AuthError("Session expired or invalid. Please sign in again.")
    return row

def require(conn, token, *roles):
    row = session(conn, token)
    if roles and row["role"] not in roles:
        raise ForbiddenError("Your account is not allowed to perform this action.")
    return row

def logout(conn, token):
    if token:
        conn.execute("DELETE FROM user_sessions WHERE token=?", (token,)); conn.commit()
