"""
Parro API client — authentication and all REST calls.

Credentials (username + password) are stored in ~/.hermes/parro.json (chmod 600).
The refresh token is cached there too for speed, but the full PKCE login is re-run
automatically whenever the refresh token is missing, expired, or rejected — so
you never need to reauthenticate manually.
"""
import json
import logging
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.expanduser("~/.hermes/parro.json")
_TOKEN_URL = "https://inloggen.parnassys.net/idp/oauth2/token"
_API_BASE = "https://rest-v2.parro.com/rest/v2"
_CLIENT_ID = "MQygAaSBUcAgPU2WInKt"
_ACCEPT = "application/vnd.topicus.geon+json;version=217"


def _urlopen(req, timeout: int = 15):
    """urlopen wrapper that strips trailing dots from hostnames (Windows SSL fix)."""
    host = req.host if hasattr(req, "host") else ""
    if host:
        if ":" in host:
            h, p = host.rsplit(":", 1)
            req.host = h.rstrip(".") + ":" + p
        else:
            req.host = host.rstrip(".")
    return urllib.request.urlopen(req, timeout=timeout)


class ParroClient:
    def __init__(self):
        self._lock = threading.Lock()
        self._access_token: str | None = None
        self._token_expiry: float = 0.0
        self._guardian_id: str | None = None
        self._config: dict = self._load_config()

    # ------------------------------------------------------------------ config

    def _load_config(self) -> dict:
        if os.path.exists(_CONFIG_PATH):
            try:
                with open(_CONFIG_PATH) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_config(self) -> None:
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        tmp = _CONFIG_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._config, f)
        os.replace(tmp, _CONFIG_PATH)
        # Restrict file permissions on POSIX systems (no-op on Windows)
        try:
            os.chmod(_CONFIG_PATH, 0o600)
        except OSError:
            pass

    # -------------------------------------------------------------------- auth

    def set_credentials(self, username: str, password: str) -> None:
        """Save username + password and clear any cached tokens (called by auth server)."""
        self._config["username"] = username
        self._config["password"] = password
        self._config.pop("refresh_token", None)
        self._access_token = None
        self._token_expiry = 0.0
        self._guardian_id = None
        self._save_config()

    def get_credentials(self) -> tuple[str, str] | None:
        """Return (username, password), preferring env vars over saved config."""
        u = os.environ.get("PARRO_USERNAME") or self._config.get("username")
        p = os.environ.get("PARRO_PASSWORD") or self._config.get("password")
        return (u, p) if u and p else None

    def get_refresh_token(self) -> str | None:
        return os.environ.get("PARRO_REFRESH_TOKEN") or self._config.get("refresh_token")

    def is_configured(self) -> bool:
        """True if we have either credentials (preferred) or a refresh token."""
        return bool(self.get_credentials() or self.get_refresh_token())

    def _refresh_access_token(self) -> None:
        """Try the cached refresh token first; fall back to full PKCE login if it fails."""
        refresh_token = self.get_refresh_token()

        if refresh_token:
            try:
                self._do_refresh(refresh_token)
                return
            except RuntimeError as exc:
                logger.warning("Refresh token rejected (%s), falling back to full login", exc)
                self._config.pop("refresh_token", None)

        # Full PKCE login using stored credentials
        creds = self.get_credentials()
        if not creds:
            raise RuntimeError(
                "Parro is not authenticated. Send /parro-auth to Hermes to connect your account."
            )
        logger.info("Re-authenticating with Parro using stored credentials")
        from . import login as _login_module
        access_token, refresh_token = _login_module.login(*creds)
        self._access_token = access_token
        self._token_expiry = time.time() + 3600 - 120
        self._config["refresh_token"] = refresh_token
        self._save_config()

    def _do_refresh(self, refresh_token: str) -> None:
        """Exchange a refresh token for a new access token (raises on failure)."""
        body = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": _CLIENT_ID,
        }).encode()

        req = urllib.request.Request(_TOKEN_URL, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with _urlopen(req) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise RuntimeError(f"Token refresh failed ({e.code}): {detail}") from e

        self._access_token = result["access_token"]
        expires_in = result.get("expires_in", 3600)
        self._token_expiry = time.time() + expires_in - 120

        new_rt = result.get("refresh_token")
        if new_rt and new_rt != refresh_token:
            self._config["refresh_token"] = new_rt
            self._save_config()

    def _ensure_token(self) -> None:
        with self._lock:
            if not self._access_token or time.time() >= self._token_expiry:
                self._refresh_access_token()

    # --------------------------------------------------------- identity / role

    def _get_guardian_id(self) -> str:
        if self._guardian_id:
            return self._guardian_id
        data = self._request("GET", "/account/me", with_role=False)
        # Guardian ID lives at account.identity.guardians[0].links[rel=self].id
        try:
            guardians = data["identity"]["guardians"]
            for guardian in guardians:
                for link in guardian.get("links", []):
                    if link.get("rel") == "self" and "id" in link:
                        self._guardian_id = str(link["id"])
                        return self._guardian_id
        except (KeyError, TypeError, IndexError):
            pass
        # Fallback: top-level links[rel=self] (account ID — may not work for all endpoints)
        for link in data.get("links", []):
            if link.get("rel") == "self" and "id" in link:
                self._guardian_id = str(link["id"])
                return self._guardian_id
        raise RuntimeError("Could not determine guardian ID from /account/me response")

    # ----------------------------------------------------------- HTTP helpers

    def _request(self, method: str, path: str, body: dict | None = None, with_role: bool = True) -> dict:
        self._ensure_token()

        url = _API_BASE + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._access_token}")
        req.add_header("Accept", _ACCEPT)
        if data:
            req.add_header("Content-Type", _ACCEPT)
        if with_role:
            gid = self._get_guardian_id()
            req.add_header("parro-authorization-role", f"GUARDIAN:{gid}")

        try:
            with _urlopen(req) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise RuntimeError(f"Parro API {method} {path} failed ({e.code}): {detail}") from e

    def _get(self, path: str, **kw) -> dict:
        return self._request("GET", path, **kw)

    def _post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, body=body)

    # ------------------------------------------------------------ API methods

    def get_my_identity_id(self) -> str:
        return self._get_guardian_id()

    def get_unread_counts(self) -> dict:
        return self._get("/identity/unreadcounts")

    def get_chatrooms(self) -> list:
        data = self._get("/chatroom")
        return data.get("items", data) if isinstance(data, dict) else data

    def get_messages(self, chatroom_id: int) -> list:
        data = self._get(f"/chatroom/{chatroom_id}/chatmessage")
        return data.get("items", data) if isinstance(data, dict) else data

    def send_message(self, chatroom_id: int, text: str) -> dict:
        return self._post(
            f"/chatroom/{chatroom_id}/chatmessage",
            {"items": [{"dtype": "chat.RChatTextMessage", "text": text}]},
        )

    def get_groups(self) -> list:
        data = self._get("/group?dtype=identity.RHomeGroup")
        return data.get("items", data) if isinstance(data, dict) else data

    def get_announcements(self, group_id: int) -> list:
        data = self._get(f"/event?dtype=event.RAnnouncementEventPrimer&group={group_id}")
        return data.get("items", data) if isinstance(data, dict) else data

    def get_children(self) -> list:
        data = self._get("/child")
        return data.get("items", data) if isinstance(data, dict) else data

    def get_calendar_events(self, since: str | None = None) -> list:
        params = "dtype=event.RCalendarItemEventPrimer&sort=asc-stream"
        if since:
            params += "&sortDateSince=" + urllib.parse.quote(since)
        data = self._get(f"/event?{params}")
        return data.get("items", data) if isinstance(data, dict) else data

    def get_chat_contacts(self) -> list:
        """List people available to start a private chat with (teachers + guardian co-parents)."""
        data = self._get("/chatroom/identity?sort=asc-streamRole")
        return data.get("items", data) if isinstance(data, dict) else data

    def get_event_detail(self, event_id: int, dtype: str | None = None) -> dict:
        path = f"/event/{event_id}"
        if dtype:
            path += f"?dtype={urllib.parse.quote(dtype)}"
        return self._get(path)

    def create_chatroom(self, contact: dict) -> dict:
        """Create a new SINGLE chatroom. contact is an item from get_chat_contacts()."""
        dtype = contact.get("dtype", "")
        entry: dict = {
            "dtype": "chat.RChatRoomCreate",
            "links": [],
            "muted": False,
            "todo": False,
            "admin": False,
            "active": True,
            "archived": False,
            "type": "SINGLE",
            "hasGuardians": False,
            "memberNames": [],
            "childNames": [],
            "repliesEnabled": True,
            "dnd": False,
            "children": [],
            "guardians": [],
            "teachers": [],
        }
        if "Teacher" in dtype:
            entry["teachers"] = [contact]
        elif "Child" in dtype:
            entry["children"] = [contact]
        else:
            entry["guardians"] = [contact]
        return self._post("/chatroom", {"items": [entry]})


# ---------------------------------------------------------------- singleton

_client: ParroClient | None = None
_client_lock = threading.Lock()


def get_client() -> ParroClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = ParroClient()
        return _client
