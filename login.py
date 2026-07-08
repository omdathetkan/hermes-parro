"""
Headless PKCE login for Parnassys using a username + password.

Flow:
  1. Generate PKCE code_verifier / code_challenge
  2. Discover the authorization endpoint via OIDC discovery (with fallback)
  3. GET the Parnassys login page (follows redirects, maintains cookies)
  4. Parse the HTML login form to find field names
  5. POST username + password
  6. Intercept the redirect to talk.parro.com and extract the authorization code
  7. Exchange code + code_verifier for access_token + refresh_token

Returns (access_token, refresh_token) on success; raises RuntimeError on failure.
"""
import base64
import hashlib
import html
import html.parser
import http.client
import http.cookiejar
import json
import logging
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_CLIENT_ID = "MQygAaSBUcAgPU2WInKt"
_REDIRECT_URI = "https://talk.parro.com/oauth2"
_TOKEN_URL = "https://inloggen.parnassys.net/idp/oauth2/token"
_OIDC_DISCOVERY_URL = "https://inloggen.parnassys.net/idp/.well-known/openid-configuration"
_FALLBACK_AUTH_URL = "https://inloggen.parnassys.net/idp/oauth2/authorize"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# SSL fix: Windows DNS resolvers sometimes append a trailing dot to FQDNs
# (e.g. 'inloggen.parnassys.net.') which breaks Python SSL hostname verification.
# ---------------------------------------------------------------------------

class _FixHostnameHTTPSHandler(urllib.request.HTTPSHandler):
    """Strip trailing dots from hostnames before SSL connects."""
    def https_open(self, req):
        host = req.host
        if ":" in host:
            h, p = host.rsplit(":", 1)
            req.host = h.rstrip(".") + ":" + p
        else:
            req.host = host.rstrip(".")
        return super().https_open(req)


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge_S256)."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


# ---------------------------------------------------------------------------
# Redirect interception
# ---------------------------------------------------------------------------

class _ParroRedirect(Exception):
    """Raised by _StopAtParroHandler when the IDP redirects to talk.parro.com."""
    def __init__(self, url: str) -> None:
        self.url = url


