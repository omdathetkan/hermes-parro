"""Parro tool handlers."""
import json
import logging

from .client import get_client

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------- check fn

def check_parro_available() -> bool:
    """Return True only if a refresh token is configured."""
    return get_client().is_configured()


# ----------------------------------------------------------------- handlers

def handle_parro_get_unread(args: dict, **_) -> str:
    try:
        client = get_client()
        counts = client.get_unread_counts()
        chatrooms = client.get_chatrooms()

        unread_rooms = []
        for room in chatrooms:
            unread = _unread_count(room)
            if unread > 0:
                unread_rooms.append({
                    "id": _room_id(room),
                    "name": _room_name(room),
                    "unread_count": unread,
                    "muted": room.get("muted", False),
                    "archived": room.get("archived", False),
                })

        return json.dumps({
            "unread_chat_rooms": counts.get("numberOfUnreadChatRooms", 0),
            "unread_announcements": counts.get("numberOfUnreadAnnouncements", 0),
            "unread_calendar_items": counts.get("numberOfUnreadCalendarItems", 0),
            "chatrooms_with_unread": unread_rooms,
        })
    except Exception as exc:
        logger.error("parro_get_unread: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_get_messages(args: dict, **_) -> str:
    try:
        client = get_client()
        chatroom_id = args.get("chatroom_id")
        unread_only = args.get("unread_only", True)
        my_id = str(client.get_my_identity_id())

        if chatroom_id is not None:
            rooms = [{"id": int(chatroom_id), "name": f"Chatroom {chatroom_id}"}]
        else:
            all_rooms = client.get_chatrooms()
            rooms = [
                {"id": _room_id(r), "name": _room_name(r), "unread": _unread_count(r)}
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
                sender_id = str(msg.get("identity", {}).get("id", ""))
                if sender_id == my_id:
                    continue  # skip own messages
                messages.append({
                    "chatroom_id": rid,
                    "chatroom_name": room.get("name", f"Room {rid}"),
                    "message_id": msg.get("id"),
                    "text": msg.get("text") or "",
                    "dtype": msg.get("dtype", ""),
                    "sender_id": sender_id,
                    "timestamp": msg.get("lastModifiedAt", ""),
                })

        # Newest first
        messages.sort(key=lambda m: m["timestamp"], reverse=True)
        return json.dumps({"messages": messages, "count": len(messages)})
    except Exception as exc:
        logger.error("parro_get_messages: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_get_announcements(args: dict, **_) -> str:
    try:
        client = get_client()
        limit = int(args.get("limit", 10))
        groups = client.get_groups()

        announcements = []
        for group in groups:
            group_id = _link_id(group) or group.get("id")
            group_name = group.get("name") or f"Group {group_id}"
            if group_id is None:
                continue
            for ann in client.get_announcements(group_id)[:limit]:
                announcements.append({
                    "group_id": group_id,
                    "group_name": group_name,
                    "announcement_id": ann.get("id"),
                    "title": ann.get("title") or "",
                    "body": ann.get("body") or "",
                    "created_at": ann.get("createdAt", ""),
                    "last_modified_at": ann.get("lastModifiedAt", ""),
                })

        announcements.sort(key=lambda a: a["last_modified_at"], reverse=True)
        return json.dumps({"announcements": announcements, "count": len(announcements)})
    except Exception as exc:
        logger.error("parro_get_announcements: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_parro_send_message(args: dict, **_) -> str:
    try:
        client = get_client()
        chatroom_id = int(args["chatroom_id"])
        text = str(args["text"])
        result = client.send_message(chatroom_id, text)
        return json.dumps({"success": True, "result": result})
    except Exception as exc:
        logger.error("parro_send_message: %s", exc)
        return json.dumps({"error": str(exc)})


# ------------------------------------------------------------------ helpers

def _link_id(obj: dict) -> int | None:
    """Extract the numeric ID from links[rel=self], falling back to obj['id']."""
    for link in obj.get("links", []):
        if link.get("rel") == "self" and "id" in link:
            return link["id"]
    return obj.get("id")


def _room_id(room: dict) -> int | None:
    return _link_id(room)


def _room_name(room: dict) -> str:
    names = room.get("memberNames")
    if names:
        return ", ".join(names)
    return room.get("name") or f"Room {_room_id(room)}"


def _unread_count(room: dict) -> int:
    member = room.get("chatroommember", {})
    if isinstance(member, dict):
        return member.get("unreadCount", 0)
    return room.get("unreadCount", 0)
