"""Parro tool handlers."""
import json
import logging
from datetime import datetime, timedelta, timezone

from .client import get_client

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------- check fn

def check_parro_available() -> bool:
    return get_client().is_configured()


# ----------------------------------------------------------------- helpers

def _link_id(obj: dict) -> int | None:
    for link in obj.get("links", []):
        if link.get("rel") == "self" and "id" in link:
            return link["id"]
    return obj.get("id")


def _room_name(room: dict) -> str:
    names = room.get("memberNames")
    if names:
        return ", ".join(names)
    return room.get("name") or f"Room {_link_id(room)}"


def _unread_count(room: dict) -> int:
    member = room.get("chatroommember", {})
    if isinstance(member, dict):
        return member.get("unreadCount", 0)
    return room.get("unreadCount", 0)


def _after(timestamp: str | None, since: str | None) -> bool:
    """Return True if timestamp is after since (or since is None)."""
    if since is None or not timestamp:
        return True
    return timestamp >= since


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")


def _one_month_ago_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")


def _since_arg(args: dict, default: str) -> str:
    since = args.get("since")
    if since is None or (isinstance(since, str) and not since.strip()):
        return default
    return str(since).strip()


def _text_matches(text: str, query: str) -> bool:
    return query.casefold() in (text or "").casefold()


def _guardian_contact_entry(guardian: dict, child_name: str) -> dict:
    return {
        "contact_id": _link_id(guardian),
        "name": f"{guardian.get('firstname', '')} {guardian.get('surname', '')}".strip(),
        "role": "GUARDIAN",
        "in_chat_room": guardian.get("inChatRoom", False),
        "child_names": [child_name],
    }


def _merge_contact_entry(existing: dict, incoming: dict) -> None:
    if incoming.get("child_names"):
        merged = list(dict.fromkeys((existing.get("child_names") or []) + incoming["child_names"]))
        existing["child_names"] = merged


def _int_arg(args: dict, key: str, default: int) -> int:
    value = args.get(key)
    if value is None:
        return default
    return int(value)


def _query_arg(args: dict) -> str:
    return (args.get("query") or "").strip()


def _matches_any_field(entry: dict, query: str, *fields: str) -> bool:
    return any(_text_matches(entry.get(field, ""), query) for field in fields)


def _calendar_item(evt: dict) -> dict:
    item = evt.get("calendarItem")
    return item if isinstance(item, dict) else {}


def _event_title(evt: dict) -> str:
    ci = _calendar_item(evt)
    return evt.get("title") or ci.get("title") or ""


def _event_body(evt: dict) -> str:
    ci = _calendar_item(evt)
    return (
        evt.get("contents") or evt.get("body") or evt.get("text")
        or ci.get("contents") or ci.get("body") or ci.get("description")
        or ""
    )


def _event_date(evt: dict) -> str:
    ci = _calendar_item(evt)
    return evt.get("sortDate") or ci.get("startDate") or evt.get("createdAt") or ""


# ----------------------------------------------------------------- handlers