class _StopAtParroHandler(urllib.request.HTTPRedirectHandler):
    """
    Custom redirect handler that raises _ParroRedirect instead of following
    the final redirect to talk.parro.com (which carries the authorization code).
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if "talk.parro.com" in newurl:
            raise _ParroRedirect(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# ---------------------------------------------------------------------------
# HTML form parser
# ---------------------------------------------------------------------------

class _FormParser(html.parser.HTMLParser):
    """
    Extracts all HTML forms with their action URL and input fields.
    Handles <input> tags (including hidden fields).
    """
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict] = []
        self._current: dict | None = None

    def handle_starttag(self, tag: str, attrs):
        a = dict(attrs)
        if tag == "form":
            self._current = {
                "action": a.get("action", ""),
                "method": a.get("method", "post").lower(),
                "fields": {},
            }
        elif tag in ("input", "button") and self._current is not None:
            name = a.get("name", "")
            value = a.get("value", "")
            itype = a.get("type", "text" if tag == "input" else "submit").lower()
            # Include everything except purely decorative/reset inputs.
            # Submit buttons ARE included — Wicket requires them to identify the action.
            if name and itype not in ("image", "reset"):
                self._current["fields"][name] = value
        elif tag == "a" and self._current is not None:
            # Wicket login buttons are <a onclick="...innerHTML += '<input name=X value=Y />'...">
            # Parse the injected hidden fields out of the onclick JavaScript.
            onclick = html.unescape(a.get("onclick", ""))
            for m in re.finditer(r'name=["\'](\w+)["\'].*?value=["\']([^"\']*)["\']', onclick):
                self._current["fields"][m.group(1)] = m.group(2)

    def handle_endtag(self, tag: str):
        if tag == "form" and self._current is not None:
            self.forms.append(self._current)
            self._current = None


def _find_login_form(forms: list[dict]) -> dict:
    """Pick the form that contains a password field."""
    for form in forms:
        for name in form["fields"]:
            if "password" in name.lower() or name.lower() in ("pw", "wachtwoord", "passwd"):
                return form
    if forms:
        return forms[0]
    raise RuntimeError(
        "No HTML form found on the Parnassys login page. "
        "The login page structure may have changed — please open an issue at "
        "https://github.com/omdathetkan/hermes-parro/issues."
    )


def _identify_fields(fields: dict) -> tuple[str, str]:
    """
    Return (username_field_name, password_field_name).
    Raises RuntimeError if either cannot be identified.
    """
    pw_field = None
    user_field = None

    for name, value in fields.items():
        lower = name.lower()
        # Skip fields that look like submit buttons (non-empty fixed values)
        if lower in ("aanmelden", "submit", "login", "inloggen") and value:
            continue
        if "password" in lower or lower in ("pw", "wachtwoord", "passwd"):
            pw_field = name
        elif any(x in lower for x in ("username", "user", "email", "mail",
                                       "gebruiker", "account", "naam")):
            user_field = name

    if pw_field is None:
        raise RuntimeError(
            f"Could not identify password field. Fields found: {list(fields)}. "
            f"Please open an issue at https://github.com/omdathetkan/hermes-parro/issues."
        )

    if user_field is None:
        # Best guess: first non-hidden, non-password field with an empty default value
        for name, val in fields.items():
            if name != pw_field and val == "":
                user_field = name
                break

    if user_field is None:
        raise RuntimeError(
            f"Could not identify username field. Fields found: {list(fields)}. "
            f"Please open an issue at https://github.com/omdathetkan/hermes-parro/issues."
        )

    return user_field, pw_field


# ---------------------------------------------------------------------------
# OIDC discovery
# ---------------------------------------------------------------------------

def _get_authorization_endpoint() -> str:
    try:
        req = urllib.request.Request(_OIDC_DISCOVERY_URL)
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            doc = json.loads(resp.read())
            endpoint = doc.get("authorization_endpoint")
            if endpoint:
                logger.debug("Authorization endpoint from discovery: %s", endpoint)
                return endpoint
    except Exception as exc:
        logger.warning("OIDC discovery failed (%s), using fallback URL", exc)
    return _FALLBACK_AUTH_URL


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def login(username: str, password: str) -> tuple[str, str]:
    """
    Perform the full PKCE authorization code flow using username + password.

    Returns:
        (access_token, refresh_token)

    Raises:
        RuntimeError on any failure (wrong credentials, network error, page structure change).
    """
    verifier, challenge = _pkce_pair()
    auth_base = _get_authorization_endpoint()

    import uuid
    auth_url = auth_base + "?" + urllib.parse.urlencode({
        "client_id": _CLIENT_ID,
        "redirect_uri": _REDIRECT_URI,
        "response_type": "code",
        "scope": "openid",
        "oauth2": "authorize",
        "state": str(uuid.uuid4()),
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    })

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        _StopAtParroHandler(),
        _FixHostnameHTTPSHandler(),
    )
    opener.addheaders = [
        ("User-Agent", _USER_AGENT),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "nl-NL,nl;q=0.9,en;q=0.8"),
    ]

    # ---- Step 1: Load login page ----
    try:
        with opener.open(auth_url, timeout=15) as resp:
            login_html = resp.read().decode("utf-8", errors="replace")
            login_url = resp.geturl()
    except _ParroRedirect:
        raise RuntimeError(
            "Got a Parro redirect before the login form was shown. "
            "This is unexpected — please try again."
        )
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Parnassys login page: {exc}") from exc

    # ---- Step 2: Parse form ----
    parser = _FormParser()
    parser.feed(login_html)
    form = _find_login_form(parser.forms)
    user_field, pw_field = _identify_fields(form["fields"])

    # Resolve relative form action URL against the login page URL
    action = form["action"] or login_url
    if not action.startswith("http"):
        action = urllib.parse.urljoin(login_url, action)

    logger.debug("Login page URL : %s", login_url)
    logger.debug("Form action    : %s", action)
    logger.debug("Form fields    : %s", list(form["fields"].keys()))
    logger.debug("Username field : %s", user_field)
    logger.debug("Password field : %s", pw_field)

    # ---- Step 3: Submit credentials ----
    fields = dict(form["fields"])
    fields[user_field] = username
    fields[pw_field] = password

    post_data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(action, data=post_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Referer", login_url)

    # ---- Step 4: Capture the redirect to talk.parro.com ----
    redirect_url = None
    try:
        with opener.open(req, timeout=15) as resp:
            final_url = resp.geturl()
            body = resp.read().decode("utf-8", errors="replace")
            logger.debug("POST response URL: %s", final_url)
            # Log a snippet of the response to spot Wicket error messages
            snippet = " | ".join(body.split("\n")[0:5])[:400]
            logger.debug("POST response body (start): %s", snippet)
            if "code=" in final_url:
                redirect_url = final_url
            else:
                raise RuntimeError(
                    "Login form submitted but no authorization code was returned. "
                    "Check your username and password."
                )
    except _ParroRedirect as exc:
        logger.debug("Captured redirect: %s", exc.url)
        redirect_url = exc.url

    # ---- Step 5: Extract authorization code ----
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(redirect_url).query)
    code = (qs.get("code") or [None])[0]

    if not code:
        error = (qs.get("error_description") or qs.get("error") or ["unknown error"])[0]
        raise RuntimeError(f"Authorization failed: {error}")

    # ---- Step 6: Exchange code for tokens ----
    token_body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": _CLIENT_ID,
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": _REDIRECT_URI,
    }).encode()

    token_req = urllib.request.Request(_TOKEN_URL, data=token_body, method="POST")
    token_req.add_header("Content-Type", "application/x-www-form-urlencoded")
    token_req.add_header("Accept", "*/*")
    token_req.add_header("Origin", "https://talk.parro.com")
    token_req.add_header("Referer", "https://talk.parro.com/")

    try:
        # Use the same opener so Cloudflare sees the established session cookies
        with opener.open(token_req, timeout=15) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Token exchange failed ({exc.code}): {detail}") from exc

    access_token = result.get("access_token")
    refresh_token = result.get("refresh_token")

    if not access_token or not refresh_token:
        raise RuntimeError(f"Token response missing expected fields: {list(result)}")

    return access_token, refresh_token
