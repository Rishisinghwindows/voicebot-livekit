"""
Web frontend for AI Voice Assistant.
Serves an HTML page and a token endpoint for LiveKit connection.
"""

import os
import json
import uuid
import fcntl
import hashlib
import secrets
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from livekit.api import AccessToken, VideoGrants

SESSIONS_FILE = Path(__file__).parent / "sessions.json"
CONFIG_FILE = Path(__file__).parent / "admin_config.json"
AUTH_FILE = Path(__file__).parent / "admin_auth.json"
VERSIONS_FILE = Path(__file__).parent / "prompt_versions.json"
CRISIS_ALERTS_FILE = Path(__file__).parent / "crisis_alerts.json"
ENV_FILE = Path(__file__).parent / ".env"

# Keys that can be viewed/edited from the admin panel
ENV_EDITABLE_KEYS = [
    ("LIVEKIT_URL", "LiveKit URL"),
    ("PUBLIC_LIVEKIT_URL", "Public LiveKit URL"),
    ("LIVEKIT_API_KEY", "LiveKit API Key"),
    ("LIVEKIT_API_SECRET", "LiveKit API Secret"),
    ("DEEPGRAM_API_KEY", "Deepgram API Key"),
    ("OPENAI_API_KEY", "OpenAI API Key"),
    ("ELEVENLABS_API_KEY", "ElevenLabs API Key"),
    ("ELEVENLABS_VOICE_ID", "ElevenLabs Voice ID"),
    ("TWILIO_ACCOUNT_SID", "Twilio Account SID"),
    ("TWILIO_AUTH_TOKEN", "Twilio Auth Token"),
    ("AIRTABLE_PAT", "Airtable PAT"),
    ("AIRTABLE_BASE_ID", "Airtable Base ID"),
    ("MAX_CALL_DURATION_SECONDS", "Max Call Duration (s)"),
    ("ADMIN_PASSWORD", "Admin Password"),
]

# In-memory auth sessions: {token: expiry_timestamp}
_auth_sessions: dict[str, float] = {}
AUTH_SESSION_DURATION = 86400  # 24 hours

DEFAULT_CONFIG = {
    "agent_profile": {
        "agent_name": "Maya",
        "company_name": "UBudy",
        "role": "mental health companion",
        "greeting": "Hi, welcome to UBudy. I'm Maya. How are you feeling today?",
        "personality": "Warm, gentle, calm, non-judgmental, patient, and empathetic",
        "language_mode": "hinglish",
    },
    "knowledge_base": "",
    "system_prompt": "",
    "llm": {"model": "gpt-4o-mini", "temperature": 0.7},
    "tts": {"model": "gpt-4o-mini-tts", "voice": "nova"},
    "stt": {"model": "nova-2", "language": "hi"},
    "vad": {"activation_threshold": 0.35, "min_speech_duration": 0.05, "min_silence_duration": 0.4},
    "max_call_duration_seconds": 600,
    "safety_keywords_tier1": [
        "suicide", "kill myself", "want to die", "end my life", "self harm",
        "self-harm", "cut myself", "hurt myself", "take my life",
    ],
    "safety_keywords_tier2": [
        "hopeless", "no reason to live", "better off dead", "no point in living",
        "can't go on", "want to disappear", "nobody cares", "burden to everyone",
    ],
    "prompt_templates": [],
    "mcp_servers": [],
}


def _load_config() -> dict:
    """Load admin config, merging with defaults for missing keys."""
    config = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_FILE.exists():
            saved = json.loads(CONFIG_FILE.read_text())
            for key, val in saved.items():
                if isinstance(val, dict) and isinstance(config.get(key), dict):
                    config[key] = {**config[key], **val}
                else:
                    config[key] = val
    except (json.JSONDecodeError, OSError):
        pass
    return config


