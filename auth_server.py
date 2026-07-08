"""
One-shot local HTTP server for the Parro credentials setup flow.

The user opens http://localhost:9877/, enters their Parro username and password,
and clicks Save. The server calls login.login() immediately to verify the
credentials, saves them on success, then shuts itself down.
"""
import http.server
import json
import logging
import secrets
import socket
import threading
import urllib.parse

logger = logging.getLogger(__name__)

_PORT = 9877

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Parro Auth \u2014 Hermes</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:#f0f2f5;margin:0;padding:32px 16px;color:#1a1a2e}}
  .card{{background:#fff;border-radius:12px;max-width:420px;margin:0 auto;
         padding:32px;box-shadow:0 2px 12px rgba(0,0,0,.1)}}
  h1{{margin:0 0 6px;font-size:1.4rem}}
  .sub{{color:#666;margin:0 0 24px;font-size:.9rem}}
  label{{display:block;font-weight:600;margin-bottom:4px;font-size:.9rem}}
  input[type=text],input[type=password]{{
    display:block;width:100%;padding:10px 12px;font-size:1rem;
    border:1px solid #d1d5db;border-radius:6px;margin-bottom:16px;outline:none}}
  input:focus{{border-color:#0066cc;box-shadow:0 0 0 3px rgba(0,102,204,.15)}}
  button{{width:100%;padding:11px;background:#0066cc;color:#fff;border:none;
          border-radius:6px;font-size:1rem;font-weight:600;cursor:pointer}}
  button:hover{{background:#0052a3}}
  button:disabled{{background:#9ca3af;cursor:default}}
  .msg{{border-radius:6px;padding:12px 14px;margin-top:16px;font-size:.9rem;display:none}}
  .msg.error{{background:#fde8e8;border:1px solid #fca5a5;color:#991b1b}}
  .msg.success{{background:#d4edda;border:1px solid #b8dfc8;color:#155724}}
  .spinner{{display:none;text-align:center;margin-top:12px;color:#666;font-size:.9rem}}
</style>
</head>
<body>
<div class="card">
  <h1>\ud83d\udd11 Parro Authentication</h1>
  <p class="sub">Enter your Parro login credentials. They are stored locally in
  <code>~/.hermes/parro.json</code> (mode 600) and never leave your machine.</p>

  <form id="form">
    <label for="u">Username / email</label>
    <input id="u" type="text" name="username" autocomplete="username" required
           placeholder="your.name@school.nl">

    <label for="p">Password</label>
    <input id="p" type="password" name="password" autocomplete="current-password" required>

    <button type="submit" id="btn">Connect Parro</button>
  </form>

  <div class="spinner" id="spinner">\u23f3 Verifying credentials\u2026</div>
  <div class="msg error" id="err"></div>
  <div class="msg success" id="ok">
    \u2705 <strong>Connected!</strong> You can close this tab and return to Hermes.
  </div>
</div>
<script>
document.getElementById('form').addEventListener('submit',function(e){{
  e.preventDefault();
  var btn=document.getElementById('btn');
  btn.disabled=true;
  document.getElementById('spinner').style.display='block';
  document.getElementById('err').style.display='none';
  fetch('/save?tok={tok}',{{
    method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{username:document.getElementById('u').value,
                          password:document.getElementById('p').value}})
  }}).then(function(r){{return r.json();}}).then(function(d){{
    document.getElementById('spinner').style.display='none';
    if(d.ok){{
      document.getElementById('form').style.display='none';
      document.getElementById('ok').style.display='block';
      document.title='\u2713 Done';
    }}else{{
      btn.disabled=false;
      var err=document.getElementById('err');
      err.textContent=d.error||'Unknown error';
      err.style.display='block';
    }}
  }}).catch(function(e){{
    document.getElementById('spinner').style.display='none';
    btn.disabled=false;
    var err=document.getElementById('err');
    err.textContent='Could not reach auth server: '+e.message;
    err.style.display='block';
  }});
}});
</script>
</body>
</html>
"""


class _AuthHandler(http.server.BaseHTTPRequestHandler):

    server: "AuthServer"

    def log_message(self, *_):
        pass

    def do_GET(self):
        html = _HTML.format(tok=self.server.session_tok).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        tok = (qs.get("tok") or [""])[0]

        if tok != self.server.session_tok or parsed.path != "/save":
            self._json({"error": "forbidden"}, 403)
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._json({"error": "invalid JSON"}, 400)
            return

        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            self._json({"error": "Username and password are required"}, 400)
            return

        # Test login immediately — this is the point: verify before saving
        try:
            from . import login as _login_module
            access_token, refresh_token = _login_module.login(username, password)
        except RuntimeError as exc:
            self._json({"error": str(exc)}, 200)  # 200 so browser JS can read it
            return
        except Exception as exc:
            logger.error("Parro login error: %s", exc)
            self._json({"error": f"Unexpected error: {exc}"}, 200)
            return

        # Save credentials and bootstrap cache
        from .client import get_client
        client = get_client()
        client.set_credentials(username, password)
        # Pre-populate the token cache so the first real API call is instant
        import time
        client._access_token = access_token
        client._token_expiry = time.time() + 3600 - 120
        client._config["refresh_token"] = refresh_token
        client._save_config()

        self.server.credentials_saved = True
        self._json({"ok": True})

        t = threading.Thread(target=self._shutdown_later, daemon=True)
        t.start()

    def _shutdown_later(self):
        import time
        time.sleep(2)
        self.server.shutdown()

    def _json(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class AuthServer(http.server.HTTPServer):
    def __init__(self, port: int):
        super().__init__(("127.0.0.1", port), _AuthHandler)
        self.session_tok: str = secrets.token_urlsafe(16)
        self.credentials_saved: bool = False


def _find_free_port(start: int) -> int:
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}\u2013{start + 20}")


def start_auth_server() -> tuple[AuthServer, str]:
    """Start the auth server in a daemon thread. Returns (server, url)."""
    port = _find_free_port(_PORT)
    server = AuthServer(port)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    url = f"http://localhost:{port}/"
    logger.info("Parro auth server listening on %s", url)
    return server, url

