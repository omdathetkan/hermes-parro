"""Parro tool handlers."""
import json
import logging
from datetime import datetime, timezone

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
        rooms = get_client().get_chatrooms()
        result = [
            {
                "id": _link_id(r),
                "name": _room_name(r),
                "type": r.get("type"),
                "unread_count": _unread_count(r),
                "muted": r.get("muted", False),
                "archived": r.get("archived", False),
            }
            for r in rooms
        ]
        return json.dumps({"chats": result, "count": len(result)})
    except Exception as exc:
        logger.error("parro_list_chats: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_get_messages(args: dict, **_) -> str:
    try:
        client = get_client()
        chatroom_id = args.get("chatroom_id")
        unread_only = args.get("unread_only", True)
        since = args.get("since")
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
            for msg in client.get_messages(rid):
                if msg.get("deleted"):
                    continue
                if str(msg.get("identity", {}).get("id", "")) == my_id:
                    continue
                ts = msg.get("lastModifiedAt", "")
                if not _after(ts, since):
                    continue
                messages.append({
                    "chatroom_id": rid,
                    "chatroom_name": room.get("name", f"Room {rid}"),
                    "message_id": _link_id(msg) or msg.get("id"),
                    "text": msg.get("text") or "",
                    "dtype": msg.get("dtype", ""),
                    "sender_id": str(msg.get("identity", {}).get("id", "")),
                    "timestamp": ts,
                })

        messages.sort(key=lambda m: m["timestamp"], reverse=True)
        return json.dumps({"messages": messages, "count": len(messages)})
    except Exception as exc:
        logger.error("parro_get_messages: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_get_announcements(args: dict, **_) -> str:
    try:
        client = get_client()
        since = args.get("since")
        limit = int(args.get("limit", 10))
        groups = client.get_groups()

        announcements = []
        for group in groups:
            group_id = _link_id(group)
            group_name = group.get("name") or f"Group {group_id}"
            if group_id is None:
                continue
            for ann in client.get_announcements(group_id)[:limit]:
                ts = ann.get("lastModifiedAt", "")
                if not _after(ts, since):
                    continue
                announcements.append({
                    "event_id": _link_id(ann) or ann.get("id"),
                    "event_type": "announcement",
                    "group_id": group_id,
                    "group_name": group_name,
                    "title": ann.get("title") or "",
                    "body": ann.get("contents") or ann.get("body") or "",
                    "created_at": ann.get("createdAt", ""),
                    "last_modified_at": ts,
                })

        announcements.sort(key=lambda a: a["last_modified_at"], reverse=True)
        return json.dumps({"announcements": announcements, "count": len(announcements)})
    except Exception as exc:
        logger.error("parro_get_announcements: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_get_calendar(args: dict, **_) -> str:
    try:
        client = get_client()
        since = args.get("since") or _today_iso()
        limit = int(args.get("limit", 20))
        items = client.get_calendar_events(since=since)[:limit]

        events = []
        for evt in items:
            events.append({
                "event_id": _link_id(evt) or evt.get("id"),
                "event_type": "calendar",
                "title": evt.get("title") or "",
                "body": evt.get("contents") or evt.get("body") or "",
                "date": evt.get("sortDate") or evt.get("createdAt", ""),
                "children": [c.get("child", {}).get("firstname", "") for c in evt.get("children", [])],
                "cancelled": evt.get("cancelled", False),
                "last_modified_at": evt.get("lastModifiedAt", ""),
            })
        return json.dumps({"events": events, "count": len(events)})
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
        return json.dumps({
            "event_id": event_id,
            "dtype": detail.get("dtype", ""),
            "title": detail.get("title") or "",
            "body": detail.get("contents") or detail.get("body") or detail.get("text") or "",
            "date": detail.get("sortDate") or detail.get("createdAt", ""),
            "cancelled": detail.get("cancelled", False),
            "last_modified_at": detail.get("lastModifiedAt", ""),
        })
    except Exception as exc:
        logger.error("parro_get_event_detail: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_send_message(args: dict, **_) -> str:
    try:
        result = get_client().send_message(int(args["chatroom_id"]), str(args["text"]))
        return json.dumps({"success": True, "result": result})
    except Exception as exc:
        logger.error("parro_send_message: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_get_contacts(args: dict, **_) -> str:
    try:
        contacts = get_client().get_chat_contacts()
        result = []
        for c in contacts:
            result.append({
                "contact_id": _link_id(c),
                "name": f"{c.get('firstname', '')} {c.get('surname', '')}".strip(),
                "role": c.get("role") or c.get("dtype", ""),
                "child_names": c.get("childNames", []),
                "in_chat_room": c.get("inChatRoom", False),
            })
        return json.dumps({"contacts": result, "count": len(result)})
    except Exception as exc:
        logger.error("parro_get_contacts: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_start_chat(args: dict, **_) -> str:
    try:
        client = get_client()
        contact_id = int(args["contact_id"])
        contacts = client.get_chat_contacts()
        contact = next((c for c in contacts if _link_id(c) == contact_id), None)
        if contact is None:
            return json.dumps({"error": f"Contact {contact_id} not found. Use parro_get_contacts to list available contacts."})
        result = client.create_chatroom(contact)
        # Extract the new chatroom ID from links[rel=self]
        new_id = None
        for link in (result.get("links") or result.get("items", [{}])[0].get("links", [])):
            if link.get("rel") == "self":
                new_id = link.get("id")
                break
        return json.dumps({"success": True, "chatroom_id": new_id, "result": result})
    except Exception as exc:
        logger.error("parro_start_chat: %s", exc)
        return json.dumps({"error": str(exc)})