def _save_config(config: dict):
    """Save config to admin_config.json with file locking."""
    with open(CONFIG_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(config, f, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)


# =============================================================================
# AUTHENTICATION HELPERS
# =============================================================================

def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()


def _init_auth():
    """Initialize auth: hash ADMIN_PASSWORD on first run, or verify existing."""
    admin_pw = os.getenv("ADMIN_PASSWORD", "admin")
    if AUTH_FILE.exists():
        try:
            data = json.loads(AUTH_FILE.read_text())
            if data.get("password_hash") and data.get("salt"):
                return  # already initialized
        except (json.JSONDecodeError, OSError):
            pass
    salt = secrets.token_hex(16)
    pw_hash = _hash_password(admin_pw, salt)
    with open(AUTH_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump({"password_hash": pw_hash, "salt": salt}, f, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)
    print(f"[auth] Admin password initialized (from ADMIN_PASSWORD env var)")


def _verify_password(password: str) -> bool:
    try:
        data = json.loads(AUTH_FILE.read_text())
        expected = _hash_password(password, data["salt"])
        return secrets.compare_digest(expected, data["password_hash"])
    except (json.JSONDecodeError, OSError, KeyError):
        return False


def _create_auth_session() -> str:
    token = secrets.token_hex(32)
    _auth_sessions[token] = time.time() + AUTH_SESSION_DURATION
    return token


def _check_auth_token(token: str) -> bool:
    if not token or token not in _auth_sessions:
        return False
    if time.time() > _auth_sessions[token]:
        del _auth_sessions[token]
        return False
    return True


def _get_cookie_token(cookie_header: str) -> str:
    """Extract auth_token from Cookie header."""
    if not cookie_header:
        return ""
    try:
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        if "auth_token" in cookie:
            return cookie["auth_token"].value
    except Exception:
        pass
    return ""


# =============================================================================
# VERSION HISTORY HELPERS
# =============================================================================

def _load_versions() -> list[dict]:
    if not VERSIONS_FILE.exists():
        return []
    try:
        return json.loads(VERSIONS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_version(change_type: str, config: dict):
    """Auto-save a version entry. Max 50 versions."""
    versions = _load_versions()
    version_num = (versions[-1]["version"] + 1) if versions else 1
    versions.append({
        "version": version_num,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "type": change_type,
        "system_prompt": config.get("system_prompt", ""),
        "config_snapshot": config,
    })
    # Prune to max 50
    if len(versions) > 50:
        versions = versions[-50:]
    with open(VERSIONS_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(versions, f, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)


# =============================================================================
# CRISIS ALERTS HELPERS
# =============================================================================

def _load_alerts() -> list[dict]:
    if not CRISIS_ALERTS_FILE.exists():
        return []
    try:
        return json.loads(CRISIS_ALERTS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_alerts(alerts: list[dict]):
    with open(CRISIS_ALERTS_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(alerts, f, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)


# =============================================================================
# ENV FILE HELPERS
# =============================================================================

def _read_env_file() -> dict[str, str]:
    """Parse .env file and return key-value pairs (ignoring comments)."""
    result = {}
    if not ENV_FILE.exists():
        return result
    for line in ENV_FILE.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, _, val = stripped.partition("=")
            result[key.strip()] = val.strip()
    return result


def _mask_value(val: str) -> str:
    """Mask a value, showing only last 4 characters."""
    if not val:
        return ""
    if len(val) <= 4:
        return "****"
    return "*" * (len(val) - 4) + val[-4:]


def _get_env_for_api() -> list[dict]:
    """Get env keys with masked values for the API response."""
    raw = _read_env_file()
    editable_keys = {k for k, _ in ENV_EDITABLE_KEYS}
    result = []
    for key, label in ENV_EDITABLE_KEYS:
        val = raw.get(key, "")
        result.append({
            "key": key,
            "label": label,
            "masked_value": _mask_value(val),
            "is_set": bool(val),
        })
    return result


def _update_env_key(key: str, value: str):
    """Update a single key in the .env file, preserving structure."""
    editable_keys = {k for k, _ in ENV_EDITABLE_KEYS}
    if key not in editable_keys:
        raise ValueError(f"Key '{key}' is not editable")

    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    found = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            line_key = stripped.partition("=")[0].strip()
            if line_key == key:
                new_lines.append(f"{key}={value}")
                found = True
                continue
        new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}")

    with open(ENV_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write("\n".join(new_lines) + "\n")
        fcntl.flock(f, fcntl.LOCK_UN)


load_dotenv()

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
PUBLIC_LIVEKIT_URL = os.getenv("PUBLIC_LIVEKIT_URL", LIVEKIT_URL)
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
PORT = 8090


class Handler(SimpleHTTPRequestHandler):

    def _is_authed(self) -> bool:
        cookie_header = self.headers.get("Cookie", "")
        token = _get_cookie_token(cookie_header)
        return _check_auth_token(token)

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_401(self):
        self._send_json({"error": "Unauthorized"}, 401)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/token":
            self.send_token(parsed)
        elif parsed.path == "/login":
            self.send_login_page()
        elif parsed.path == "/dashboard":
            self.send_dashboard()
        elif parsed.path == "/admin":
            if not self._is_authed():
                self.send_response(302)
                self.send_header("Location", "/login")
                self.end_headers()
                return
            self.send_admin()
        elif parsed.path == "/api/sessions":
            self.send_sessions_api()
        elif parsed.path == "/api/config":
            if not self._is_authed():
                return self._send_401()
            self.send_config_api()
        elif parsed.path == "/api/versions":
            if not self._is_authed():
                return self._send_401()
            self._send_json(_load_versions())
        elif parsed.path == "/api/alerts":
            if not self._is_authed():
                return self._send_401()
            self._send_json(_load_alerts())
        elif parsed.path == "/api/alerts/count":
            alerts = _load_alerts()
            count = sum(1 for a in alerts if a.get("status") == "new")
            self._send_json({"count": count})
        elif parsed.path == "/api/knowledge-files":
            if not self._is_authed():
                return self._send_401()
            self.send_knowledge_files_api()
        elif parsed.path == "/api/env":
            if not self._is_authed():
                return self._send_401()
            self._send_json(_get_env_for_api())
        elif parsed.path == "/" or parsed.path == "":
            self.send_html()
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/login":
            self.handle_login()
        elif parsed.path == "/api/logout":
            self.handle_logout()
        elif parsed.path == "/api/config":
            if not self._is_authed():
                return self._send_401()
            self.handle_config_save()
        elif parsed.path == "/api/versions/rollback":
            if not self._is_authed():
                return self._send_401()
            self.handle_rollback()
        elif parsed.path == "/api/env":
            if not self._is_authed():
                return self._send_401()
            self.handle_env_update()
        else:
            self.send_error(404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/sessions/"):
            if not self._is_authed():
                return self._send_401()
            session_id = parsed.path[len("/api/sessions/"):]
            self.handle_session_delete(session_id)
        else:
            self.send_error(404)

    def do_PATCH(self):
        parsed = urlparse(self.path)
        # PATCH /api/alerts/<id>
        if parsed.path.startswith("/api/alerts/") and parsed.path != "/api/alerts/count":
            if not self._is_authed():
                return self._send_401()
            alert_id = parsed.path[len("/api/alerts/"):]
            self.handle_alert_update(alert_id)
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def send_token(self, parsed):
        params = parse_qs(parsed.query)
        user_id = f"user-{uuid.uuid4().hex[:8]}"
        room_name = f"voice-{uuid.uuid4().hex[:6]}"

        # Build user metadata from query params
        metadata = {}
        for key in ("name", "subject", "grade", "language", "type"):
            val = params.get(key, [""])[0].strip()
            if val:
                metadata[key] = val

        token_builder = (
            AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(user_id)
            .with_grants(VideoGrants(room_join=True, room=room_name))
        )
        if metadata:
            token_builder = token_builder.with_metadata(json.dumps(metadata))

        data = {
            "token": token_builder.to_jwt(),
            "url": PUBLIC_LIVEKIT_URL,
        }
        print(f"[token] user={user_id} room={room_name} metadata={metadata} url={PUBLIC_LIVEKIT_URL} client={self.client_address[0]}")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def send_login_page(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(LOGIN_PAGE.encode())

    def send_dashboard(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(DASHBOARD_PAGE.encode())

    def handle_login(self):
        try:
            body = json.loads(self._read_body())
            password = body.get("password", "")
            if _verify_password(password):
                token = _create_auth_session()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", f"auth_token={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={AUTH_SESSION_DURATION}")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode())
                print("[auth] Admin logged in")
            else:
                self._send_json({"error": "Invalid password"}, 401)
        except Exception as e:
            self._send_json({"error": str(e)}, 400)

    def handle_logout(self):
        cookie_header = self.headers.get("Cookie", "")
        token = _get_cookie_token(cookie_header)
        if token in _auth_sessions:
            del _auth_sessions[token]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", "auth_token=; Path=/; HttpOnly; Max-Age=0")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode())

    def handle_rollback(self):
        try:
            body = json.loads(self._read_body())
            target_version = body.get("version")
            versions = _load_versions()
            target = None
            for v in versions:
                if v["version"] == target_version:
                    target = v
                    break
            if not target:
                return self._send_json({"error": "Version not found"}, 404)
            # Restore config from snapshot
            restored = target["config_snapshot"]
            _save_config(restored)
            # Save a new rollback version entry
            _save_version("rollback", restored)
            self._send_json({"ok": True, "restored_version": target_version})
            print(f"[admin] Rolled back to version {target_version}")
        except Exception as e:
            self._send_json({"error": str(e)}, 400)

    def handle_alert_update(self, alert_id):
        try:
            body = json.loads(self._read_body())
            alerts = _load_alerts()
            found = False
            for a in alerts:
                if a.get("id") == alert_id:
                    if "status" in body:
                        a["status"] = body["status"]
                    if "notes" in body:
                        a["notes"] = body["notes"]
                    a["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    found = True
                    break
            if not found:
                return self._send_json({"error": "Alert not found"}, 404)
            _save_alerts(alerts)
            self._send_json({"ok": True})
            print(f"[admin] Alert {alert_id} updated: {body}")
        except Exception as e:
            self._send_json({"error": str(e)}, 400)

    def handle_env_update(self):
        try:
            body = json.loads(self._read_body())
            key = body.get("key", "")
            value = body.get("value", "")
            if not key:
                return self._send_json({"error": "Missing key"}, 400)
            _update_env_key(key, value)
            self._send_json({"ok": True})
            print(f"[admin] Env key updated: {key}")
        except ValueError as e:
            self._send_json({"error": str(e)}, 400)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def send_sessions_api(self):
        try:
            data = json.loads(SESSIONS_FILE.read_text()) if SESSIONS_FILE.exists() else []
        except (json.JSONDecodeError, OSError):
            data = []
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def send_admin(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(ADMIN_PAGE.encode())

    def send_config_api(self):
        config = _load_config()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(config).encode())

    def send_knowledge_files_api(self):
        kb_dir = Path(__file__).parent / "knowledge"
        files = []
        if kb_dir.exists():
            for f in sorted(kb_dir.iterdir()):
                if f.is_file() and f.suffix.lower() in (".txt", ".pdf"):
                    files.append({"name": f.name, "size": f.stat().st_size})
        self._send_json(files)

    def handle_config_save(self):
        try:
            body = json.loads(self._read_body())
            old_config = _load_config()
            _save_config(body)
            # Determine change type for version history
            if body.get("system_prompt") != old_config.get("system_prompt"):
                change_type = "prompt"
            else:
                change_type = "settings"
            _save_version(change_type, body)
            self._send_json({"ok": True})
            print(f"[admin] Config saved: {list(body.keys())} (version type: {change_type})")
        except Exception as e:
            self._send_json({"error": str(e)}, 400)

    def handle_session_delete(self, session_id):
        try:
            data = json.loads(SESSIONS_FILE.read_text()) if SESSIONS_FILE.exists() else []
            original_len = len(data)
            data = [s for s in data if s.get("id") != session_id]
            if len(data) == original_len:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Session not found"}).encode())
                return
            with open(SESSIONS_FILE, "w") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                json.dump(data, f, indent=2)
                fcntl.flock(f, fcntl.LOCK_UN)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
            print(f"[admin] Session deleted: {session_id}")
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def send_html(self):
        html = HTML_PAGE.replace("{{LIVEKIT_URL}}", PUBLIC_LIVEKIT_URL)
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        print(f"[web] {args[0]}")


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Voice AI</title>
<script>
/* Detect type from URL and set data-theme on html before paint */
(function(){
    var p=new URLSearchParams(window.location.search);
    if(p.get('type')==='legalAdviser') document.documentElement.setAttribute('data-theme','legal');
})();
</script>
<script src="https://cdn.jsdelivr.net/npm/livekit-client@2/dist/livekit-client.umd.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}

body{
    font-family:'Inter',-apple-system,sans-serif;
    background:radial-gradient(ellipse at 50% 40%,#0e0b1a 0%,#060608 55%,#030305 100%);
    min-height:100vh;overflow:hidden;color:#fff;
    display:flex;align-items:center;justify-content:center;
}

.scene{display:flex;flex-direction:column;align-items:center;gap:28px}

.heading{text-align:center;margin-bottom:8px}
.heading h1{
    font-size:28px;font-weight:600;letter-spacing:-.5px;
    background:linear-gradient(135deg,rgba(167,139,250,.9),rgba(99,102,241,.9),rgba(6,182,212,.8));
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;
    background-clip:text;
    animation:fadeSlideIn .8s ease-out both;
}
.heading p{
    font-size:14px;color:rgba(255,255,255,.25);
    margin-top:6px;font-weight:300;letter-spacing:.3px;
    animation:fadeSlideIn .8s ease-out .2s both;
}

/* Tagline with typewriter */
.tagline{
    text-align:center;max-width:340px;margin-top:-12px;
    min-height:44px;
    animation:fadeSlideIn .8s ease-out .4s both;
}
.tagline-inner{
    font-size:13px;font-weight:300;line-height:1.6;
    color:rgba(255,255,255,.30);letter-spacing:.2px;
}
.tagline-cursor{
    display:inline-block;width:1px;height:14px;
    background:rgba(167,139,250,.5);
    margin-left:2px;vertical-align:middle;
    animation:blink 1s step-end infinite;
}
[data-theme="legal"] .tagline-cursor{background:rgba(210,140,40,.5)}
[data-theme="legal"] .tagline-inner{color:rgba(245,190,80,.45)}

@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
@keyframes fadeSlideIn{
    from{opacity:0;transform:translateY(12px)}
    to{opacity:1;transform:translateY(0)}
}

.footer-text{
    text-align:center;margin-top:4px;
    font-size:12px;color:rgba(255,255,255,.10);
    font-weight:300;letter-spacing:.3px;
    max-width:300px;line-height:1.5;
    animation:fadeSlideIn .8s ease-out .8s both;
}

#st{animation:fadeSlideIn .8s ease-out .7s both}
.orb-wrap{animation:fadeScaleIn 1s ease-out .3s both}
@keyframes fadeScaleIn{
    from{opacity:0;transform:scale(.92)}
    to{opacity:1;transform:scale(1)}
}

/* ── Floating particles ── */
.ptc{
    position:fixed;width:2px;height:2px;border-radius:50%;
    pointer-events:none;opacity:0;
}
@keyframes floatUp{
    0%{transform:translateY(0) translateX(0);opacity:0}
    8%{opacity:1}
    92%{opacity:1}
    100%{transform:translateY(-110vh) translateX(80px);opacity:0}
}

/* ── Orb system (responsive) ── */
:root{
    --orb-size:min(284px, 60vw);
    --ring-sharp:min(296px, 63vw);
    --ring-soft:min(320px, 68vw);
    --wrap-size:min(380px, 80vw);
    --glow-far:min(520px, 110vw);
    --glow-mid:min(400px, 85vw);
}

.orb-wrap{
    position:relative;
    width:var(--wrap-size);height:var(--wrap-size);
    display:flex;align-items:center;justify-content:center;
}

/* Glow layers */
.glow{position:absolute;border-radius:50%;pointer-events:none}
.glow-far{
    width:var(--glow-far);height:var(--glow-far);
    background:radial-gradient(circle,rgba(139,92,246,.18) 0%,transparent 65%);
    filter:blur(40px);
    animation:glowBreathe 5s ease-in-out infinite;
}
.glow-mid{
    width:var(--glow-mid);height:var(--glow-mid);
    background:radial-gradient(circle,rgba(139,92,246,.28) 0%,transparent 55%);
    filter:blur(20px);
    animation:glowBreathe 5s ease-in-out infinite 1.2s;
}
@keyframes glowBreathe{
    0%,100%{transform:scale(1);opacity:.75}
    50%{transform:scale(1.06);opacity:1}
}

/* Rotating border ring */
@property --ba{syntax:'<angle>';initial-value:0deg;inherits:false}
.ring{
    position:absolute;border-radius:50%;
    background:conic-gradient(from var(--ba),#8B5CF6,#6366F1,#3B82F6,#06B6D4,#A78BFA,#8B5CF6);
    animation:rspin 5s linear infinite;
}
.ring-sharp{width:var(--ring-sharp);height:var(--ring-sharp);opacity:.65}
.ring-soft{width:var(--ring-soft);height:var(--ring-soft);filter:blur(14px);opacity:.3}
@keyframes rspin{to{--ba:360deg}}

/* Main orb */
.orb{
    position:relative;
    width:var(--orb-size);height:var(--orb-size);
    border-radius:50%;
    overflow:hidden;
    clip-path:circle(50%);
    -webkit-clip-path:circle(50%);
    z-index:1;
    box-shadow:
        0 0 60px 15px rgba(139,92,246,.30),
        0 0 120px 50px rgba(139,92,246,.12),
        0 0 220px 100px rgba(139,92,246,.05);
    transition:box-shadow 2s ease,transform .15s ease-out;
}

.orb-bg{
    position:absolute;inset:0;
    background:radial-gradient(circle at 48% 45%,#1e1245 0%,#0f0b20 50%,#080812 100%);
}

/* Gradient blobs inside orb (use % for responsive sizing) */
.blob{
    position:absolute;border-radius:50%;
    filter:blur(28px);
    mix-blend-mode:screen;
    will-change:transform;
    transition:background 2.5s ease;
}
.b1{width:85%;height:85%;background:rgba(139,92,246,.9);top:-30%;left:-18%}
.b2{width:74%;height:74%;background:rgba(99,102,241,.8);bottom:-22%;right:-16%}
.b3{width:67%;height:67%;background:rgba(59,130,246,.7);top:18%;left:22%}
.b4{width:56%;height:56%;background:rgba(6,182,212,.6);bottom:0%;left:-8%}
.b5{width:46%;height:46%;background:rgba(167,139,250,.5);top:35%;right:-5%}

/* Glass specular + edge depth */
.shine{
    position:absolute;inset:0;border-radius:50%;
    background:
        radial-gradient(circle at 32% 26%,rgba(255,255,255,.25),transparent 35%),
        radial-gradient(ellipse at 50% 50%,transparent 52%,rgba(0,0,0,.40) 100%);
    pointer-events:none;
}

/* Icon */
.icon{position:absolute;z-index:2;pointer-events:none}
.icon svg{
    width:30px;height:30px;
    color:rgba(255,255,255,.85);
    filter:drop-shadow(0 2px 10px rgba(0,0,0,.5));
    transition:all .4s;
}

.hit{
    position:absolute;z-index:3;
    width:var(--orb-size);height:var(--orb-size);
    border-radius:50%;border:none;
    background:transparent;cursor:pointer;outline:none;
    -webkit-tap-highlight-color:transparent;
}
.hit:disabled{cursor:not-allowed}

/* Status */
#st{
    font-size:14px;font-weight:400;letter-spacing:.5px;
    text-align:center;min-height:22px;
    transition:all .6s;
    color:rgba(255,255,255,.18);
}
#st.on{color:rgba(167,139,250,.6)}
#st.sp{color:rgba(52,211,153,.6)}

.tmr{
    font-size:11px;color:rgba(255,255,255,.08);
    margin-top:6px;text-align:center;
    font-variant-numeric:tabular-nums;display:none;
}
.tmr.v{display:block}

.dots{display:inline-flex;gap:4px;margin-left:4px}
.dots span{
    width:4px;height:4px;border-radius:50%;
    background:rgba(167,139,250,.5);
    animation:db 1.4s ease-in-out infinite;
}
.dots span:nth-child(2){animation-delay:.2s}
.dots span:nth-child(3){animation-delay:.4s}
@keyframes db{0%,80%,100%{transform:translateY(0);opacity:.3}40%{transform:translateY(-5px);opacity:1}}

/* ═══ Speaking state ═══ */
.orb-wrap.speaking .orb{
    box-shadow:
        0 0 60px 15px rgba(20,241,149,.30),
        0 0 120px 50px rgba(20,241,149,.12),
        0 0 220px 100px rgba(20,241,149,.05);
}
.orb-wrap.speaking .b1{background:rgba(20,241,149,.9)}
.orb-wrap.speaking .b2{background:rgba(6,182,212,.8)}
.orb-wrap.speaking .b3{background:rgba(52,211,153,.7)}
.orb-wrap.speaking .b4{background:rgba(34,211,238,.65)}
.orb-wrap.speaking .b5{background:rgba(20,241,149,.5)}
.orb-wrap.speaking .glow-far{background:radial-gradient(circle,rgba(20,241,149,.18) 0%,transparent 65%)}
.orb-wrap.speaking .glow-mid{background:radial-gradient(circle,rgba(20,241,149,.28) 0%,transparent 55%)}
.orb-wrap.speaking .ring-sharp{
    background:conic-gradient(from var(--ba),#14F195,#06B6D4,#3B82F6,#22D3EE,#10B981,#14F195);
}
.orb-wrap.speaking .ring-soft{
    background:conic-gradient(from var(--ba),#14F195,#06B6D4,#3B82F6,#22D3EE,#10B981,#14F195);
}
.orb-wrap.speaking .orb-bg{
    background:radial-gradient(circle at 48% 45%,#0a1a1a 0%,#081215 50%,#060a10 100%);
}

/* ═══ Legal Adviser Theme (warm amber/golden) ═══ */
[data-theme="legal"] body{
    background:radial-gradient(ellipse at 50% 40%,#1a120a 0%,#0d0804 55%,#050302 100%);
}
[data-theme="legal"] .heading h1{
    background:linear-gradient(135deg,rgba(245,180,60,.95),rgba(220,140,40,.9),rgba(200,120,30,.8));
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
[data-theme="legal"] .heading p{color:rgba(245,190,80,.50)}

/* Orb — idle state */
[data-theme="legal"] .glow-far{background:radial-gradient(circle,rgba(210,140,40,.20) 0%,transparent 65%)}
[data-theme="legal"] .glow-mid{background:radial-gradient(circle,rgba(210,140,40,.30) 0%,transparent 55%)}
[data-theme="legal"] .ring-sharp{
    background:conic-gradient(from var(--ba),#D4880A,#C87020,#E8A020,#B8860B,#DAA520,#D4880A);
}
[data-theme="legal"] .ring-soft{
    background:conic-gradient(from var(--ba),#D4880A,#C87020,#E8A020,#B8860B,#DAA520,#D4880A);
}
[data-theme="legal"] .orb{
    box-shadow:
        0 0 60px 15px rgba(210,140,40,.30),
        0 0 120px 50px rgba(210,140,40,.12),
        0 0 220px 100px rgba(210,140,40,.05);
}
[data-theme="legal"] .orb-bg{
    background:radial-gradient(circle at 48% 45%,#1a1008 0%,#120a04 50%,#080502 100%);
}
[data-theme="legal"] .b1{background:rgba(210,140,40,.9)}
[data-theme="legal"] .b2{background:rgba(180,110,30,.8)}
[data-theme="legal"] .b3{background:rgba(220,160,50,.7)}
[data-theme="legal"] .b4{background:rgba(245,180,60,.6)}
[data-theme="legal"] .b5{background:rgba(200,130,35,.5)}

/* Orb — speaking state */
[data-theme="legal"] .orb-wrap.speaking .orb{
    box-shadow:
        0 0 60px 15px rgba(245,200,80,.30),
        0 0 120px 50px rgba(245,200,80,.12),
        0 0 220px 100px rgba(245,200,80,.05);
}
[data-theme="legal"] .orb-wrap.speaking .b1{background:rgba(245,200,80,.9)}
[data-theme="legal"] .orb-wrap.speaking .b2{background:rgba(220,170,50,.8)}
[data-theme="legal"] .orb-wrap.speaking .b3{background:rgba(255,210,90,.7)}
[data-theme="legal"] .orb-wrap.speaking .b4{background:rgba(200,160,40,.65)}
[data-theme="legal"] .orb-wrap.speaking .b5{background:rgba(245,200,80,.5)}
[data-theme="legal"] .orb-wrap.speaking .glow-far{background:radial-gradient(circle,rgba(245,200,80,.20) 0%,transparent 65%)}
[data-theme="legal"] .orb-wrap.speaking .glow-mid{background:radial-gradient(circle,rgba(245,200,80,.30) 0%,transparent 55%)}
[data-theme="legal"] .orb-wrap.speaking .ring-sharp{
    background:conic-gradient(from var(--ba),#F5C850,#DAA520,#E8B830,#C8A020,#F0D060,#F5C850);
}
[data-theme="legal"] .orb-wrap.speaking .ring-soft{
    background:conic-gradient(from var(--ba),#F5C850,#DAA520,#E8B830,#C8A020,#F0D060,#F5C850);
}
[data-theme="legal"] .orb-wrap.speaking .orb-bg{
    background:radial-gradient(circle at 48% 45%,#1a1508 0%,#120e04 50%,#080602 100%);
}

/* Status text */
[data-theme="legal"] #st{color:rgba(245,190,80,.40)}
[data-theme="legal"] #st.on{color:rgba(230,170,50,.70)}
[data-theme="legal"] #st.sp{color:rgba(255,210,90,.70)}
[data-theme="legal"] .dots span{background:rgba(230,170,50,.6)}
[data-theme="legal"] .tmr{color:rgba(245,190,80,.20)}
[data-theme="legal"] .footer-text{color:rgba(245,190,80,.25)}
</style>
</head>
<body>
<div class="scene">
    <div class="heading">
        <h1>Voice AI Assistant</h1>
        <p>Talk in Hindi or English — powered by real-time AI</p>
    </div>
    <div class="tagline"><span class="tagline-inner" id="tagTxt"></span><span class="tagline-cursor" id="tagCur"></span></div>
    <div class="orb-wrap" id="orbWrap">
        <div class="glow glow-far" id="glowFar"></div>
        <div class="glow glow-mid" id="glowMid"></div>
        <div class="ring ring-soft"></div>
        <div class="ring ring-sharp"></div>
        <div class="orb" id="orb">
            <div class="orb-bg"></div>
            <div class="blob b1" id="b1"></div>
            <div class="blob b2" id="b2"></div>
            <div class="blob b3" id="b3"></div>
            <div class="blob b4" id="b4"></div>
            <div class="blob b5" id="b5"></div>
            <div class="shine"></div>
        </div>
        <div class="icon">
            <svg id="mic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                <line x1="12" y1="19" x2="12" y2="23"/>
                <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
            <svg id="stp" style="display:none" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2"/>
            </svg>
        </div>
        <button class="hit" id="btn" onclick="tog()"></button>
    </div>
    <div>
        <div id="st">Tap the orb to start talking</div>
        <div class="tmr" id="tmr">00:00</div>
    </div>
    <div class="footer-text">Ask anything — available 24/7 in English and Hindi</div>
</div>

<script>
const LK=window.LivekitClient;
let room=null,conn=false,tInt=null,sec=0,bSt='idle',spHold=0;

/* Audio */
let uCtx,uAn,uSrc,uArr,bCtx,bAn,bSrc,bArr;

/* DOM */
const orbEl=document.getElementById('orb');
const orbWrap=document.getElementById('orbWrap');
const glowFar=document.getElementById('glowFar');
const glowMid=document.getElementById('glowMid');
const blobs=[
    document.getElementById('b1'),document.getElementById('b2'),
    document.getElementById('b3'),document.getElementById('b4'),
    document.getElementById('b5')
];

/* Blob movement configs */
const drifts=[
    {xs:.35,xo:0,   ys:.28,yo:.5,  xA:55,yA:45},
    {xs:.25,xo:1.5, ys:.32,yo:2.0, xA:50,yA:50},
    {xs:.30,xo:3.0, ys:.22,yo:3.5, xA:40,yA:40},
    {xs:.20,xo:4.5, ys:.35,yo:5.0, xA:45,yA:35},
    {xs:.28,xo:5.5, ys:.25,yo:6.2, xA:35,yA:45}
];

/* Detect agent type from URL */
var urlParams=new URLSearchParams(window.location.search);
var agentType=urlParams.get('type')||'';
var isLegal=agentType==='legalAdviser';
var userLang=(urlParams.get('language')||'').toLowerCase();
var isHindi=userLang==='hindi'||userLang==='hi'||userLang==='hinglish';

/* Update heading and footer for legal adviser */
if(isLegal){
    var h1=document.querySelector('.heading h1');
    var sub=document.querySelector('.heading p');
    var foot=document.querySelector('.footer-text');
    if(isHindi){
        h1.textContent='AI Legal Guru';
        sub.textContent='भारतीय कानून के लिए आपका AI मार्गदर्शक';
        foot.textContent='BNS, IPC और संविधान — कुछ भी पूछें';
        document.getElementById('st').textContent='बात शुरू करने के लिए ऑर्ब दबाएं';
    }else{
        h1.textContent='AI Legal Guru';
        sub.textContent='Your AI-powered guide to Indian law';
        foot.textContent='Ask about BNS, IPC, Constitution & more — 24/7';
        document.getElementById('st').textContent='Tap the orb to ask a legal question';
    }
    document.title='AI Legal Guru';
}

/* Typewriter tagline */
(function typewriter(){
    var taglines;
    if(isLegal&&isHindi){
        taglines=[
            'IPC, BNS और संविधान के बारे में पूछें',
            'कानूनी धाराओं की जानकारी पाएं',
            'अपने अधिकार जानें, कानून समझें'
        ];
    }else if(isLegal){
        taglines=[
            'Ask about IPC, BNS & Indian Constitution',
            'Get instant answers on legal sections',
            'Understand your rights under Indian law'
        ];
    }else if(isHindi){
        taglines=[
            'Main Maya hoon, aapki mental health companion',
            'Apne feelings share karein, main sun rahi hoon',
            'Breathing exercises aur coping tips ke liye poochein'
        ];
    }else{
        taglines=[
            "I'm Maya, your mental health companion",
            'Share how you feel, I\'m here to listen',
            'Ask about breathing exercises & coping tips'
        ];
    }
    var el=document.getElementById('tagTxt');
    var cur=document.getElementById('tagCur');
    var idx=0,charIdx=0,deleting=false,pause=0;
    function tick(){
        if(pause>0){pause--;setTimeout(tick,50);return}
        var txt=taglines[idx];
        if(!deleting){
            charIdx++;
            el.textContent=txt.substring(0,charIdx);
            if(charIdx>=txt.length){pause=60;deleting=true;}
            setTimeout(tick,35+Math.random()*25);
        }else{
            charIdx--;
            el.textContent=txt.substring(0,charIdx);
            if(charIdx<=0){deleting=false;idx=(idx+1)%taglines.length;pause=10;}
            setTimeout(tick,20);
        }
    }
    setTimeout(tick,800);
})();

/* Floating background particles */
(function createParticles(){
    for(var i=0;i<25;i++){
        var p=document.createElement('div');
        p.className='ptc';
        p.style.left=Math.random()*100+'vw';
        p.style.top=Math.random()*100+'vh';
        p.style.width=(1+Math.random()*2)+'px';
        p.style.height=p.style.width;
        if(isLegal){
            p.style.background='rgba('+(160+Math.random()*80)+','+(100+Math.random()*60)+','+(20+Math.random()*30)+','+(0.15+Math.random()*0.2)+')';
        }else{
            p.style.background='rgba('+(100+Math.random()*80)+','+(80+Math.random()*60)+','+(200+Math.random()*55)+','+(0.15+Math.random()*0.2)+')';
        }
        p.style.animation='floatUp '+(18+Math.random()*20)+'s linear infinite';
        p.style.animationDelay=(-Math.random()*30)+'s';
        document.body.appendChild(p);
    }
})();

function setBSt(s){
    if(bSt===s)return;bSt=s;
    var st=document.getElementById('st');
    if(s==='speaking'){
        st.textContent=isLegal&&isHindi?'बोल रहा है...':'Speaking...';
        st.className='sp';orbWrap.classList.add('speaking');
    }else if(s==='listening'){
        st.textContent=isLegal&&isHindi?'सुन रहा है...':'Listening...';
        st.className='on';orbWrap.classList.remove('speaking');
    }
}

function getLevel(an,arr){
    if(!an||!arr)return 0;
    an.getByteFrequencyData(arr);
    var s=0;for(var i=0;i<arr.length;i++)s+=arr[i];
    return Math.min(1,s/arr.length/100);
}

/* ── Animation loop ── */
var t0=performance.now(),speedMul=1,smoothAudio=0;

function animate(){
    var time=(performance.now()-t0)/1000;

    var bLvl=getLevel(bAn,bArr);
    var uLvl=getLevel(uAn,uArr);

    /* Auto-detect speaking vs listening */
    if(conn&&bSt!=='connecting'){
        if(bLvl>.06){spHold=25;if(bSt!=='speaking')setBSt('speaking');}
        else if(spHold>0)spHold--;
        else if(bSt!=='listening')setBSt('listening');
    }

    var aLvl=bSt==='speaking'?bLvl:bSt==='listening'?uLvl:0;
    smoothAudio+=(aLvl-smoothAudio)*.12;

    /* Speed multiplier */
    var targetSpd=bSt==='connecting'?2.8:bSt==='speaking'?1.6+smoothAudio*1.5:1;
    speedMul+=(targetSpd-speedMul)*.025;

    /* Move blobs */
    for(var i=0;i<5;i++){
        var d=drifts[i];
        var t=time*speedMul;
        var x=Math.sin(t*d.xs+d.xo)*d.xA;
        var y=Math.cos(t*d.ys+d.yo)*d.yA;
        var sc=1+smoothAudio*.12;
        blobs[i].style.transform='translate('+x+'%,'+y+'%) scale('+sc+')';
    }

    /* Audio-reactive orb scale + glow */
    orbEl.style.transform='scale('+(1+smoothAudio*.045)+')';
    glowFar.style.transform='scale('+(1+smoothAudio*.15)+')';
    glowMid.style.transform='scale('+(1+smoothAudio*.10)+')';

    requestAnimationFrame(animate);
}
animate();

/* ── Audio setup ── */
function setupUA(){
    try{var pub=room.localParticipant.getTrackPublication(LK.Track.Source.Microphone);
    if(!pub||!pub.track)return;var stream=new MediaStream([pub.track.mediaStreamTrack]);
    uCtx=new AudioContext();uAn=uCtx.createAnalyser();uAn.fftSize=256;uAn.smoothingTimeConstant=.8;
    uSrc=uCtx.createMediaStreamSource(stream);uSrc.connect(uAn);uArr=new Uint8Array(uAn.frequencyBinCount);
    }catch(e){console.warn('UA:',e)}
}
function setupBA(trk){
    try{var stream=new MediaStream([trk]);bCtx=new AudioContext();bAn=bCtx.createAnalyser();
    bAn.fftSize=256;bAn.smoothingTimeConstant=.8;bSrc=bCtx.createMediaStreamSource(stream);
    bSrc.connect(bAn);bArr=new Uint8Array(bAn.frequencyBinCount);
    }catch(e){console.warn('BA:',e)}
}
function tearA(){
    [uSrc,bSrc].forEach(function(s){if(s)s.disconnect()});
    [uCtx,bCtx].forEach(function(c){if(c)c.close().catch(function(){})});
    uCtx=uAn=uSrc=uArr=null;bCtx=bAn=bSrc=bArr=null;
}

/* Timer */
function startT(){sec=0;document.getElementById('tmr').classList.add('v');updT();tInt=setInterval(function(){sec++;updT()},1000)}
function stopT(){clearInterval(tInt);document.getElementById('tmr').classList.remove('v')}
function updT(){document.getElementById('tmr').textContent=String(Math.floor(sec/60)).padStart(2,'0')+':'+String(sec%60).padStart(2,'0')}

function tog(){if(conn)disc();else connect()}

function connect(){
    var btn=document.getElementById('btn'),st=document.getElementById('st');
    btn.disabled=true;
    st.innerHTML='Connecting<span class="dots"><span></span><span></span><span></span></span>';
    st.className='';bSt='connecting';

    console.log('[LK] Fetching token...');
    var tokenUrl='/token'+window.location.search;
    fetch(tokenUrl).then(function(r){return r.json()}).then(function(data){
        console.log('[LK] Token received, connecting to:', data.url);
        room=new LK.Room({audioCaptureDefaults:{autoGainControl:true,noiseSuppression:true,echoCancellation:true}});
        room.on(LK.RoomEvent.TrackSubscribed,function(track){
            console.log('[LK] Track subscribed:', track.kind, track.source);
            if(track.kind==='audio'){var el=track.attach();el.style.display='none';document.body.appendChild(el);setupBA(track.mediaStreamTrack);}
        });
        room.on(LK.RoomEvent.Disconnected,function(reason){console.log('[LK] Disconnected, reason:', reason);disc()});
        room.on(LK.RoomEvent.Reconnecting,function(){console.log('[LK] Reconnecting...')});
        room.on(LK.RoomEvent.Reconnected,function(){console.log('[LK] Reconnected')});
        room.on(LK.RoomEvent.SignalConnected,function(){console.log('[LK] Signal connected (WebSocket OK)')});
        room.on(LK.RoomEvent.MediaDevicesError,function(e){console.error('[LK] Media device error:', e)});
        room.on(LK.RoomEvent.ConnectionQualityChanged,function(q,p){console.log('[LK] Connection quality:', q, 'participant:', p.identity)});
        room.on(LK.RoomEvent.ParticipantConnected,function(p){console.log('[LK] Participant joined:', p.identity)});

        /* Monitor ICE connection state */
        room.on(LK.RoomEvent.SignalConnected, function(){
            console.log('[LK] Signal connected - checking PC state...');
            try {
                var engine = room.engine;
                if (engine && engine.pcManager) {
                    var pcs = [engine.pcManager.publisher, engine.pcManager.subscriber];
                    pcs.forEach(function(pc, idx) {
                        if (pc && pc.pc) {
                            var label = idx === 0 ? 'publisher' : 'subscriber';
                            pc.pc.onicecandidate = function(ev) {
                                if (ev.candidate) {
                                    console.log('[ICE][' + label + '] candidate:', ev.candidate.type, ev.candidate.protocol, ev.candidate.address + ':' + ev.candidate.port);
                                } else {
                                    console.log('[ICE][' + label + '] gathering complete');
                                }
                            };
                            pc.pc.oniceconnectionstatechange = function() {
                                console.log('[ICE][' + label + '] state:', pc.pc.iceConnectionState);
                            };
                            pc.pc.onconnectionstatechange = function() {
                                console.log('[PC][' + label + '] state:', pc.pc.connectionState);
                            };
                            pc.pc.onicegatheringstatechange = function() {
                                console.log('[ICE][' + label + '] gathering:', pc.pc.iceGatheringState);
                            };
                        }
                    });
                }
            } catch(e) { console.warn('[LK] Could not attach ICE monitors:', e); }
        });

        return room.connect(data.url,data.token).then(function(){
            console.log('[LK] Room connected, enabling mic...');
            return room.localParticipant.setMicrophoneEnabled(true);
        });
    }).then(function(){
        console.log('[LK] Mic enabled, fully connected!');
        conn=true;btn.disabled=false;
        document.getElementById('mic').style.display='none';
        document.getElementById('stp').style.display='block';
        setBSt('listening');setupUA();startT();
    }).catch(function(e){
        console.error('[LK] Connection error:', e.message || e);
        console.error('[LK] Error details:', e);
        st.textContent='Connection failed: ' + (e.message || 'unknown error');st.className='';
        btn.disabled=false;bSt='idle';
    });
}

function disc(){
    if(room){room.disconnect();room=null}conn=false;
    document.getElementById('mic').style.display='block';
    document.getElementById('stp').style.display='none';
    document.getElementById('st').textContent=isLegal?(isHindi?'बात शुरू करने के लिए ऑर्ब दबाएं':'Tap the orb to ask a legal question'):'Tap to start';
    document.getElementById('st').className='';
    orbWrap.classList.remove('speaking');
    tearA();bSt='idle';spHold=0;stopT();
}
</script>
</body>
</html>
"""

LOGIN_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Login - Voice AI Admin</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{
    font-family:'Inter',-apple-system,sans-serif;
    background:#f5f5f7;
    min-height:100vh;color:#1a1a2e;
    display:flex;align-items:center;justify-content:center;
}
.login-card{
    background:#fff;border:1px solid rgba(0,0,0,.08);
    border-radius:18px;padding:40px;width:380px;max-width:90vw;
    box-shadow:0 4px 24px rgba(0,0,0,.06);
}
.login-card h1{
    font-size:22px;font-weight:600;text-align:center;margin-bottom:6px;
    background:linear-gradient(135deg,#7c3aed,#4f46e5,#0891b2);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
.login-card p{font-size:13px;color:rgba(0,0,0,.4);text-align:center;margin-bottom:28px}
.field{margin-bottom:20px}
.field label{display:block;font-size:12px;color:rgba(0,0,0,.45);font-weight:500;margin-bottom:8px;letter-spacing:.5px;text-transform:uppercase}
.field input{
    width:100%;background:rgba(0,0,0,.03);border:1px solid rgba(0,0,0,.12);
    border-radius:10px;padding:12px 16px;color:#1a1a2e;font-size:14px;font-family:inherit;outline:none;
    transition:border-color .2s;
}
.field input:focus{border-color:rgba(124,58,237,.5)}
.login-btn{
    width:100%;padding:12px;border-radius:10px;font-size:14px;font-weight:600;
    border:none;cursor:pointer;font-family:inherit;
    background:linear-gradient(135deg,#7c3aed,#4f46e5);color:#fff;
    transition:opacity .2s,transform .1s;
}
.login-btn:hover{opacity:.9;transform:translateY(-1px)}
.login-btn:disabled{opacity:.5;cursor:not-allowed;transform:none}
.error-msg{
    margin-top:16px;padding:10px 14px;border-radius:8px;font-size:13px;
    background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.15);color:#dc2626;
    display:none;text-align:center;
}
</style>
</head>
<body>
<div class="login-card">
    <h1>Admin Login</h1>
    <p>Enter password to access the admin panel</p>
    <div class="field">
        <label>Password</label>
        <input type="password" id="pw" placeholder="Enter admin password" autofocus
               onkeydown="if(event.key==='Enter')doLogin()">
    </div>
    <button class="login-btn" id="loginBtn" onclick="doLogin()">Sign In</button>
    <div class="error-msg" id="err"></div>
</div>
<script>
function doLogin(){
    var btn=document.getElementById('loginBtn');
    var pw=document.getElementById('pw').value;
    var err=document.getElementById('err');
    if(!pw){err.textContent='Please enter a password';err.style.display='block';return;}
    btn.disabled=true;err.style.display='none';
    fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})})
    .then(function(r){return r.json().then(function(d){return{status:r.status,data:d}})})
    .then(function(res){
        if(res.status===200&&res.data.ok){window.location.href='/admin';}
        else{err.textContent=res.data.error||'Login failed';err.style.display='block';btn.disabled=false;}
    }).catch(function(){err.textContent='Connection error';err.style.display='block';btn.disabled=false;});
}
</script>
</body>
</html>
"""

DASHBOARD_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Dashboard - Voice AI</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{
    font-family:'Inter',-apple-system,sans-serif;
    background:#060608;color:#fff;min-height:100vh;
}
.top-bar{
    display:flex;align-items:center;justify-content:space-between;
    padding:20px 32px;border-bottom:1px solid rgba(255,255,255,.06);
}
.top-bar h1{
    font-size:22px;font-weight:600;
    background:linear-gradient(135deg,rgba(167,139,250,.9),rgba(99,102,241,.9),rgba(6,182,212,.8));
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
.top-bar a{
    color:rgba(167,139,250,.7);text-decoration:none;font-size:13px;font-weight:500;
    transition:color .2s;
}
.top-bar a:hover{color:rgba(167,139,250,1)}
.container{max-width:1100px;margin:0 auto;padding:28px 32px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:32px}
.card{
    background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);
    border-radius:14px;padding:22px 24px;
}
.card .label{font-size:12px;color:rgba(255,255,255,.35);font-weight:500;letter-spacing:.5px;text-transform:uppercase}
.card .value{font-size:32px;font-weight:700;margin-top:6px;letter-spacing:-.5px}
.card .sub{font-size:12px;color:rgba(255,255,255,.2);margin-top:4px}
.card:nth-child(1) .value{color:#a78bfa}
.card:nth-child(2) .value{color:#6366f1}
.card:nth-child(3) .value{color:#06b6d4}
.card:nth-child(4) .value{color:#14f195}
.tbl-wrap{
    background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.06);
    border-radius:14px;overflow:hidden;
}
.tbl-head{padding:18px 24px;border-bottom:1px solid rgba(255,255,255,.06);display:flex;align-items:center;justify-content:space-between}
.tbl-head h2{font-size:15px;font-weight:600;color:rgba(255,255,255,.7)}
.tbl-head .refresh{font-size:11px;color:rgba(255,255,255,.2)}
table{width:100%;border-collapse:collapse}
th{
    text-align:left;padding:12px 24px;font-size:11px;font-weight:600;
    color:rgba(255,255,255,.3);letter-spacing:.5px;text-transform:uppercase;
    border-bottom:1px solid rgba(255,255,255,.04);
}
td{
    padding:14px 24px;font-size:13px;color:rgba(255,255,255,.6);
    border-bottom:1px solid rgba(255,255,255,.03);
}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(255,255,255,.015)}
.badge{
    display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:500;
}
.badge.active{background:rgba(20,241,149,.12);color:#14f195}
.badge.completed{background:rgba(167,139,250,.12);color:#a78bfa}
.empty{text-align:center;padding:48px 24px;color:rgba(255,255,255,.15);font-size:14px}
.filter-bar{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}
.filter-bar input{
    flex:1;min-width:200px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);
    border-radius:8px;padding:10px 14px;color:#fff;font-size:13px;font-family:inherit;outline:none;
    transition:border-color .2s;
}
.filter-bar input:focus{border-color:rgba(167,139,250,.5)}
.filter-bar select{
    background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);
    border-radius:8px;padding:10px 14px;color:#fff;font-size:13px;font-family:inherit;outline:none;
}
.filter-bar select option{background:#1a1a2e;color:#fff}
</style>
</head>
<body>
<div class="top-bar">
    <h1>Voice AI Dashboard</h1>
    <a href="/">&#8592; Back to Voice UI</a>
</div>
<div class="container">
    <div class="cards">
        <div class="card"><div class="label">Total Sessions</div><div class="value" id="totalSessions">-</div><div class="sub">All time</div></div>
        <div class="card"><div class="label">Unique Users</div><div class="value" id="uniqueUsers">-</div><div class="sub">By name</div></div>
        <div class="card"><div class="label">Avg Duration</div><div class="value" id="avgDuration">-</div><div class="sub">Completed sessions</div></div>
        <div class="card"><div class="label">Sessions Today</div><div class="value" id="todaySessions">-</div><div class="sub" id="todayDate">-</div></div>
        <div class="card"><div class="label">Crisis Alerts</div><div class="value" id="crisisCount" style="color:#ef4444">-</div><div class="sub">Unreviewed</div></div>
        <div class="card"><div class="label">Total Cost</div><div class="value" id="totalCost" style="color:#f472b6">-</div><div class="sub">INR (all sessions)</div></div>
    </div>
    <div class="filter-bar">
        <input type="text" id="dSearch" placeholder="Search by name, topic, or language..." oninput="renderTable()">
        <select id="dStatusFilter" onchange="renderTable()">
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="completed">Completed</option>
        </select>
        <select id="dLangFilter" onchange="renderTable()">
            <option value="all">All Languages</option>
        </select>
    </div>
    <div class="tbl-wrap">
        <div class="tbl-head">
            <h2>Recent Sessions</h2>
            <span class="refresh" id="refreshNote">Auto-refreshes every 30s</span>
        </div>
        <table>
            <thead><tr><th>Name</th><th>Topic</th><th>Language</th><th>Duration</th><th>Cost (INR)</th><th>Status</th><th>Time</th></tr></thead>
            <tbody id="tbody"></tbody>
        </table>
        <div class="empty" id="empty" style="display:none">No sessions yet. Start a voice conversation to see data here.</div>
    </div>
</div>
<script>
function fmt(s){
    if(s==null)return'-';
    var m=Math.floor(s/60),ss=s%60;
    return m>0?m+'m '+ss+'s':ss+'s';
}
function fmtAvg(s){
    if(isNaN(s))return'-';
    var m=Math.floor(s/60),ss=Math.round(s%60);
    return m>0?m+'m '+ss+'s':ss+'s';
}
function relTime(iso){
    if(!iso)return'-';
    var d=new Date(iso),now=new Date(),diff=Math.floor((now-d)/1000);
    if(diff<60)return 'Just now';
    if(diff<3600)return Math.floor(diff/60)+'m ago';
    if(diff<86400)return Math.floor(diff/3600)+'h ago';
    return d.toLocaleDateString();
}
function todayStr(){return new Date().toISOString().slice(0,10)}

var allSessions=[];
function load(){
    fetch('/api/sessions').then(function(r){return r.json()}).then(function(data){
        allSessions=data;
        var total=data.length;
        var names={};var todayCount=0;var durSum=0;var durCount=0;var today=todayStr();
        var langs={};var costSum=0;
        data.forEach(function(s){
            if(s.name&&s.name!=='Unknown')names[s.name]=1;
            if(s.started_at&&s.started_at.slice(0,10)===today)todayCount++;
            if(s.duration_seconds!=null){durSum+=s.duration_seconds;durCount++;}
            if(s.language&&s.language!=='-')langs[s.language]=1;
            if(s.cost&&s.cost.total_cost_inr!=null)costSum+=s.cost.total_cost_inr;
        });
        document.getElementById('totalSessions').textContent=total;
        document.getElementById('uniqueUsers').textContent=Object.keys(names).length;
        document.getElementById('avgDuration').textContent=fmtAvg(durCount?durSum/durCount:NaN);
        document.getElementById('todaySessions').textContent=todayCount;
        document.getElementById('todayDate').textContent=today;
        document.getElementById('totalCost').textContent='\u20b9'+costSum.toFixed(2);
        /* Populate language filter */
        var lf=document.getElementById('dLangFilter');var curVal=lf.value;
        lf.innerHTML='<option value="all">All Languages</option>';
        Object.keys(langs).sort().forEach(function(l){lf.innerHTML+='<option value="'+l+'">'+l+'</option>';});
        lf.value=curVal;
        renderTable();
    }).catch(function(e){console.error('Failed to load sessions:',e)});
}
function renderTable(){
    var q=(document.getElementById('dSearch').value||'').toLowerCase();
    var sf=document.getElementById('dStatusFilter').value;
    var lf=document.getElementById('dLangFilter').value;
    var filtered=allSessions.filter(function(s){
        if(sf!=='all'&&s.status!==sf)return false;
        if(lf!=='all'&&(s.language||'')!==lf)return false;
        if(q){
            var hay=((s.name||'')+(s.subject||'')+(s.language||'')).toLowerCase();
            if(hay.indexOf(q)===-1)return false;
        }
        return true;
    });
    var tb=document.getElementById('tbody');
    var emp=document.getElementById('empty');
    if(filtered.length===0){tb.innerHTML='';emp.style.display='block';return;}
    emp.style.display='none';
    var sorted=filtered.slice().sort(function(a,b){return (b.started_at||'').localeCompare(a.started_at||'')});
    var rows=sorted.slice(0,50).map(function(s){
        var costTd='-';
        if(s.cost&&s.cost.total_cost_inr!=null){
            costTd='<span title="STT: \u20b9'+s.cost.stt_cost_inr+' | LLM: \u20b9'+s.cost.llm_cost_inr+' | TTS: \u20b9'+s.cost.tts_cost_inr+'" style="cursor:help">\u20b9'+s.cost.total_cost_inr.toFixed(2)+'</span>';
        }
        return '<tr>'
            +'<td>'+(s.name||'-')+'</td>'
            +'<td>'+(s.subject||'-')+'</td>'
            +'<td>'+(s.language||'-')+'</td>'
            +'<td>'+fmt(s.duration_seconds)+'</td>'
            +'<td>'+costTd+'</td>'
            +'<td><span class="badge '+s.status+'">'+s.status+'</span></td>'
            +'<td>'+relTime(s.started_at)+'</td>'
            +'</tr>';
    }).join('');
    tb.innerHTML=rows;
}
load();
setInterval(load,30000);
/* Crisis alerts count */
function loadCrisis(){
    fetch('/api/alerts/count').then(function(r){return r.json()}).then(function(d){
        document.getElementById('crisisCount').textContent=d.count||0;
    }).catch(function(){});
}
loadCrisis();setInterval(loadCrisis,30000);
</script>
</body>
</html>
"""


ADMIN_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Admin Panel - Voice AI</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
    --bg:#060608;--fg:#fff;--fg2:rgba(255,255,255,.6);--fg3:rgba(255,255,255,.35);--fg4:rgba(255,255,255,.2);--fg5:rgba(255,255,255,.15);
    --border:rgba(255,255,255,.06);--border2:rgba(255,255,255,.1);--border3:rgba(255,255,255,.04);
    --surface:rgba(255,255,255,.03);--surface2:rgba(255,255,255,.06);--surface3:rgba(255,255,255,.02);
    --hover:rgba(255,255,255,.015);--input-bg:rgba(255,255,255,.06);--select-opt-bg:#1a1a2e;
    --modal-bg:#1a1a2e;--modal-overlay:rgba(0,0,0,.6);
    --accent:#a78bfa;--accent2:#6366f1;--accent3:#06b6d4;--green:#14f195;--yellow:#f59e0b;--red:#ef4444;--pink:#f472b6;
}
body.light{
    --bg:#f5f5f7;--fg:#1a1a2e;--fg2:rgba(0,0,0,.6);--fg3:rgba(0,0,0,.45);--fg4:rgba(0,0,0,.3);--fg5:rgba(0,0,0,.15);
    --border:rgba(0,0,0,.08);--border2:rgba(0,0,0,.12);--border3:rgba(0,0,0,.06);
    --surface:rgba(0,0,0,.025);--surface2:rgba(0,0,0,.04);--surface3:rgba(0,0,0,.02);
    --hover:rgba(0,0,0,.03);--input-bg:rgba(0,0,0,.04);--select-opt-bg:#fff;
    --modal-bg:#fff;--modal-overlay:rgba(0,0,0,.35);
    --accent:#7c3aed;--accent2:#4f46e5;--accent3:#0891b2;--green:#059669;--yellow:#d97706;--red:#dc2626;--pink:#db2777;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',-apple-system,sans-serif;background:var(--bg);color:var(--fg);min-height:100vh;transition:background .3s,color .3s}
/* Layout */
.app-layout{display:flex;min-height:100vh}
.sidebar{
    width:240px;min-width:240px;background:var(--surface);border-right:1px solid var(--border);
    display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;z-index:100;
    transition:transform .3s;
}
.sidebar-brand{
    padding:24px 20px;border-bottom:1px solid var(--border);
    display:flex;align-items:center;gap:12px;
}
.sidebar-brand .logo{
    width:32px;height:32px;border-radius:10px;
    background:linear-gradient(135deg,var(--accent),var(--accent2));
    display:flex;align-items:center;justify-content:center;
    font-weight:700;font-size:14px;color:#fff;
}
.sidebar-brand span{
    font-size:16px;font-weight:600;
    background:linear-gradient(135deg,var(--accent),var(--accent2),var(--accent3));
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
.sidebar-nav{flex:1;overflow-y:auto;padding:12px 8px}
.nav-item{
    display:flex;align-items:center;gap:12px;padding:10px 12px;
    border-radius:8px;cursor:pointer;transition:all .2s;
    color:var(--fg3);font-size:13px;font-weight:500;
    border-left:3px solid transparent;margin-bottom:2px;position:relative;
}
.nav-item:hover{background:var(--hover);color:var(--fg2)}
.nav-item.active{background:var(--surface2);color:var(--accent);border-left-color:var(--accent)}
.nav-item svg{width:18px;height:18px;flex-shrink:0;opacity:.6}
.nav-item.active svg{opacity:1}
.nav-badge{
    background:var(--red);color:#fff;border-radius:10px;
    padding:1px 7px;font-size:10px;font-weight:700;margin-left:auto;
}
.sidebar-bottom{
    padding:16px 20px;border-top:1px solid var(--border);
    display:flex;flex-direction:column;gap:4px;
}
.sidebar-bottom .theme-toggle{
    display:flex;align-items:center;gap:10px;padding:8px 12px;
    border-radius:8px;cursor:pointer;color:var(--fg3);font-size:13px;
    transition:all .2s;background:none;border:none;font-family:inherit;width:100%;
}
.sidebar-bottom .theme-toggle:hover{background:var(--hover);color:var(--fg2)}
.sidebar-bottom .logout-btn{
    display:flex;align-items:center;gap:10px;padding:8px 12px;
    border-radius:8px;cursor:pointer;color:var(--red);font-size:13px;
    transition:all .2s;background:none;border:none;font-family:inherit;width:100%;opacity:.7;
}
.sidebar-bottom .logout-btn:hover{opacity:1;background:rgba(239,68,68,.08)}
.main-area{margin-left:240px;flex:1;display:flex;flex-direction:column;min-height:100vh}
.page-header{
    display:flex;align-items:center;justify-content:space-between;
    padding:16px 32px;border-bottom:1px solid var(--border);
    position:sticky;top:0;background:var(--bg);z-index:50;
}
.page-header h2{font-size:18px;font-weight:600;color:var(--fg)}
.page-header .header-links{display:flex;gap:16px;align-items:center}
.page-header a{color:var(--accent);text-decoration:none;font-size:13px;font-weight:500;opacity:.7;transition:opacity .2s}
.page-header a:hover{opacity:1}
.content-area{padding:28px 32px;flex:1;max-width:1100px;width:100%}
.hamburger{
    display:none;background:none;border:none;color:var(--fg);
    cursor:pointer;padding:4px;margin-right:12px;
}
.sidebar-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:99}
.tab-content{display:none}
.tab-content.active{display:block}
@media(max-width:768px){
    .sidebar{transform:translateX(-100%)}
    .sidebar.open{transform:translateX(0)}
    .sidebar-overlay.open{display:block}
    .main-area{margin-left:0}
    .hamburger{display:block}
    .content-area{padding:20px 16px}
    .page-header{padding:12px 16px}
}

/* Cards */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px;margin-bottom:28px}
.card{
    background:var(--surface);border:1px solid var(--border);
    border-radius:14px;padding:22px 24px;
}
.card .label{font-size:12px;color:var(--fg3);font-weight:500;letter-spacing:.5px;text-transform:uppercase}
.card .value{font-size:28px;font-weight:700;margin-top:6px;letter-spacing:-.5px}
.card .sub{font-size:12px;color:var(--fg4);margin-top:4px}
.card:nth-child(1) .value{color:var(--accent)}
.card:nth-child(2) .value{color:var(--accent2)}
.card:nth-child(3) .value{color:var(--accent3)}
.card:nth-child(4) .value{color:var(--green)}
.card:nth-child(5) .value{color:var(--yellow)}

/* Chart */
.chart-wrap{
    background:var(--surface);border:1px solid var(--border);
    border-radius:14px;padding:22px 24px;
}
.chart-wrap h3{font-size:14px;font-weight:600;color:var(--fg2);margin-bottom:18px}
.bar-chart{display:flex;align-items:flex-end;gap:12px;height:140px;padding-top:10px}
.bar-col{flex:1;display:flex;flex-direction:column;align-items:center;gap:6px}
.bar{
    width:100%;min-height:4px;border-radius:6px 6px 0 0;
    background:linear-gradient(180deg,var(--accent),var(--accent2));
    transition:height .3s;
}
.bar-label{font-size:10px;color:var(--fg4)}
.bar-val{font-size:10px;color:var(--fg3);font-weight:600}

/* Form */
.form-section{
    background:var(--surface);border:1px solid var(--border);
    border-radius:14px;padding:28px;margin-bottom:20px;
}
.form-section h3{font-size:15px;font-weight:600;color:var(--fg2);margin-bottom:20px}
.form-row{display:flex;align-items:center;gap:16px;margin-bottom:18px;flex-wrap:wrap}
.form-row label{
    width:160px;font-size:13px;color:var(--fg3);font-weight:500;flex-shrink:0;
}
.form-row .note{font-size:11px;color:var(--fg4);margin-left:4px}
.form-row select,.form-row input[type=number]{
    background:var(--input-bg);border:1px solid var(--border2);
    border-radius:8px;padding:9px 14px;color:var(--fg);font-size:13px;font-family:inherit;
    min-width:200px;outline:none;transition:border-color .2s;
}
.form-row select:focus,.form-row input[type=number]:focus{border-color:var(--accent)}
.form-row select option{background:var(--select-opt-bg);color:var(--fg)}
.form-row input[type=range]{
    width:200px;accent-color:var(--accent);
}
.range-val{font-size:13px;color:var(--fg2);min-width:40px;font-variant-numeric:tabular-nums}
textarea{
    width:100%;min-height:300px;background:var(--input-bg);
    border:1px solid var(--border2);border-radius:10px;padding:16px;
    color:var(--fg);font-size:13px;font-family:'Inter',monospace;line-height:1.6;
    resize:vertical;outline:none;transition:border-color .2s;
}
textarea:focus{border-color:var(--accent)}
.char-count{font-size:11px;color:var(--fg4);margin-top:8px;text-align:right}
.btn-row{display:flex;gap:12px;margin-top:20px}
.btn{
    padding:10px 24px;border-radius:10px;font-size:13px;font-weight:600;
    border:none;cursor:pointer;font-family:inherit;transition:all .2s;
}
.btn-primary{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff}
.btn-primary:hover{opacity:.9;transform:translateY(-1px)}
.btn-secondary{background:var(--surface2);color:var(--fg2);border:1px solid var(--border2)}
.btn-secondary:hover{background:var(--hover)}
.btn-danger{background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.2)}
.btn-danger:hover{background:rgba(239,68,68,.25)}

/* Toast */
.toast{
    position:fixed;top:24px;right:24px;padding:14px 22px;border-radius:10px;
    background:rgba(20,241,149,.15);border:1px solid rgba(20,241,149,.3);color:var(--green);
    font-size:13px;font-weight:500;z-index:1000;
    transform:translateY(-20px);opacity:0;transition:all .3s;pointer-events:none;
}
.toast.show{transform:translateY(0);opacity:1}
.toast.error{background:rgba(239,68,68,.15);border-color:rgba(239,68,68,.3);color:var(--red)}

/* Session management */
.search-bar{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}
.search-bar input{
    flex:1;min-width:200px;background:var(--input-bg);border:1px solid var(--border2);
    border-radius:8px;padding:10px 14px;color:var(--fg);font-size:13px;font-family:inherit;outline:none;
}
.search-bar input:focus{border-color:var(--accent)}
.search-bar select{
    background:var(--input-bg);border:1px solid var(--border2);
    border-radius:8px;padding:10px 14px;color:var(--fg);font-size:13px;font-family:inherit;outline:none;
}
.search-bar select option{background:var(--select-opt-bg);color:var(--fg)}
.tbl-wrap{
    background:var(--surface3);border:1px solid var(--border);
    border-radius:14px;overflow:hidden;
}
.tbl-head{padding:18px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.tbl-head h2{font-size:15px;font-weight:600;color:var(--fg2)}
.tbl-head .refresh{font-size:11px;color:var(--fg4)}
table{width:100%;border-collapse:collapse}
th{
    text-align:left;padding:12px 24px;font-size:11px;font-weight:600;
    color:var(--fg3);letter-spacing:.5px;text-transform:uppercase;
    border-bottom:1px solid var(--border3);
}
td{
    padding:14px 24px;font-size:13px;color:var(--fg2);
    border-bottom:1px solid var(--border3);
}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--hover)}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:500}
.badge.active{background:rgba(20,241,149,.12);color:var(--green)}
.badge.completed{background:rgba(167,139,250,.12);color:var(--accent)}
.empty{text-align:center;padding:48px 24px;color:var(--fg5);font-size:14px}
th.sortable{cursor:pointer;user-select:none;transition:color .2s}
th.sortable:hover{color:var(--accent)}
th.sortable::after{content:'';margin-left:4px;font-size:9px}
th.sortable.asc::after{content:' \25b2'}
th.sortable.desc::after{content:' \25bc'}
.del-btn{
    background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.2);color:var(--red);
    padding:4px 12px;border-radius:6px;font-size:11px;cursor:pointer;font-family:inherit;
    transition:all .2s;
}
.del-btn:hover{background:rgba(239,68,68,.25)}

/* Modal */
.modal-overlay{
    position:fixed;inset:0;background:var(--modal-overlay);z-index:999;
    display:none;align-items:center;justify-content:center;
}
.modal-overlay.show{display:flex}
.modal{
    background:var(--modal-bg);border:1px solid var(--border2);border-radius:14px;
    padding:28px;max-width:400px;width:90%;
}
.modal h3{font-size:16px;font-weight:600;margin-bottom:12px}
.modal p{font-size:13px;color:var(--fg2);margin-bottom:24px;line-height:1.5}
.modal .btn-row{justify-content:flex-end}

/* Alert cards */
.alert-card{
    background:var(--surface);border:1px solid var(--border);
    border-radius:14px;padding:22px 24px;margin-bottom:12px;
}
.alert-card.tier1{border-left:4px solid var(--red)}
.alert-card.tier2{border-left:4px solid var(--yellow)}
.alert-header{display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap}
.tier-badge{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;text-transform:uppercase}
.tier-badge.tier1{background:rgba(239,68,68,.15);color:var(--red)}
.tier-badge.tier2{background:rgba(245,158,11,.15);color:var(--yellow)}
.alert-status{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:500}
.alert-status.new{background:rgba(239,68,68,.12);color:var(--red)}
.alert-status.reviewing{background:rgba(99,102,241,.12);color:var(--accent2)}
.alert-status.resolved{background:rgba(20,241,149,.12);color:var(--green)}
.alert-status.false_positive{background:var(--surface2);color:var(--fg3)}
.alert-time{font-size:11px;color:var(--fg4);margin-left:auto}
.alert-keyword{font-size:13px;color:var(--fg2);margin-bottom:8px}
.alert-keyword strong{color:var(--fg)}
.alert-text{font-size:13px;color:var(--fg3);background:var(--surface);border-radius:8px;padding:10px 14px;margin-bottom:10px;line-height:1.5}
.alert-context{font-size:12px;color:var(--fg4);margin-bottom:12px}
.alert-context summary{cursor:pointer;color:var(--fg3);font-weight:500}
.alert-context pre{margin-top:6px;white-space:pre-wrap;font-family:'Inter',monospace;font-size:11px}
.alert-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.alert-actions .btn{padding:6px 14px;font-size:11px}
.alert-notes{width:100%;background:var(--input-bg);border:1px solid var(--border2);border-radius:8px;padding:8px 12px;color:var(--fg);font-size:12px;font-family:inherit;outline:none;resize:vertical;min-height:36px;margin-top:8px}

/* Badge for PII redacted */
.badge.pii{background:rgba(245,158,11,.12);color:var(--yellow)}

/* Version type badges */
.type-badge{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:500}
.type-badge.prompt{background:rgba(167,139,250,.12);color:var(--accent)}
.type-badge.settings{background:rgba(6,182,212,.12);color:var(--accent3)}
.type-badge.rollback{background:rgba(245,158,11,.12);color:var(--yellow)}

/* Env key rows */
.env-row{
    display:flex;align-items:center;gap:14px;padding:14px 0;
    border-bottom:1px solid var(--border3);flex-wrap:wrap;
}
.env-row:last-child{border-bottom:none}
.env-label{width:180px;flex-shrink:0;font-size:13px;color:var(--fg2);font-weight:500}
.env-masked{
    flex:1;min-width:200px;font-size:12px;color:var(--fg4);
    font-family:'Inter',monospace;letter-spacing:.5px;overflow:hidden;text-overflow:ellipsis;
}
.env-status{width:60px;text-align:center}
.env-status .dot{display:inline-block;width:8px;height:8px;border-radius:50%}
.env-status .dot.set{background:var(--green)}
.env-status .dot.unset{background:rgba(239,68,68,.6)}
.env-actions{display:flex;gap:8px;flex-shrink:0}
.env-input{
    width:100%;background:var(--input-bg);border:1px solid var(--border2);
    border-radius:8px;padding:9px 14px;color:var(--fg);font-size:13px;font-family:'Inter',monospace;
    outline:none;transition:border-color .2s;
}
.env-input:focus{border-color:var(--accent)}
.env-edit-row{
    display:none;width:100%;margin-top:10px;gap:10px;align-items:center;
}
.env-edit-row.show{display:flex}

/* Chart sections */
.chart-section{margin-top:20px}
.chart-section .chart-wrap{margin-bottom:0}

/* Horizontal bar chart */
.hbar-chart{display:flex;flex-direction:column;gap:8px;padding:4px 0}
.hbar-row{display:flex;align-items:center;gap:12px}
.hbar-label{width:140px;font-size:11px;color:var(--fg3);text-align:right;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hbar{height:20px;border-radius:4px;min-width:4px;transition:width .3s}
.hbar.cost-low{background:var(--green)}
.hbar.cost-mid{background:var(--yellow)}
.hbar.cost-high{background:var(--red)}
.hbar-val{font-size:11px;color:var(--fg2);font-weight:600;flex-shrink:0}

/* Heatmap */
.heatmap{display:grid;grid-template-columns:repeat(24,1fr);gap:4px}
.heatmap-cell{
    aspect-ratio:1;border-radius:4px;background:var(--accent);
    opacity:0.08;transition:opacity .3s;position:relative;
}
.heatmap-cell:hover{outline:1px solid var(--accent)}
.heatmap-labels{display:grid;grid-template-columns:repeat(24,1fr);gap:4px;margin-top:4px}
.heatmap-lbl{font-size:9px;color:var(--fg4);text-align:center}

/* Template bar */
.template-bar{
    display:flex;align-items:center;gap:10px;margin-bottom:16px;flex-wrap:wrap;
}
.template-bar select{
    background:var(--input-bg);border:1px solid var(--border2);
    border-radius:8px;padding:9px 14px;color:var(--fg);font-size:13px;font-family:inherit;
    min-width:200px;outline:none;flex:1;max-width:320px;
}
.template-bar select option{background:var(--select-opt-bg);color:var(--fg)}
.tpl-inline-form{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.tpl-inline-form input{
    background:var(--input-bg);border:1px solid var(--border2);border-radius:8px;
    padding:8px 12px;color:var(--fg);font-size:13px;font-family:inherit;outline:none;width:180px;
}
.tpl-inline-form input:focus{border-color:var(--accent)}
</style>
</head>
<body class="light">
<div class="sidebar-overlay" id="sidebarOverlay" onclick="closeSidebar()"></div>
<div class="app-layout">
<aside class="sidebar" id="sidebar">
    <div class="sidebar-brand">
        <div class="logo" id="sidebarLogo">U</div>
        <span id="sidebarBrandName">Admin</span>
    </div>
    <nav class="sidebar-nav">
        <div class="nav-item active" data-tab="analytics" onclick="switchTab('analytics')">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            Dashboard
        </div>
        <div class="nav-item" data-tab="profile" onclick="switchTab('profile')">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            Agent Profile
        </div>
        <div class="nav-item" data-tab="sessions" onclick="switchTab('sessions')">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            Sessions
        </div>
        <div class="nav-item" data-tab="prompt" onclick="switchTab('prompt')">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            System Prompt
        </div>
        <div class="nav-item" data-tab="settings" onclick="switchTab('settings')">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            Agent Settings
        </div>
        <div class="nav-item" data-tab="safety" onclick="switchTab('safety')">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            Safety
            <span class="nav-badge" id="safetyNavBadge" style="display:none"></span>
        </div>
        <div class="nav-item" data-tab="versions" onclick="switchTab('versions')">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            Version History
        </div>
        <div class="nav-item" data-tab="envkeys" onclick="switchTab('envkeys')">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
            Env Keys
        </div>
        <div class="nav-item" data-tab="mcp" onclick="switchTab('mcp')">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/></svg>
            MCP Sources
        </div>
    </nav>
    <div class="sidebar-bottom">
        <button class="theme-toggle" onclick="toggleTheme()">
            <span id="themeIcon">&#9728;</span>
            <span id="themeLabel">Light Mode</span>
        </button>
        <button class="logout-btn" onclick="doLogout()">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="18" height="18"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            Logout
        </button>
    </div>
</aside>
<main class="main-area">
<div class="page-header">
    <div style="display:flex;align-items:center">
        <button class="hamburger" onclick="toggleSidebar()">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
        <h2 id="pageTitle">Dashboard</h2>
    </div>
    <div class="header-links">
        <a href="/">Voice UI</a>
        <a href="/dashboard">Dashboard</a>
    </div>
</div>
<div class="content-area">

    <!-- Tab 1: Analytics -->
    <div class="tab-content active" id="tab-analytics">
        <div class="cards">
            <div class="card"><div class="label">Total Sessions</div><div class="value" id="aTotalSessions">-</div><div class="sub">All time</div></div>
            <div class="card"><div class="label">Unique Users</div><div class="value" id="aUniqueUsers">-</div><div class="sub">By name</div></div>
            <div class="card"><div class="label">Avg Duration</div><div class="value" id="aAvgDuration">-</div><div class="sub">Completed</div></div>
            <div class="card"><div class="label">Today</div><div class="value" id="aTodaySessions">-</div><div class="sub" id="aTodayDate">-</div></div>
            <div class="card"><div class="label">Active Now</div><div class="value" id="aActiveSessions">-</div><div class="sub">In progress</div></div>
            <div class="card"><div class="label">Total Cost</div><div class="value" id="aTotalCost" style="color:#f472b6">-</div><div class="sub">INR (all sessions)</div></div>
            <div class="card"><div class="label">Avg Cost/Session</div><div class="value" id="aAvgCost" style="color:#f472b6">-</div><div class="sub">Completed sessions</div></div>
        </div>
        <div class="chart-wrap">
            <h3>Sessions — Last 7 Days</h3>
            <div class="bar-chart" id="barChart"></div>
        </div>
        <div class="chart-section">
            <div class="chart-wrap">
                <h3>Cost Per Session — Last 10</h3>
                <div class="hbar-chart" id="costChart"></div>
            </div>
        </div>
        <div class="chart-section">
            <div class="chart-wrap">
                <h3>Peak Hours (All Sessions)</h3>
                <div class="heatmap" id="heatmap"></div>
                <div class="heatmap-labels" id="heatmapLabels"></div>
            </div>
        </div>
    </div>

    <!-- Tab: Agent Profile -->
    <div class="tab-content" id="tab-profile">
        <div class="form-section">
            <h3>Agent Identity</h3>
            <p style="font-size:13px;color:var(--fg3);margin-bottom:20px">
                Configure who the agent is. These fields auto-build the system prompt unless a custom prompt is set.
            </p>
            <div class="form-row">
                <label>Agent Name</label>
                <input type="text" id="profileAgentName" placeholder="e.g. Maya, Alex, Support Bot" style="background:var(--input-bg);border:1px solid var(--border2);border-radius:8px;padding:9px 14px;color:var(--fg);font-size:13px;font-family:inherit;min-width:200px;outline:none">
            </div>
            <div class="form-row">
                <label>Company Name</label>
                <input type="text" id="profileCompanyName" placeholder="e.g. UBudy, Acme Corp" style="background:var(--input-bg);border:1px solid var(--border2);border-radius:8px;padding:9px 14px;color:var(--fg);font-size:13px;font-family:inherit;min-width:200px;outline:none">
            </div>
            <div class="form-row">
                <label>Role</label>
                <input type="text" id="profileRole" placeholder="e.g. mental health companion, customer support agent" style="background:var(--input-bg);border:1px solid var(--border2);border-radius:8px;padding:9px 14px;color:var(--fg);font-size:13px;font-family:inherit;min-width:300px;outline:none">
            </div>
            <div class="form-row">
                <label>Greeting</label>
                <textarea id="profileGreeting" style="min-height:60px;width:100%;max-width:500px" placeholder="First message the agent speaks..."></textarea>
            </div>
            <div class="form-row">
                <label>Personality</label>
                <textarea id="profilePersonality" style="min-height:60px;width:100%;max-width:500px" placeholder="e.g. Warm, gentle, calm, non-judgmental..."></textarea>
            </div>
            <div class="form-row">
                <label>Language Mode</label>
                <select id="profileLanguageMode">
                    <option value="english">English only</option>
                    <option value="hindi">Hindi (Romanized)</option>
                    <option value="hinglish">Hinglish (mix)</option>
                    <option value="auto">Auto-detect</option>
                </select>
            </div>
        </div>
        <div class="btn-row">
            <button class="btn btn-primary" onclick="saveProfile()">Save Profile</button>
        </div>
    </div>

    <!-- Tab 2: System Prompt + Knowledge Base -->
    <div class="tab-content" id="tab-prompt">
        <div class="form-section">
            <h3>Knowledge Base</h3>
            <p style="font-size:13px;color:var(--fg3);margin-bottom:16px">
                Paste product docs, FAQs, or any context the agent should know. This gets injected into the system prompt automatically.
            </p>
            <textarea id="knowledgeBase" style="min-height:200px" placeholder="Your product knowledge, FAQs, documentation...&#10;&#10;Example:&#10;Q: What is your return policy?&#10;A: We offer 30-day returns on all products."></textarea>
            <div class="char-count"><span id="kbCharCount">0</span> characters</div>
            <div id="knowledgeFilesList" style="margin-top:12px"></div>
            <div class="btn-row">
                <button class="btn btn-primary" onclick="saveKnowledgeBase()">Save Knowledge Base</button>
            </div>
        </div>
        <div class="form-section">
            <h3>Advanced: Custom System Prompt</h3>
            <p style="font-size:13px;color:var(--fg3);margin-bottom:16px">
                If set, this overrides the auto-generated prompt from Agent Profile. Leave empty to use the auto-built prompt.
            </p>
            <div class="template-bar">
                <select id="templateSelect"><option value="">— Select Template —</option></select>
                <button class="btn btn-secondary" style="padding:8px 16px;font-size:12px" onclick="loadTemplateIntoEditor()">Load</button>
                <button class="btn btn-primary" style="padding:8px 16px;font-size:12px" onclick="showSaveTemplateForm()">Save As Template</button>
                <button class="btn btn-danger" style="padding:8px 16px;font-size:12px" onclick="deleteTemplate()">Delete Template</button>
            </div>
            <div class="tpl-inline-form" id="tplSaveForm" style="display:none;margin-bottom:14px">
                <input type="text" id="tplNameInput" placeholder="Template name...">
                <button class="btn btn-primary" style="padding:8px 16px;font-size:12px" onclick="saveAsTemplate()">Save</button>
                <button class="btn btn-secondary" style="padding:8px 16px;font-size:12px" onclick="hideSaveTemplateForm()">Cancel</button>
            </div>
            <textarea id="promptText" placeholder="Leave empty to use auto-generated prompt from Agent Profile + Knowledge Base..."></textarea>
            <div class="char-count"><span id="charCount">0</span> characters</div>
            <div class="btn-row">
                <button class="btn btn-primary" onclick="savePrompt()">Save Custom Prompt</button>
                <button class="btn btn-secondary" onclick="clearPrompt()">Clear (use auto-generated)</button>
            </div>
        </div>
    </div>

    <!-- Tab 3: Agent Settings -->
    <div class="tab-content" id="tab-settings">
        <div class="form-section">
            <h3>LLM Configuration</h3>
            <div class="form-row">
                <label>Model</label>
                <select id="llmModel">
                    <option value="gpt-4o-mini">gpt-4o-mini</option>
                    <option value="gpt-4o">gpt-4o</option>
                    <option value="gpt-4-turbo">gpt-4-turbo</option>
                    <option value="gpt-3.5-turbo">gpt-3.5-turbo</option>
                </select>
            </div>
            <div class="form-row">
                <label>Temperature</label>
                <input type="range" id="llmTemp" min="0" max="2" step="0.1" value="0.7" oninput="document.getElementById('llmTempVal').textContent=this.value">
                <span class="range-val" id="llmTempVal">0.7</span>
            </div>
        </div>
        <div class="form-section">
            <h3>TTS Configuration</h3>
            <div class="form-row">
                <label>Model</label>
                <select id="ttsModel">
                    <option value="gpt-4o-mini-tts">gpt-4o-mini-tts</option>
                    <option value="tts-1">tts-1</option>
                    <option value="tts-1-hd">tts-1-hd</option>
                </select>
            </div>
            <div class="form-row">
                <label>Voice</label>
                <select id="ttsVoice">
                    <option value="alloy">alloy</option>
                    <option value="echo">echo</option>
                    <option value="fable">fable</option>
                    <option value="onyx">onyx</option>
                    <option value="nova">nova</option>
                    <option value="shimmer">shimmer</option>
                </select>
            </div>
        </div>
        <div class="form-section">
            <h3>STT Configuration</h3>
            <div class="form-row">
                <label>Model</label>
                <select id="sttModel">
                    <option value="nova-2">nova-2</option>
                    <option value="nova">nova</option>
                    <option value="enhanced">enhanced</option>
                    <option value="base">base</option>
                </select>
            </div>
            <div class="form-row">
                <label>Language</label>
                <select id="sttLang">
                    <option value="hi">hi (Hindi)</option>
                    <option value="en">en (English)</option>
                    <option value="en-IN">en-IN (English India)</option>
                    <option value="multi">multi (Multilingual)</option>
                </select>
            </div>
        </div>
        <div class="form-section">
            <h3>VAD Configuration <span class="note">(changes require agent restart)</span></h3>
            <div class="form-row">
                <label>Activation Threshold</label>
                <input type="range" id="vadThreshold" min="0.1" max="0.9" step="0.05" value="0.35" oninput="document.getElementById('vadThresholdVal').textContent=this.value">
                <span class="range-val" id="vadThresholdVal">0.35</span>
            </div>
            <div class="form-row">
                <label>Min Speech Duration</label>
                <input type="number" id="vadMinSpeech" min="0.01" max="1.0" step="0.01" value="0.05">
                <span class="note">seconds (0.01–1.0)</span>
            </div>
            <div class="form-row">
                <label>Min Silence Duration</label>
                <input type="number" id="vadMinSilence" min="0.1" max="2.0" step="0.1" value="0.4">
                <span class="note">seconds (0.1–2.0)</span>
            </div>
        </div>
        <div class="form-section">
            <h3>Call Limits</h3>
            <div class="form-row">
                <label>Max Call Duration</label>
                <input type="number" id="maxCallDuration" min="60" max="3600" step="30" value="600">
                <span class="note">seconds (60–3600)</span>
            </div>
        </div>
        <div class="form-section">
            <h3>Privacy & Safety</h3>
            <div class="form-row">
                <label>PII Redaction</label>
                <select id="piiEnabled">
                    <option value="true">Enabled</option>
                    <option value="false">Disabled</option>
                </select>
                <span class="note">Redact phone numbers, emails, Aadhaar from transcripts</span>
            </div>
        </div>
        <div class="btn-row">
            <button class="btn btn-primary" onclick="saveSettings()">Save All Settings</button>
            <button class="btn btn-secondary" onclick="resetSettings()">Reset to Defaults</button>
        </div>
    </div>

    <!-- Tab 4: Session Management -->
    <div class="tab-content" id="tab-sessions">
        <div class="search-bar">
            <input type="text" id="sessSearch" placeholder="Search by name, topic, or language..." oninput="renderSessions()">
            <select id="sessFilter" onchange="renderSessions()">
                <option value="all">All Status</option>
                <option value="active">Active</option>
                <option value="completed">Completed</option>
            </select>
            <select id="sessLangFilter" onchange="renderSessions()">
                <option value="all">All Languages</option>
            </select>
            <select id="sessDateFilter" onchange="renderSessions()">
                <option value="all">All Time</option>
                <option value="today">Today</option>
                <option value="7d">Last 7 Days</option>
                <option value="30d">Last 30 Days</option>
            </select>
            <select id="sessNameFilter" onchange="renderSessions()">
                <option value="all">All Users</option>
            </select>
        </div>
        <div class="tbl-wrap">
            <div class="tbl-head">
                <h2>Session Management</h2>
                <span class="refresh">Auto-refreshes every 30s</span>
            </div>
            <table>
                <thead><tr>
                    <th class="sortable" onclick="sessSort('name')">Name</th>
                    <th>Topic</th>
                    <th class="sortable" onclick="sessSort('language')">Language</th>
                    <th class="sortable" onclick="sessSort('duration')">Duration</th>
                    <th class="sortable" onclick="sessSort('cost')">Cost (INR)</th>
                    <th class="sortable" onclick="sessSort('status')">Status</th>
                    <th>PII</th>
                    <th class="sortable desc" onclick="sessSort('time')">Time</th>
                    <th></th>
                </tr></thead>
                <tbody id="sessTbody"></tbody>
            </table>
            <div class="empty" id="sessEmpty" style="display:none">No sessions found.</div>
        </div>
    </div>

    <!-- Tab 5: Safety -->
    <div class="tab-content" id="tab-safety">
        <div class="form-section" style="margin-bottom:20px">
            <h3>Safety Keywords Configuration</h3>
            <p style="font-size:13px;color:var(--fg3);margin-bottom:16px">
                Configure keywords that trigger safety alerts. One keyword per line. Leave empty to disable safety alerts.
            </p>
            <div class="form-row" style="align-items:flex-start">
                <label style="color:var(--red)">Tier 1 (Critical)</label>
                <textarea id="safetyTier1" style="min-height:100px;width:100%;max-width:500px" placeholder="suicide&#10;kill myself&#10;want to die&#10;(one keyword per line)"></textarea>
            </div>
            <div class="form-row" style="align-items:flex-start">
                <label style="color:var(--yellow)">Tier 2 (Warning)</label>
                <textarea id="safetyTier2" style="min-height:100px;width:100%;max-width:500px" placeholder="hopeless&#10;no reason to live&#10;(one keyword per line)"></textarea>
            </div>
            <div class="btn-row">
                <button class="btn btn-primary" onclick="saveSafetyKeywords()">Save Keywords</button>
            </div>
        </div>
        <div class="cards">
            <div class="card"><div class="label">Unreviewed</div><div class="value" id="sUnreviewed" style="color:#ef4444">-</div></div>
            <div class="card"><div class="label">Tier 1 (Critical)</div><div class="value" id="sTier1" style="color:#ef4444">-</div></div>
            <div class="card"><div class="label">Tier 2 (Warning)</div><div class="value" id="sTier2" style="color:#f59e0b">-</div></div>
            <div class="card"><div class="label">Resolved</div><div class="value" id="sResolved" style="color:#14f195">-</div></div>
        </div>
        <div class="search-bar">
            <select id="alertStatusFilter" onchange="renderAlerts()">
                <option value="all">All Status</option>
                <option value="new">New</option>
                <option value="reviewing">Reviewing</option>
                <option value="resolved">Resolved</option>
                <option value="false_positive">False Positive</option>
            </select>
            <select id="alertTierFilter" onchange="renderAlerts()">
                <option value="all">All Tiers</option>
                <option value="tier1">Tier 1 (Critical)</option>
                <option value="tier2">Tier 2 (Warning)</option>
            </select>
        </div>
        <div id="alertsList"></div>
        <div class="empty" id="alertsEmpty" style="display:none">No safety alerts found.</div>
    </div>

    <!-- Tab 6: Version History -->
    <div class="tab-content" id="tab-versions">
        <div class="tbl-wrap">
            <div class="tbl-head">
                <h2>Configuration Version History</h2>
                <span class="refresh">Max 50 versions</span>
            </div>
            <table>
                <thead><tr><th>#</th><th>Type</th><th>Timestamp</th><th>Prompt Preview</th><th>Actions</th></tr></thead>
                <tbody id="versTbody"></tbody>
            </table>
            <div class="empty" id="versEmpty" style="display:none">No version history yet. Save a config change to start tracking.</div>
        </div>
    </div>

    <!-- Tab 7: Env Keys -->
    <div class="tab-content" id="tab-envkeys">
        <div class="form-section">
            <h3>Environment Variables</h3>
            <p style="font-size:13px;color:rgba(255,255,255,.3);margin-bottom:20px">
                Update API keys and configuration. Values are masked for security. Changes are written to <code style="background:rgba(255,255,255,.08);padding:2px 6px;border-radius:4px">.env</code> — restart the agent process to apply.
            </p>
            <div id="envKeysList"></div>
            <div style="margin-top:16px;padding:12px 16px;background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.15);border-radius:10px;font-size:12px;color:rgba(245,158,11,.8)">
                Note: After updating keys, restart the agent (<code>python3 agent.py</code>) and web server (<code>python3 web_frontend.py</code>) for changes to take effect.
            </div>
        </div>
    </div>

    <!-- Tab: MCP Knowledge Sources -->
    <div class="tab-content" id="tab-mcp">
        <div class="form-section">
            <h3>MCP Knowledge Sources</h3>
            <p style="font-size:13px;color:var(--fg3);margin-bottom:16px">
                Connect external data sources via MCP (Model Context Protocol). The agent can query these during conversations to provide accurate, real-time information.
            </p>
            <div class="btn-row" style="margin-bottom:16px">
                <button class="btn btn-primary" onclick="addMcpServer('http')">+ Add HTTP Source</button>
                <button class="btn btn-secondary" onclick="addMcpServer('stdio')">+ Add Stdio Source</button>
            </div>
            <div id="mcpServersList"></div>
        </div>
    </div>
</div><!-- /content-area -->
</main>
</div><!-- /app-layout -->

<!-- Delete confirmation modal -->
<div class="modal-overlay" id="delModal">
    <div class="modal">
        <h3>Delete Session</h3>
        <p>Are you sure you want to delete this session? This action cannot be undone.</p>
        <div class="btn-row">
            <button class="btn btn-secondary" onclick="closeDelModal()">Cancel</button>
            <button class="btn btn-danger" id="delConfirmBtn" onclick="confirmDelete()">Delete</button>
        </div>
    </div>
</div>

<!-- Version view modal -->
<div class="modal-overlay" id="versModal">
    <div class="modal" style="max-width:600px">
        <h3>Version <span id="versModalNum"></span> Details</h3>
        <div style="margin-bottom:16px">
            <div style="font-size:12px;color:rgba(255,255,255,.35);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px">System Prompt</div>
            <pre id="versModalPrompt" style="background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:14px;font-size:12px;color:rgba(255,255,255,.6);max-height:300px;overflow:auto;white-space:pre-wrap;font-family:'Inter',monospace"></pre>
        </div>
        <div style="margin-bottom:16px">
            <div style="font-size:12px;color:rgba(255,255,255,.35);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px">Settings Snapshot</div>
            <pre id="versModalSettings" style="background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:14px;font-size:12px;color:rgba(255,255,255,.6);max-height:200px;overflow:auto;white-space:pre-wrap;font-family:'Inter',monospace"></pre>
        </div>
        <div class="btn-row" style="justify-content:flex-end">
            <button class="btn btn-secondary" onclick="closeVersModal()">Close</button>
        </div>
    </div>
</div>

<!-- Cost breakdown modal -->
<div class="modal-overlay" id="costModal">
    <div class="modal" style="max-width:420px">
        <h3 style="margin-bottom:16px">Cost Breakdown</h3>
        <div id="costModalBody"></div>
        <div class="btn-row" style="justify-content:flex-end;margin-top:16px">
            <button class="btn btn-secondary" onclick="closeCostModal()">Close</button>
        </div>
    </div>
</div>

<div class="toast" id="toast"></div>

<script>
/* ── Theme toggle ── */
function toggleTheme(){
    document.body.classList.toggle('light');
    var isLight=document.body.classList.contains('light');
    localStorage.setItem('admin-theme',isLight?'light':'dark');
    document.getElementById('themeIcon').innerHTML=isLight?'&#9728;':'&#9790;';
    document.getElementById('themeLabel').textContent=isLight?'Light Mode':'Dark Mode';
}
function toggleSidebar(){
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('sidebarOverlay').classList.toggle('open');
}
function closeSidebar(){
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebarOverlay').classList.remove('open');
}
(function(){
    var saved=localStorage.getItem('admin-theme');
    if(saved==='dark'){
        document.body.classList.remove('light');
        document.getElementById('themeIcon').innerHTML='&#9790;';
        document.getElementById('themeLabel').textContent='Dark Mode';
    } else {
        document.getElementById('themeIcon').innerHTML='&#9728;';
        document.getElementById('themeLabel').textContent='Light Mode';
    }
})();

var config={};
var sessions=[];
var alerts=[];
var versions=[];
var deleteTargetId=null;

/* ── Auth: fetch interceptor ── */
var _origFetch=window.fetch;
window.fetch=function(){
    return _origFetch.apply(this,arguments).then(function(r){
        if(r.status===401&&r.url&&r.url.indexOf('/api/login')===-1){
            window.location.href='/login';
        }
        return r;
    });
};
function doLogout(){
    fetch('/api/logout',{method:'POST'}).then(function(){window.location.href='/login'}).catch(function(){window.location.href='/login'});
}

/* ── Tabs ── */
var tabTitles={analytics:'Dashboard',profile:'Agent Profile',sessions:'Sessions',prompt:'System Prompt & Knowledge',settings:'Agent Settings',safety:'Safety',versions:'Version History',envkeys:'Env Keys',mcp:'MCP Knowledge Sources'};
function switchTab(name){
    document.querySelectorAll('.nav-item').forEach(function(b){
        b.classList.toggle('active',b.getAttribute('data-tab')===name);
    });
    document.querySelectorAll('.tab-content').forEach(function(c){c.classList.remove('active')});
    document.getElementById('tab-'+name).classList.add('active');
    document.getElementById('pageTitle').textContent=tabTitles[name]||name;
    closeSidebar();
    if(name==='analytics')loadAnalytics();
    if(name==='sessions')loadSessions();
    if(name==='prompt')loadKnowledgeFiles();
    if(name==='safety')loadAlerts();
    if(name==='versions')loadVersions();
    if(name==='envkeys')loadEnvKeys();
    if(name==='mcp')renderMcpServers();
}

/* ── Toast ── */
function showToast(msg,isError){
    var t=document.getElementById('toast');
    t.textContent=msg;
    t.className='toast'+(isError?' error':'')+' show';
    setTimeout(function(){t.classList.remove('show')},3000);
}

/* ── Config load/save ── */
function loadConfig(){
    fetch('/api/config').then(function(r){return r.json()}).then(function(c){
        config=c;
        applyConfigToUI();
    }).catch(function(e){console.error('Failed to load config:',e)});
}
function saveConfig(data){
    return fetch('/api/config',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(data)
    }).then(function(r){return r.json()});
}
function applyConfigToUI(){
    /* Agent Profile */
    var p=config.agent_profile||{};
    document.getElementById('profileAgentName').value=p.agent_name||'';
    document.getElementById('profileCompanyName').value=p.company_name||'';
    document.getElementById('profileRole').value=p.role||'';
    document.getElementById('profileGreeting').value=p.greeting||'';
    document.getElementById('profilePersonality').value=p.personality||'';
    document.getElementById('profileLanguageMode').value=p.language_mode||'english';

    /* Knowledge Base */
    document.getElementById('knowledgeBase').value=config.knowledge_base||'';
    updateKbCharCount();

    /* System Prompt */
    document.getElementById('promptText').value=config.system_prompt||'';
    updateCharCount();

    /* Agent Settings */
    document.getElementById('llmModel').value=config.llm?config.llm.model||'gpt-4o-mini':'gpt-4o-mini';
    var temp=config.llm?config.llm.temperature:0.7;if(temp==null)temp=0.7;
    document.getElementById('llmTemp').value=temp;
    document.getElementById('llmTempVal').textContent=temp;
    document.getElementById('ttsModel').value=config.tts?config.tts.model||'gpt-4o-mini-tts':'gpt-4o-mini-tts';
    document.getElementById('ttsVoice').value=config.tts?config.tts.voice||'nova':'nova';
    document.getElementById('sttModel').value=config.stt?config.stt.model||'nova-2':'nova-2';
    document.getElementById('sttLang').value=config.stt?config.stt.language||'hi':'hi';
    var vad=config.vad||{};
    var vt=vad.activation_threshold!=null?vad.activation_threshold:0.35;
    document.getElementById('vadThreshold').value=vt;
    document.getElementById('vadThresholdVal').textContent=vt;
    document.getElementById('vadMinSpeech').value=vad.min_speech_duration!=null?vad.min_speech_duration:0.05;
    document.getElementById('vadMinSilence').value=vad.min_silence_duration!=null?vad.min_silence_duration:0.4;
    document.getElementById('maxCallDuration').value=config.max_call_duration_seconds||600;
    document.getElementById('piiEnabled').value=config.pii_redaction_enabled!==false?'true':'false';
    renderTemplateDropdown();

    /* MCP Servers */
    if(!config.mcp_servers)config.mcp_servers=[];

    /* Safety Keywords */
    document.getElementById('safetyTier1').value=(config.safety_keywords_tier1||[]).join('\n');
    document.getElementById('safetyTier2').value=(config.safety_keywords_tier2||[]).join('\n');

    /* Dynamic sidebar branding */
    var companyName=p.company_name||'Voice AI';
    document.getElementById('sidebarBrandName').textContent=companyName+' Admin';
    document.getElementById('sidebarLogo').textContent=(companyName.charAt(0)||'V').toUpperCase();
}

/* ── Prompt ── */
function updateCharCount(){
    document.getElementById('charCount').textContent=document.getElementById('promptText').value.length;
}
document.getElementById('promptText').addEventListener('input',updateCharCount);

function savePrompt(){
    config.system_prompt=document.getElementById('promptText').value;
    saveConfig(config).then(function(){showToast('Custom prompt saved')}).catch(function(){showToast('Failed to save',true)});
}
function clearPrompt(){
    config.system_prompt='';
    document.getElementById('promptText').value='';
    updateCharCount();
    saveConfig(config).then(function(){
        showToast('Custom prompt cleared — using auto-generated prompt');
    }).catch(function(){showToast('Failed to save',true)});
}

/* ── Knowledge Base ── */
function updateKbCharCount(){
    document.getElementById('kbCharCount').textContent=document.getElementById('knowledgeBase').value.length;
}
document.getElementById('knowledgeBase').addEventListener('input',updateKbCharCount);

function saveKnowledgeBase(){
    config.knowledge_base=document.getElementById('knowledgeBase').value;
    saveConfig(config).then(function(){showToast('Knowledge base saved')}).catch(function(){showToast('Failed to save',true)});
}
function loadKnowledgeFiles(){
    fetch('/api/knowledge-files').then(function(r){return r.json()}).then(function(files){
        var el=document.getElementById('knowledgeFilesList');
        if(!files.length){el.innerHTML='';return;}
        var html='<div style="font-size:12px;color:var(--fg3);margin-bottom:8px;font-weight:500">Knowledge files in <code style="background:var(--input-bg);padding:2px 6px;border-radius:4px">knowledge/</code> directory:</div>';
        files.forEach(function(f){
            var sz=f.size<1024?(f.size+' B'):(Math.round(f.size/1024)+' KB');
            html+='<div style="font-size:12px;color:var(--fg2);padding:4px 0">&#128196; '+f.name+' <span style="color:var(--fg4)">('+sz+')</span></div>';
        });
        el.innerHTML=html;
    }).catch(function(){});
}

/* ── MCP Servers ── */
function renderMcpServers(){
    var servers=config.mcp_servers||[];
    var el=document.getElementById('mcpServersList');
    if(!servers.length){
        el.innerHTML='<div style="text-align:center;padding:40px 20px;color:var(--fg4)"><p style="font-size:14px;margin-bottom:8px">No MCP sources configured</p><p style="font-size:12px">Add an HTTP or Stdio MCP server to give the agent access to external knowledge.</p></div>';
        return;
    }
    var html='';
    servers.forEach(function(s,i){
        var typeLabel=s.type==='http'?'HTTP':'Stdio';
        var statusClass=s.enabled!==false?'color:#22c55e':'color:#ef4444';
        var statusText=s.enabled!==false?'Enabled':'Disabled';
        html+='<div style="background:var(--input-bg);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:12px">';
        html+='<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">';
        html+='<div><span style="font-weight:600;color:var(--fg1)">'+(s.name||'Unnamed')+'</span>';
        html+=' <span style="font-size:11px;background:var(--accent);color:#fff;padding:2px 8px;border-radius:4px;margin-left:8px">'+typeLabel+'</span>';
        html+=' <span style="font-size:11px;'+statusClass+'">'+statusText+'</span></div>';
        html+='<div style="display:flex;gap:6px">';
        html+='<button class="btn btn-secondary" style="padding:4px 10px;font-size:11px" onclick="toggleMcpServer('+i+')">'+(s.enabled!==false?'Disable':'Enable')+'</button>';
        html+='<button class="btn btn-danger" style="padding:4px 10px;font-size:11px" onclick="removeMcpServer('+i+')">Remove</button>';
        html+='</div></div>';
        if(s.type==='http'){
            html+='<div style="margin-bottom:8px"><label style="font-size:12px;color:var(--fg3);display:block;margin-bottom:4px">URL</label>';
            html+='<input type="text" value="'+(s.url||'')+'" onchange="updateMcpField('+i+',\'url\',this.value)" style="width:100%;padding:8px 12px;background:var(--bg2);border:1px solid var(--border);border-radius:6px;color:var(--fg1);font-size:13px" placeholder="https://example.com/mcp"></div>';
            html+='<div><label style="font-size:12px;color:var(--fg3);display:block;margin-bottom:4px">Headers (JSON, optional)</label>';
            html+='<input type="text" value="'+(s.headers?JSON.stringify(s.headers).replace(/"/g,'&quot;'):'')+'" onchange="updateMcpHeaders('+i+',this.value)" style="width:100%;padding:8px 12px;background:var(--bg2);border:1px solid var(--border);border-radius:6px;color:var(--fg1);font-size:13px" placeholder=\'{"Authorization":"Bearer xxx"}\'></div>';
        } else {
            html+='<div style="display:flex;gap:8px;margin-bottom:8px"><div style="flex:1"><label style="font-size:12px;color:var(--fg3);display:block;margin-bottom:4px">Command</label>';
            html+='<input type="text" value="'+(s.command||'')+'" onchange="updateMcpField('+i+',\'command\',this.value)" style="width:100%;padding:8px 12px;background:var(--bg2);border:1px solid var(--border);border-radius:6px;color:var(--fg1);font-size:13px" placeholder="npx"></div>';
            html+='<div style="flex:2"><label style="font-size:12px;color:var(--fg3);display:block;margin-bottom:4px">Args (comma-separated)</label>';
            html+='<input type="text" value="'+(s.args||[]).join(', ')+'" onchange="updateMcpArgs('+i+',this.value)" style="width:100%;padding:8px 12px;background:var(--bg2);border:1px solid var(--border);border-radius:6px;color:var(--fg1);font-size:13px" placeholder="-y, @modelcontextprotocol/server-name"></div></div>';
            html+='<div><label style="font-size:12px;color:var(--fg3);display:block;margin-bottom:4px">Env vars (JSON, optional)</label>';
            html+='<input type="text" value="'+(s.env?JSON.stringify(s.env).replace(/"/g,'&quot;'):'')+'" onchange="updateMcpEnv('+i+',this.value)" style="width:100%;padding:8px 12px;background:var(--bg2);border:1px solid var(--border);border-radius:6px;color:var(--fg1);font-size:13px" placeholder=\'{"API_KEY":"xxx"}\'></div>';
        }
        html+='</div>';
    });
    el.innerHTML=html;
}
function addMcpServer(type){
    if(!config.mcp_servers)config.mcp_servers=[];
    if(type==='http'){
        config.mcp_servers.push({name:'New HTTP Source',type:'http',url:'',headers:null,enabled:true});
    } else {
        config.mcp_servers.push({name:'New Stdio Source',type:'stdio',command:'',args:[],env:null,enabled:true});
    }
    saveMcpConfig();
}
function removeMcpServer(i){
    if(!confirm('Remove this MCP source?'))return;
    config.mcp_servers.splice(i,1);
    saveMcpConfig();
}
function toggleMcpServer(i){
    config.mcp_servers[i].enabled=!config.mcp_servers[i].enabled;
    saveMcpConfig();
}
function updateMcpField(i,field,val){
    config.mcp_servers[i][field]=val;
    config.mcp_servers[i].name=val?val.split('/').pop().split('?')[0]||config.mcp_servers[i].name:config.mcp_servers[i].name;
    saveMcpConfig();
}
function updateMcpHeaders(i,val){
    try{config.mcp_servers[i].headers=val?JSON.parse(val):null}catch(e){showToast('Invalid JSON for headers',true);return}
    saveMcpConfig();
}
function updateMcpArgs(i,val){
    config.mcp_servers[i].args=val.split(',').map(function(s){return s.trim()}).filter(Boolean);
    saveMcpConfig();
}
function updateMcpEnv(i,val){
    try{config.mcp_servers[i].env=val?JSON.parse(val):null}catch(e){showToast('Invalid JSON for env vars',true);return}
    saveMcpConfig();
}
function saveMcpConfig(){
    saveConfig(config).then(function(){showToast('MCP sources saved');renderMcpServers()}).catch(function(){showToast('Failed to save',true)});
}

/* ── Agent Profile ── */
function saveProfile(){
    config.agent_profile={
        agent_name:document.getElementById('profileAgentName').value.trim(),
        company_name:document.getElementById('profileCompanyName').value.trim(),
        role:document.getElementById('profileRole').value.trim(),
        greeting:document.getElementById('profileGreeting').value.trim(),
        personality:document.getElementById('profilePersonality').value.trim(),
        language_mode:document.getElementById('profileLanguageMode').value
    };
    saveConfig(config).then(function(){
        showToast('Agent profile saved');
        /* Update sidebar branding */
        var cn=config.agent_profile.company_name||'Voice AI';
        document.getElementById('sidebarBrandName').textContent=cn+' Admin';
        document.getElementById('sidebarLogo').textContent=(cn.charAt(0)||'V').toUpperCase();
    }).catch(function(){showToast('Failed to save',true)});
}

/* ── Safety Keywords ── */
function saveSafetyKeywords(){
    var t1=document.getElementById('safetyTier1').value.split('\n').map(function(s){return s.trim()}).filter(Boolean);
    var t2=document.getElementById('safetyTier2').value.split('\n').map(function(s){return s.trim()}).filter(Boolean);
    config.safety_keywords_tier1=t1;
    config.safety_keywords_tier2=t2;
    saveConfig(config).then(function(){showToast('Safety keywords saved')}).catch(function(){showToast('Failed to save',true)});
}

/* ── Settings ── */
function gatherSettings(){
    return {
        agent_profile:config.agent_profile||{},
        knowledge_base:config.knowledge_base||'',
        system_prompt:config.system_prompt||'',
        llm:{model:document.getElementById('llmModel').value,temperature:parseFloat(document.getElementById('llmTemp').value)},
        tts:{model:document.getElementById('ttsModel').value,voice:document.getElementById('ttsVoice').value},
        stt:{model:document.getElementById('sttModel').value,language:document.getElementById('sttLang').value},
        vad:{
            activation_threshold:parseFloat(document.getElementById('vadThreshold').value),
            min_speech_duration:parseFloat(document.getElementById('vadMinSpeech').value),
            min_silence_duration:parseFloat(document.getElementById('vadMinSilence').value)
        },
        max_call_duration_seconds:parseInt(document.getElementById('maxCallDuration').value),
        pii_redaction_enabled:document.getElementById('piiEnabled').value==='true',
        safety_keywords_tier1:config.safety_keywords_tier1||[],
        safety_keywords_tier2:config.safety_keywords_tier2||[],
        prompt_templates:config.prompt_templates||[]
    };
}
function saveSettings(){
    config=gatherSettings();
    saveConfig(config).then(function(){showToast('All settings saved')}).catch(function(){showToast('Failed to save',true)});
}
function resetSettings(){
    config={system_prompt:config.system_prompt||'',llm:{model:'gpt-4o-mini',temperature:0.7},tts:{model:'gpt-4o-mini-tts',voice:'nova'},stt:{model:'nova-2',language:'hi'},vad:{activation_threshold:0.35,min_speech_duration:0.05,min_silence_duration:0.4},max_call_duration_seconds:600,pii_redaction_enabled:true};
    applyConfigToUI();
    saveConfig(config).then(function(){showToast('Settings reset to defaults')}).catch(function(){showToast('Failed to save',true)});
}

/* ── Analytics ── */
function fmtAvg(s){
    if(isNaN(s))return'-';
    var m=Math.floor(s/60),ss=Math.round(s%60);
    return m>0?m+'m '+ss+'s':ss+'s';
}
function loadAnalytics(){
    fetch('/api/sessions').then(function(r){return r.json()}).then(function(data){
        var total=data.length,names={},todayCount=0,durSum=0,durCount=0,activeCount=0,costSum=0;
        var today=new Date().toISOString().slice(0,10);
        data.forEach(function(s){
            if(s.name&&s.name!=='Unknown')names[s.name]=1;
            if(s.started_at&&s.started_at.slice(0,10)===today)todayCount++;
            if(s.duration_seconds!=null){durSum+=s.duration_seconds;durCount++;}
            if(s.status==='active')activeCount++;
            if(s.cost&&s.cost.total_cost_inr!=null)costSum+=s.cost.total_cost_inr;
        });
        document.getElementById('aTotalSessions').textContent=total;
        document.getElementById('aUniqueUsers').textContent=Object.keys(names).length;
        document.getElementById('aAvgDuration').textContent=fmtAvg(durCount?durSum/durCount:NaN);
        document.getElementById('aTodaySessions').textContent=todayCount;
        document.getElementById('aTodayDate').textContent=today;
        document.getElementById('aActiveSessions').textContent=activeCount;
        document.getElementById('aTotalCost').textContent='\u20b9'+costSum.toFixed(2);

        var dayCounts={};
        for(var i=6;i>=0;i--){
            var d=new Date();d.setDate(d.getDate()-i);
            dayCounts[d.toISOString().slice(0,10)]=0;
        }
        data.forEach(function(s){
            if(s.started_at){var dk=s.started_at.slice(0,10);if(dayCounts[dk]!=null)dayCounts[dk]++;}
        });
        var maxVal=Math.max.apply(null,Object.values(dayCounts).concat([1]));
        var chartHtml='';
        var dayNames=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
        Object.keys(dayCounts).forEach(function(dk){
            var cnt=dayCounts[dk];
            var h=Math.max(4,Math.round(cnt/maxVal*120));
            var dn=dayNames[new Date(dk+'T12:00:00').getDay()];
            chartHtml+='<div class="bar-col"><div class="bar-val">'+cnt+'</div><div class="bar" style="height:'+h+'px"></div><div class="bar-label">'+dn+'</div></div>';
        });
        document.getElementById('barChart').innerHTML=chartHtml;

        /* Avg cost per session */
        var costSessions=data.filter(function(s){return s.cost&&s.cost.total_cost_inr!=null&&s.status==='completed'});
        var avgCost=costSessions.length?costSum/costSessions.length:0;
        document.getElementById('aAvgCost').textContent='\u20b9'+avgCost.toFixed(2);

        /* Cost per session - last 10 */
        var costData=data.filter(function(s){return s.cost&&s.cost.total_cost_inr!=null})
            .sort(function(a,b){return(b.started_at||'').localeCompare(a.started_at||'')}).slice(0,10).reverse();
        var maxCost=Math.max.apply(null,costData.map(function(s){return s.cost.total_cost_inr}).concat([0.01]));
        var costHtml='';
        costData.forEach(function(s){
            var c=s.cost.total_cost_inr;
            var pct=Math.max(4,Math.round(c/maxCost*100));
            var cls=c<2?'cost-low':c<=5?'cost-mid':'cost-high';
            var label=(s.name||'Unknown')+' '+((s.started_at||'').slice(5,10));
            costHtml+='<div class="hbar-row"><div class="hbar-label" title="'+label+'">'+label+'</div><div class="hbar '+cls+'" style="width:'+pct+'%"></div><div class="hbar-val">\u20b9'+c.toFixed(2)+'</div></div>';
        });
        document.getElementById('costChart').innerHTML=costHtml||'<div style="color:var(--fg4);font-size:13px;padding:12px">No cost data yet</div>';

        /* Peak hours heatmap */
        var hourCounts=new Array(24).fill(0);
        data.forEach(function(s){
            if(s.started_at){
                var h=new Date(s.started_at).getHours();
                if(h>=0&&h<24)hourCounts[h]++;
            }
        });
        var maxHour=Math.max.apply(null,hourCounts.concat([1]));
        var hmHtml='';var lbHtml='';
        for(var hi=0;hi<24;hi++){
            var op=0.08+0.82*(hourCounts[hi]/maxHour);
            hmHtml+='<div class="heatmap-cell" style="opacity:'+op.toFixed(2)+'" title="'+hi+':00 — '+hourCounts[hi]+' sessions"></div>';
            lbHtml+='<div class="heatmap-lbl">'+(hi<10?'0':'')+hi+'</div>';
        }
        document.getElementById('heatmap').innerHTML=hmHtml;
        document.getElementById('heatmapLabels').innerHTML=lbHtml;
    }).catch(function(e){console.error('Analytics error:',e)});
}

/* ── Sessions ── */
var sessSortCol='time',sessSortDir='desc';
function sessSort(col){
    if(sessSortCol===col){sessSortDir=sessSortDir==='asc'?'desc':'asc';}
    else{sessSortCol=col;sessSortDir=col==='cost'||col==='duration'?'desc':'asc';}
    document.querySelectorAll('#tab-sessions th.sortable').forEach(function(th){th.classList.remove('asc','desc')});
    var idx={name:0,language:1,duration:2,cost:3,status:4,time:5};
    var ths=document.querySelectorAll('#tab-sessions th.sortable');
    ths.forEach(function(th){
        var t=th.textContent.trim().toLowerCase();
        if((col==='name'&&t==='name')||(col==='language'&&t==='language')||(col==='duration'&&t==='duration')
          ||(col==='cost'&&t.indexOf('cost')!==-1)||(col==='status'&&t==='status')||(col==='time'&&t==='time'))
            th.classList.add(sessSortDir);
    });
    renderSessions();
}
function fmt(s){
    if(s==null)return'-';
    var m=Math.floor(s/60),ss=s%60;
    return m>0?m+'m '+ss+'s':ss+'s';
}
function relTime(iso){
    if(!iso)return'-';
    var d=new Date(iso),now=new Date(),diff=Math.floor((now-d)/1000);
    if(diff<60)return 'Just now';
    if(diff<3600)return Math.floor(diff/60)+'m ago';
    if(diff<86400)return Math.floor(diff/3600)+'h ago';
    return d.toLocaleDateString();
}
function loadSessions(){
    fetch('/api/sessions').then(function(r){return r.json()}).then(function(data){
        sessions=data;
        /* Populate language filter */
        var langs={},names={};
        data.forEach(function(s){
            if(s.language&&s.language!=='-')langs[s.language]=1;
            if(s.name&&s.name!=='Unknown')names[s.name]=1;
        });
        var lf=document.getElementById('sessLangFilter');var curLang=lf.value;
        lf.innerHTML='<option value="all">All Languages</option>';
        Object.keys(langs).sort().forEach(function(l){lf.innerHTML+='<option value="'+l+'">'+l+'</option>';});
        lf.value=curLang;
        var nf=document.getElementById('sessNameFilter');var curName=nf.value;
        nf.innerHTML='<option value="all">All Users</option>';
        Object.keys(names).sort().forEach(function(n){nf.innerHTML+='<option value="'+n+'">'+n+'</option>';});
        nf.value=curName;
        renderSessions();
    }).catch(function(e){console.error('Sessions error:',e)});
}
function renderSessions(){
    var q=(document.getElementById('sessSearch').value||'').toLowerCase();
    var f=document.getElementById('sessFilter').value;
    var lf=document.getElementById('sessLangFilter').value;
    var df=document.getElementById('sessDateFilter').value;
    var nf=document.getElementById('sessNameFilter').value;
    var now=new Date();
    var filtered=sessions.filter(function(s){
        if(f!=='all'&&s.status!==f)return false;
        if(lf!=='all'&&(s.language||'')!==lf)return false;
        if(nf!=='all'&&(s.name||'')!==nf)return false;
        if(df!=='all'&&s.started_at){
            var sd=new Date(s.started_at);
            var diffDays=(now-sd)/(1000*60*60*24);
            if(df==='today'&&s.started_at.slice(0,10)!==now.toISOString().slice(0,10))return false;
            if(df==='7d'&&diffDays>7)return false;
            if(df==='30d'&&diffDays>30)return false;
        }
        if(q){
            var hay=((s.name||'')+(s.subject||'')+(s.language||'')).toLowerCase();
            if(hay.indexOf(q)===-1)return false;
        }
        return true;
    });
    var tb=document.getElementById('sessTbody');
    var emp=document.getElementById('sessEmpty');
    if(filtered.length===0){tb.innerHTML='';emp.style.display='block';return;}
    emp.style.display='none';
    var dir=sessSortDir==='asc'?1:-1;
    var sorted=filtered.slice().sort(function(a,b){
        var av,bv;
        if(sessSortCol==='name'){av=(a.name||'').toLowerCase();bv=(b.name||'').toLowerCase();return av<bv?-dir:av>bv?dir:0;}
        if(sessSortCol==='language'){av=(a.language||'').toLowerCase();bv=(b.language||'').toLowerCase();return av<bv?-dir:av>bv?dir:0;}
        if(sessSortCol==='duration'){av=a.duration_seconds||0;bv=b.duration_seconds||0;return (av-bv)*dir;}
        if(sessSortCol==='cost'){av=a.cost?a.cost.total_cost_inr:0;bv=b.cost?b.cost.total_cost_inr:0;return (av-bv)*dir;}
        if(sessSortCol==='status'){av=a.status||'';bv=b.status||'';return av<bv?-dir:av>bv?dir:0;}
        /* default: time */
        av=a.started_at||'';bv=b.started_at||'';return av<bv?-dir:av>bv?dir:0;
    });
    var rows=sorted.slice(0,100).map(function(s){
        var piiBadge=s.pii_redacted?'<span class="badge pii">PII Redacted</span>':'-';
        var costTd='-';
        if(s.cost&&s.cost.total_cost_inr!=null){
            costTd='<span onclick="showCostModal(\''+s.id+'\')" style="cursor:pointer;color:#f472b6;text-decoration:underline;text-underline-offset:2px">\u20b9'+s.cost.total_cost_inr.toFixed(2)+'</span>';
        }
        return '<tr>'
            +'<td>'+(s.name||'-')+'</td>'
            +'<td>'+(s.subject||'-')+'</td>'
            +'<td>'+(s.language||'-')+'</td>'
            +'<td>'+fmt(s.duration_seconds)+'</td>'
            +'<td>'+costTd+'</td>'
            +'<td><span class="badge '+s.status+'">'+s.status+'</span></td>'
            +'<td>'+piiBadge+'</td>'
            +'<td>'+relTime(s.started_at)+'</td>'
            +'<td><button class="del-btn" onclick="openDelModal(\''+s.id+'\')">Delete</button></td>'
            +'</tr>';
    }).join('');
    tb.innerHTML=rows;
}

/* ── Cost modal ── */
function showCostModal(id){
    var s=sessions.find(function(x){return x.id===id});
    if(!s||!s.cost)return;
    var c=s.cost;var u=c.usage||{};
    var html='<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">'
        +'<div style="background:var(--surface);border:1px solid var(--border2);border-radius:10px;padding:14px">'
        +'<div style="font-size:11px;color:var(--fg3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">STT (Deepgram)</div>'
        +'<div style="font-size:20px;font-weight:600;color:#14f195">\u20b9'+c.stt_cost_inr.toFixed(2)+'</div>'
        +'<div style="font-size:11px;color:var(--fg4);margin-top:4px">'+(u.stt_audio_minutes||0)+' min audio</div>'
        +'</div>'
        +'<div style="background:var(--surface);border:1px solid var(--border2);border-radius:10px;padding:14px">'
        +'<div style="font-size:11px;color:var(--fg3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">LLM (OpenAI)</div>'
        +'<div style="font-size:20px;font-weight:600;color:#a78bfa">\u20b9'+c.llm_cost_inr.toFixed(2)+'</div>'
        +'<div style="font-size:11px;color:var(--fg4);margin-top:4px">'+(u.llm_input_tokens||0)+' in / '+(u.llm_output_tokens||0)+' out tokens</div>'
        +'</div>'
        +'<div style="background:var(--surface);border:1px solid var(--border2);border-radius:10px;padding:14px">'
        +'<div style="font-size:11px;color:var(--fg3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">TTS (OpenAI)</div>'
        +'<div style="font-size:20px;font-weight:600;color:#38bdf8">\u20b9'+c.tts_cost_inr.toFixed(2)+'</div>'
        +'<div style="font-size:11px;color:var(--fg4);margin-top:4px">'+(u.tts_audio_minutes||u.tts_characters||0)+(u.tts_audio_minutes?' min audio':' chars')+'</div>'
        +'</div>'
        +'<div style="background:var(--surface);border:1px solid var(--border2);border-radius:10px;padding:14px">'
        +'<div style="font-size:11px;color:var(--fg3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Total</div>'
        +'<div style="font-size:20px;font-weight:600;color:#f472b6">\u20b9'+c.total_cost_inr.toFixed(2)+'</div>'
        +'<div style="font-size:11px;color:var(--fg4);margin-top:4px">$'+c.total_cost_usd.toFixed(4)+' USD</div>'
        +'</div>'
        +'</div>'
        +'<div style="font-size:12px;color:var(--fg4)">Session: '+s.name+' &middot; '+fmt(s.duration_seconds)+' &middot; '+relTime(s.started_at)+'</div>';
    document.getElementById('costModalBody').innerHTML=html;
    document.getElementById('costModal').classList.add('show');
}
function closeCostModal(){document.getElementById('costModal').classList.remove('show')}

/* ── Delete modal ── */
function openDelModal(id){deleteTargetId=id;document.getElementById('delModal').classList.add('show')}
function closeDelModal(){deleteTargetId=null;document.getElementById('delModal').classList.remove('show')}
function confirmDelete(){
    if(!deleteTargetId)return;
    fetch('/api/sessions/'+deleteTargetId,{method:'DELETE'}).then(function(r){return r.json()}).then(function(d){
        if(d.ok){showToast('Session deleted');loadSessions();loadAnalytics();}
        else showToast(d.error||'Failed to delete',true);
    }).catch(function(){showToast('Failed to delete',true)});
    closeDelModal();
}

/* ── Safety / Alerts ── */
function loadAlerts(){
    fetch('/api/alerts').then(function(r){return r.json()}).then(function(data){
        alerts=data;renderAlerts();updateSafetyBadge();
    }).catch(function(e){console.error('Alerts error:',e)});
}
function updateSafetyBadge(){
    var newCount=alerts.filter(function(a){return a.status==='new'}).length;
    var badge=document.getElementById('safetyNavBadge');
    if(newCount>0){badge.textContent=newCount;badge.style.display='inline';}
    else{badge.style.display='none';}
    // Stats
    document.getElementById('sUnreviewed').textContent=newCount;
    document.getElementById('sTier1').textContent=alerts.filter(function(a){return a.tier==='tier1'}).length;
    document.getElementById('sTier2').textContent=alerts.filter(function(a){return a.tier==='tier2'}).length;
    document.getElementById('sResolved').textContent=alerts.filter(function(a){return a.status==='resolved'}).length;
}
function renderAlerts(){
    var sf=document.getElementById('alertStatusFilter').value;
    var tf=document.getElementById('alertTierFilter').value;
    var filtered=alerts.filter(function(a){
        if(sf!=='all'&&a.status!==sf)return false;
        if(tf!=='all'&&a.tier!==tf)return false;
        return true;
    });
    var container=document.getElementById('alertsList');
    var emp=document.getElementById('alertsEmpty');
    if(filtered.length===0){container.innerHTML='';emp.style.display='block';return;}
    emp.style.display='none';
    var sorted=filtered.slice().sort(function(a,b){return(b.created_at||'').localeCompare(a.created_at||'')});
    var html=sorted.map(function(a){
        var ctx='';
        if(a.transcript_context&&a.transcript_context.length){
            ctx='<details class="alert-context"><summary>Transcript context ('+a.transcript_context.length+' entries)</summary><pre>'+a.transcript_context.join('\n').replace(/</g,'&lt;')+'</pre></details>';
        }
        return '<div class="alert-card '+a.tier+'">'
            +'<div class="alert-header">'
            +'<span class="tier-badge '+a.tier+'">'+(a.tier==='tier1'?'CRITICAL':'WARNING')+'</span>'
            +'<span class="alert-status '+a.status+'">'+a.status.replace('_',' ')+'</span>'
            +'<span style="font-size:11px;color:rgba(255,255,255,.3)">Session: '+a.session_id+'</span>'
            +'<span class="alert-time">'+relTime(a.created_at)+'</span>'
            +'</div>'
            +'<div class="alert-keyword">Matched keyword: <strong>'+a.matched_keyword+'</strong></div>'
            +'<div class="alert-text">'+((a.matched_text||'').replace(/</g,'&lt;'))+'</div>'
            +ctx
            +'<div class="alert-actions">'
            +'<button class="btn btn-secondary" onclick="updateAlert(\''+a.id+'\',\'reviewing\')">Reviewing</button>'
            +'<button class="btn btn-primary" onclick="updateAlert(\''+a.id+'\',\'resolved\')">Resolved</button>'
            +'<button class="btn btn-secondary" onclick="updateAlert(\''+a.id+'\',\'false_positive\')">False Positive</button>'
            +'</div>'
            +'<textarea class="alert-notes" placeholder="Add notes..." onchange="updateAlertNotes(\''+a.id+'\',this.value)">'+(a.notes||'')+'</textarea>'
            +'</div>';
    }).join('');
    container.innerHTML=html;
}
function updateAlert(id,status){
    fetch('/api/alerts/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:status})})
    .then(function(r){return r.json()}).then(function(d){
        if(d.ok){showToast('Alert updated');loadAlerts();}
        else showToast(d.error||'Failed',true);
    }).catch(function(){showToast('Failed to update alert',true)});
}
function updateAlertNotes(id,notes){
    fetch('/api/alerts/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({notes:notes})})
    .then(function(r){return r.json()}).then(function(d){
        if(!d.ok)showToast('Failed to save notes',true);
    }).catch(function(){});
}

/* ── Version History ── */
function loadVersions(){
    fetch('/api/versions').then(function(r){return r.json()}).then(function(data){
        versions=data;renderVersions();
    }).catch(function(e){console.error('Versions error:',e)});
}
function renderVersions(){
    var tb=document.getElementById('versTbody');
    var emp=document.getElementById('versEmpty');
    if(versions.length===0){tb.innerHTML='';emp.style.display='block';return;}
    emp.style.display='none';
    var sorted=versions.slice().reverse();
    var rows=sorted.map(function(v){
        var preview=(v.system_prompt||'').substring(0,80);
        if(preview.length>=80)preview+='...';
        if(!preview)preview='(empty)';
        return '<tr>'
            +'<td>v'+v.version+'</td>'
            +'<td><span class="type-badge '+v.type+'">'+v.type+'</span></td>'
            +'<td>'+v.timestamp+'</td>'
            +'<td style="color:rgba(255,255,255,.4);font-size:12px">'+preview.replace(/</g,'&lt;')+'</td>'
            +'<td>'
            +'<button class="btn btn-secondary" style="padding:4px 12px;font-size:11px" onclick="viewVersion('+v.version+')">View</button> '
            +'<button class="btn btn-primary" style="padding:4px 12px;font-size:11px" onclick="rollbackVersion('+v.version+')">Rollback</button>'
            +'</td></tr>';
    }).join('');
    tb.innerHTML=rows;
}
function viewVersion(num){
    var v=versions.find(function(x){return x.version===num});
    if(!v)return;
    document.getElementById('versModalNum').textContent=num;
    document.getElementById('versModalPrompt').textContent=v.system_prompt||'(empty)';
    var snap=Object.assign({},v.config_snapshot||{});
    delete snap.system_prompt;
    document.getElementById('versModalSettings').textContent=JSON.stringify(snap,null,2);
    document.getElementById('versModal').classList.add('show');
}
function closeVersModal(){document.getElementById('versModal').classList.remove('show')}
function rollbackVersion(num){
    if(!confirm('Rollback to version '+num+'? Current config will be replaced.'))return;
    fetch('/api/versions/rollback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version:num})})
    .then(function(r){return r.json()}).then(function(d){
        if(d.ok){showToast('Rolled back to v'+num);loadConfig();loadVersions();}
        else showToast(d.error||'Rollback failed',true);
    }).catch(function(){showToast('Rollback failed',true)});
}

/* ── Env Keys ── */
var envKeys=[];
function loadEnvKeys(){
    fetch('/api/env').then(function(r){return r.json()}).then(function(data){
        envKeys=data;renderEnvKeys();
    }).catch(function(e){console.error('Env error:',e)});
}
function renderEnvKeys(){
    var container=document.getElementById('envKeysList');
    var html=envKeys.map(function(e){
        return '<div class="env-row" id="envrow-'+e.key+'">'
            +'<div class="env-label">'+e.label+'</div>'
            +'<div class="env-status"><span class="dot '+(e.is_set?'set':'unset')+'" title="'+(e.is_set?'Set':'Not set')+'"></span></div>'
            +'<div class="env-masked">'+(e.is_set?e.masked_value:'<span style="color:rgba(239,68,68,.6)">Not set</span>')+'</div>'
            +'<div class="env-actions">'
            +'<button class="btn btn-secondary" style="padding:6px 14px;font-size:11px" onclick="toggleEnvEdit(\''+e.key+'\')">Edit</button>'
            +'</div>'
            +'<div class="env-edit-row" id="envedit-'+e.key+'">'
            +'<input class="env-input" type="text" id="envinput-'+e.key+'" placeholder="Enter new value for '+e.key+'...">'
            +'<button class="btn btn-primary" style="padding:8px 18px;font-size:12px;flex-shrink:0" onclick="saveEnvKey(\''+e.key+'\')">Save</button>'
            +'<button class="btn btn-secondary" style="padding:8px 14px;font-size:12px;flex-shrink:0" onclick="toggleEnvEdit(\''+e.key+'\')">Cancel</button>'
            +'</div>'
            +'</div>';
    }).join('');
    container.innerHTML=html;
}
function toggleEnvEdit(key){
    var el=document.getElementById('envedit-'+key);
    el.classList.toggle('show');
    if(el.classList.contains('show'))document.getElementById('envinput-'+key).focus();
}
function saveEnvKey(key){
    var val=document.getElementById('envinput-'+key).value;
    if(!val){showToast('Please enter a value',true);return;}
    fetch('/api/env',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:key,value:val})})
    .then(function(r){return r.json()}).then(function(d){
        if(d.ok){showToast(key+' updated');document.getElementById('envinput-'+key).value='';toggleEnvEdit(key);loadEnvKeys();}
        else showToast(d.error||'Failed',true);
    }).catch(function(){showToast('Failed to update',true)});
}

/* ── Prompt Templates ── */
function renderTemplateDropdown(){
    var sel=document.getElementById('templateSelect');
    var cur=sel.value;
    sel.innerHTML='<option value="">— Select Template —</option>';
    var tpls=config.prompt_templates||[];
    tpls.forEach(function(t){
        sel.innerHTML+='<option value="'+t.id+'">'+t.name.replace(/</g,'&lt;')+'</option>';
    });
    sel.value=cur;
}
function loadTemplateIntoEditor(){
    var id=document.getElementById('templateSelect').value;
    if(!id){showToast('Select a template first',true);return;}
    var tpl=(config.prompt_templates||[]).find(function(t){return t.id===id});
    if(!tpl)return;
    document.getElementById('promptText').value=tpl.prompt;
    updateCharCount();
    showToast('Loaded: '+tpl.name);
}
function showSaveTemplateForm(){document.getElementById('tplSaveForm').style.display='flex';document.getElementById('tplNameInput').focus();}
function hideSaveTemplateForm(){document.getElementById('tplSaveForm').style.display='none';document.getElementById('tplNameInput').value='';}
function saveAsTemplate(){
    var name=document.getElementById('tplNameInput').value.trim();
    if(!name){showToast('Enter a template name',true);return;}
    var prompt=document.getElementById('promptText').value;
    if(!config.prompt_templates)config.prompt_templates=[];
    var id='tpl_'+Date.now();
    config.prompt_templates.push({id:id,name:name,prompt:prompt});
    saveConfig(config).then(function(){
        showToast('Template saved: '+name);
        hideSaveTemplateForm();
        renderTemplateDropdown();
        document.getElementById('templateSelect').value=id;
    }).catch(function(){showToast('Failed to save template',true)});
}
function deleteTemplate(){
    var id=document.getElementById('templateSelect').value;
    if(!id){showToast('Select a template first',true);return;}
    var tpl=(config.prompt_templates||[]).find(function(t){return t.id===id});
    if(!tpl)return;
    if(!confirm('Delete template "'+tpl.name+'"?'))return;
    config.prompt_templates=config.prompt_templates.filter(function(t){return t.id!==id});
    saveConfig(config).then(function(){
        showToast('Template deleted');
        renderTemplateDropdown();
    }).catch(function(){showToast('Failed to delete template',true)});
}

/* ── Init ── */
loadConfig();
loadAnalytics();
/* Load safety badge count on init */
fetch('/api/alerts').then(function(r){return r.json()}).then(function(data){alerts=data;updateSafetyBadge();}).catch(function(){});
setInterval(function(){loadSessions()},30000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    _init_auth()
    print(f"Voice AI running at: http://localhost:{PORT}")
    print(f"Dashboard: http://localhost:{PORT}/dashboard")
    print(f"Admin Panel: http://localhost:{PORT}/admin")
    print(f"LiveKit URL: {LIVEKIT_URL}")
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