def handle_parro_get_unread(args: dict, **_) -> str:
    try:
        client = get_client()
        counts = client.get_unread_counts()
        rooms = client.get_chatrooms()
        unread_rooms = [
            {
                "id": _link_id(r),
                "name": _room_name(r),
                "unread_count": _unread_count(r),
                "muted": r.get("muted", False),
            }
            for r in rooms if _unread_count(r) > 0
        ]
        return json.dumps({
            "unread_chat_rooms": counts.get("numberOfUnreadChatRooms", 0),
            "unread_announcements": counts.get("numberOfUnreadAnnouncements", 0),
            "unread_calendar_items": counts.get("numberOfUnreadCalendarItems", 0),
            "chatrooms_with_unread": unread_rooms,
        })
    except Exception as exc:
        logger.error("parro_get_unread: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_list_chats(args: dict, **_) -> str:
    try:
        query = _query_arg(args)
        unread_only = bool(args.get("unread_only", False))
        limit = _int_arg(args, "limit", 20)
        rooms = get_client().get_chatrooms()
        result = []
        for r in rooms:
            if unread_only and _unread_count(r) <= 0:
                continue
            entry = {
                "id": _link_id(r),
                "name": _room_name(r),
                "type": r.get("type"),
                "unread_count": _unread_count(r),
                "muted": r.get("muted", False),
                "archived": r.get("archived", False),
            }
            if query and not _text_matches(entry["name"], query):
                continue
            result.append(entry)
        result = result[:limit]
        payload: dict = {"chats": result, "count": len(result)}
        if query:
            payload["query"] = query
        return json.dumps(payload)
    except Exception as exc:
        logger.error("parro_list_chats: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_get_messages(args: dict, **_) -> str:
    try:
        client = get_client()
        chatroom_id = args.get("chatroom_id")
        unread_only = args.get("unread_only", True)
        since = _since_arg(args, _one_month_ago_iso())
        query = _query_arg(args)
        limit = _int_arg(args, "limit", 20)
        my_id = str(client.get_my_identity_id())

        if chatroom_id is not None:
            rooms = [{"id": int(chatroom_id), "name": f"Chatroom {chatroom_id}"}]
        else:
            all_rooms = client.get_chatrooms()
            rooms = [
                {"id": _link_id(r), "name": _room_name(r), "unread": _unread_count(r)}
                for r in all_rooms
                if not unread_only or _unread_count(r) > 0
            ]

        messages = []
        for room in rooms:
            rid = room["id"]
            if rid is None:
                continue
            room_name = room.get("name", f"Room {rid}")
            for msg in client.get_messages(rid):
                if msg.get("deleted"):
                    continue
                if str(msg.get("identity", {}).get("id", "")) == my_id:
                    continue
                ts = msg.get("lastModifiedAt", "")
                if not _after(ts, since):
                    continue
                text = msg.get("text") or ""
                if query and not (_text_matches(text, query) or _text_matches(room_name, query)):
                    continue
                messages.append({
                    "chatroom_id": rid,
                    "chatroom_name": room_name,
                    "message_id": _link_id(msg) or msg.get("id"),
                    "text": text,
                    "dtype": msg.get("dtype", ""),
                    "sender_id": str(msg.get("identity", {}).get("id", "")),
                    "timestamp": ts,
                })

        messages.sort(key=lambda m: m["timestamp"], reverse=True)
        messages = messages[:limit]
        payload: dict = {"messages": messages, "count": len(messages), "since": since}
        if query:
            payload["query"] = query
        return json.dumps(payload)
    except Exception as exc:
        logger.error("parro_get_messages: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_get_announcements(args: dict, **_) -> str:
    try:
        client = get_client()
        since = _since_arg(args, _one_month_ago_iso())
        query = _query_arg(args)
        limit = _int_arg(args, "limit", 10)
        groups = client.get_groups()

        announcements = []
        for group in groups:
            group_id = _link_id(group)
            group_name = group.get("name") or f"Group {group_id}"
            if group_id is None:
                continue
            for ann in client.get_announcements(group_id):
                ts = ann.get("lastModifiedAt", "")
                if not _after(ts, since):
                    continue
                title = ann.get("title") or ""
                entry = {
                    "event_id": _link_id(ann) or ann.get("id"),
                    "event_type": "announcement",
                    "group_id": group_id,
                    "group_name": group_name,
                    "title": title,
                    "created_at": ann.get("createdAt", ""),
                    "last_modified_at": ts,
                }
                if query and not _matches_any_field(entry, query, "title", "group_name"):
                    continue
                announcements.append(entry)

        announcements.sort(key=lambda a: a["last_modified_at"], reverse=True)
        announcements = announcements[:limit]
        payload: dict = {"announcements": announcements, "count": len(announcements), "since": since}
        if query:
            payload["query"] = query
        return json.dumps(payload)
    except Exception as exc:
        logger.error("parro_get_announcements: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_get_calendar(args: dict, **_) -> str:
    try:
        client = get_client()
        since = args.get("since") or _today_iso()
        query = _query_arg(args)
        limit = _int_arg(args, "limit", 10)
        items = client.get_calendar_events(since=since)

        events = []
        for evt in items:
            ci = _calendar_item(evt)
            title = _event_title(evt)
            entry = {
                "event_id": _link_id(evt) or evt.get("id"),
                "event_type": "calendar",
                "title": title,
                "date": _event_date(evt),
                "children": [c.get("child", {}).get("firstname", "") for c in evt.get("children", [])],
                "cancelled": evt.get("cancelled", False),
                "last_modified_at": evt.get("lastModifiedAt", ""),
            }
            if ci.get("type"):
                entry["item_type"] = ci["type"]
            if query and not _text_matches(title, query):
                continue
            events.append(entry)

        events = events[:limit]
        payload: dict = {"events": events, "count": len(events)}
        if query:
            payload["query"] = query
        return json.dumps(payload)
    except Exception as exc:
        logger.error("parro_get_calendar: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_get_event_detail(args: dict, **_) -> str:
    try:
        event_id = int(args["event_id"])
        event_type = args.get("event_type", "")
        # Map friendly type names to Parro dtypes
        dtype_map = {
            "announcement": "event.RAnnouncementEvent",
            "calendar": "event.RCalendarItemEvent",
        }
        dtype = dtype_map.get(event_type)
        detail = get_client().get_event_detail(event_id, dtype=dtype)
        ci = _calendar_item(detail)
        payload = {
            "event_id": event_id,
            "dtype": detail.get("dtype", ""),
            "title": _event_title(detail),
            "body": _event_body(detail),
            "date": _event_date(detail),
            "cancelled": detail.get("cancelled", False),
            "last_modified_at": detail.get("lastModifiedAt", ""),
        }
        if ci.get("type"):
            payload["item_type"] = ci["type"]
        if ci.get("startDate"):
            payload["start_date"] = ci["startDate"]
        if ci.get("endDate"):
            payload["end_date"] = ci["endDate"]
        return json.dumps(payload)
    except Exception as exc:
        logger.error("parro_get_event_detail: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_send_message(args: dict, **_) -> str:
    try:
        result = get_client().send_message(int(args["chatroom_id"]), str(args["text"]))
        created = (result.get("items") or [None])[0] or result
        message_id = _link_id(created) or created.get("id")
        payload: dict = {"success": True, "chatroom_id": int(args["chatroom_id"])}
        if message_id is not None:
            payload["message_id"] = message_id
        return json.dumps(payload)
    except Exception as exc:
        logger.error("parro_send_message: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_get_contacts(args: dict, **_) -> str:
    try:
        query = (args.get("query") or "").strip()
        contacts = get_client().get_chat_contacts()
        result: list[dict] = []
        by_id: dict[int, dict] = {}

        def add(entry: dict) -> None:
            contact_id = entry.get("contact_id")
            if contact_id is None:
                return
            if contact_id in by_id:
                _merge_contact_entry(by_id[contact_id], entry)
            else:
                by_id[contact_id] = entry

        for c in contacts:
            dtype = c.get("dtype", "")
            entry: dict = {
                "contact_id": _link_id(c),
                "name": f"{c.get('firstname', '')} {c.get('surname', '')}".strip(),
                "role": c.get("role") or (
                    "CHILD" if "Child" in dtype else
                    "TEACHER" if "Teacher" in dtype else
                    "GUARDIAN"
                ),
                "in_chat_room": c.get("inChatRoom", False),
            }
            # For children: include the names and IDs of their parents/guardians
            if c.get("guardianNames"):
                entry["guardian_names"] = c["guardianNames"]
            if c.get("guardians"):
                entry["guardians"] = [
                    {
                        "contact_id": _link_id(g),
                        "name": f"{g.get('firstname', '')} {g.get('surname', '')}".strip(),
                    }
                    for g in c["guardians"]
                ]
            # For guardians: include which children they belong to
            if c.get("childNames"):
                entry["child_names"] = c["childNames"]

            if not query:
                result.append(entry)
                continue

            child_name = entry["name"]
            self_hit = _text_matches(child_name, query)
            child_names_hit = any(
                _text_matches(name, query) for name in entry.get("child_names", [])
            )
            guardian_hit = any(
                _text_matches(name, query) for name in entry.get("guardian_names", [])
            )

            for guardian in c.get("guardians", []):
                guardian_name = f"{guardian.get('firstname', '')} {guardian.get('surname', '')}".strip()
                this_guardian_hit = _text_matches(guardian_name, query)
                if this_guardian_hit:
                    guardian_hit = True
                if this_guardian_hit or self_hit:
                    add(_guardian_contact_entry(guardian, child_name))

            if self_hit or child_names_hit or guardian_hit:
                add(entry)

        if query:
            result = list(by_id.values())

        payload: dict = {"contacts": result, "count": len(result)}
        if query:
            payload["query"] = query
        return json.dumps(payload)
    except Exception as exc:
        logger.error("parro_get_contacts: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_start_chat(args: dict, **_) -> str:
    try:
        client = get_client()
        contact_id = int(args["contact_id"])
        contacts = client.get_chat_contacts()

        # First look in top-level contacts
        contact = next((c for c in contacts if _link_id(c) == contact_id), None)

        # If not found, search within children's guardian lists
        # (parent IDs come from child.guardians[].links[rel=self].id)
        if contact is None:
            for c in contacts:
                for guardian in c.get("guardians", []):
                    if _link_id(guardian) == contact_id:
                        contact = guardian
                        break
                if contact is not None:
                    break

        if contact is None:
            return json.dumps({"error": f"Contact {contact_id} not found. Use parro_get_contacts to list available contacts."})

        result = client.create_chatroom(contact)
        new_id = None
        for link in (result.get("links") or result.get("items", [{}])[0].get("links", [])):
            if link.get("rel") == "self":
                new_id = link.get("id")
                break
        return json.dumps({"success": True, "chatroom_id": new_id})
    except Exception as exc:
        logger.error("parro_start_chat: %s", exc)
        return json.dumps({"error": str(exc)})

