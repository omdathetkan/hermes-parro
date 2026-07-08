#!/usr/bin/env python3
"""
Local test runner for hermes-parro.
Run from the hermes-parro/ directory:

    python test_local.py

Credentials are read from (in order of priority):
  1. Environment variables: PARRO_USERNAME, PARRO_PASSWORD
  2. A .env file in this directory (never committed — see .gitignore)
  3. The auth server (browser form) if neither is set

.env format:
    PARRO_USERNAME=your.email@school.nl
    PARRO_PASSWORD=yourpassword
"""
import importlib.util
import json
import logging
import os
import sys
import types

# ---- load .env before anything else ----------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_env_file = os.path.join(_HERE, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
    print(f"Loaded credentials from .env")

# ---- enable debug logging ---------------------------------------------------
logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
# Quiet noisy stdlib loggers
for _noisy in ("urllib3", "urllib", "http.client"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Bootstrap: register this directory as a Python package called "hermes_parro"
# so that relative imports inside the plugin (from .client import ...) work.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = "hermes_parro"

def _register_package():
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [_HERE]
    pkg.__package__ = _PKG
    sys.modules[_PKG] = pkg

def _load_module(name):
    path = os.path.join(_HERE, f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"{_PKG}.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = _PKG
    sys.modules[f"{_PKG}.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod

_register_package()
for _m in ("client", "login", "schemas", "tools", "auth_server"):
    _load_module(_m)

# Now normal imports work
from hermes_parro.client import get_client
from hermes_parro.tools import (
    check_parro_available,
    handle_parro_get_calendar,
    handle_parro_get_contacts,
    handle_parro_get_event_detail,
    handle_parro_get_messages,
    handle_parro_get_announcements,
    handle_parro_get_unread,
    handle_parro_list_chats,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pretty(result_json: str) -> None:
    try:
        print(json.dumps(json.loads(result_json), indent=2, ensure_ascii=False))
    except Exception:
        print(result_json)

def _section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)

# ---------------------------------------------------------------------------
# Auth setup
# ---------------------------------------------------------------------------

def ensure_auth():
    if check_parro_available():
        creds = get_client().get_credentials()
        print(f"✓ Credentials found (user: {creds[0] if creds else 'via env'})")
        return

    if not os.environ.get("PARRO_USERNAME"):
        print("\nNo credentials found.")
        print("Create a .env file in this directory:")
        print("  PARRO_USERNAME=your.email@school.nl")
        print("  PARRO_PASSWORD=yourpassword")
        sys.exit(1)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_unread():
    _section("Unread counts")
    result = handle_parro_get_unread({})
    _pretty(result)

def test_messages():
    _section("Messages (unread chatrooms)")
    result = handle_parro_get_messages({"unread_only": True})
    data = json.loads(result)
    if "error" in data:
        print(f"ERROR: {data['error']}")
        return
    print(f"Total messages returned: {data['count']}")
    for msg in data["messages"][:5]:
        print(f"\n  Room : {msg['chatroom_name']} (id={msg['chatroom_id']})")
        print(f"  Time : {msg['timestamp']}")
        print(f"  Text : {msg['text'][:120]}")

def test_announcements():
    _section("Announcements (limit=5)")
    result = handle_parro_get_announcements({"limit": 5})
    data = json.loads(result)
    if "error" in data:
        print(f"ERROR: {data['error']}")
        return
    print(f"Total announcements returned: {data['count']}")
    first_id = None
    for ann in data["announcements"][:5]:
        print(f"\n  Group : {ann['group_name']}")
        print(f"  Title : {ann['title']}")
        print(f"  Date  : {ann['last_modified_at']}")
        if first_id is None:
            first_id = ann.get("event_id")
    if first_id:
        _section(f"Event detail (id={first_id})")
        detail = json.loads(handle_parro_get_event_detail({"event_id": first_id, "event_type": "announcement"}))
        print(f"  Title : {detail.get('title')}")
        print(f"  Body  : {(detail.get('body') or '')[:200]}")

def test_calendar():
    _section("Upcoming calendar events")
    result = handle_parro_get_calendar({})
    data = json.loads(result)
    if "error" in data:
        print(f"ERROR: {data['error']}")
        return
    print(f"Total events: {data['count']}")
    for evt in data["events"][:5]:
        print(f"\n  Title : {evt['title']}")
        print(f"  Date  : {evt['date']}")
        print(f"  Children: {evt.get('children', [])}")

def test_list_chats():
    _section("Chatrooms (query=Esther, limit=5)")
    result = handle_parro_list_chats({"query": "Esther", "limit": 5})
    data = json.loads(result)
    if "error" in data:
        print(f"ERROR: {data['error']}")
        return
    print(f"Matches: {data['count']}")
    for chat in data["chats"]:
        print(f"  id={chat['id']}  unread={chat['unread_count']}  {chat['name'][:80]}")

def test_contacts():
    for q in ("evan", "Alexander"):
        _section(f"Chat contacts (query={q})")
        result = handle_parro_get_contacts({"query": q})
        data = json.loads(result)
        if "error" in data:
            print(f"ERROR: {data['error']}")
            return
        print(f"Matches: {data['count']}")
        for c in data["contacts"]:
            print(f"  id={c['contact_id']}  {c['name']}  ({c['role']})")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("hermes-parro local test")
    print("-" * 40)

    ensure_auth()

    print("\nTesting API access...")
    try:
        test_unread()
        test_list_chats()
        test_messages()
        test_announcements()
        test_calendar()
        test_contacts()
        print("\n✓ All tests completed.")
    except Exception as exc:
        print(f"\n✗ Error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
