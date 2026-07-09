"""JSON schemas for all Parro tools."""

_SINCE = {
    "type": "string",
    "description": (
        "ISO 8601 datetime to filter results. Only items modified/created after "
        "this timestamp are returned. Example: '2026-07-01T00:00:00'. "
        "Omit to return all available items."
    ),
}

_QUERY = {
    "type": "string",
    "description": (
        "Case-insensitive search term. ALWAYS provide this when the user mentions a "
        "specific name or topic — omitting it returns the full list (90+ items)."
    ),
}

_LIMIT = {
    "type": "integer",
    "description": "Maximum number of items to return after filtering and sorting.",
}

# ------------------------------------------------------------------ read

PARRO_GET_UNREAD_SCHEMA = {
    "name": "parro_get_unread",
    "description": (
        "Lightweight check for unread Parro activity. Call this FIRST when the user asks "
        "'anything new?' or 'unread messages'. Returns counts plus chatrooms with unread "
        "messages. Follow up with parro_get_messages only if there are unread chats."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

PARRO_LIST_CHATS_SCHEMA = {
    "name": "parro_list_chats",
    "description": (
        "Find existing Parro chatrooms and their chatroom_id. "
        "ALWAYS pass 'query' with a person's first name when looking for a specific chat "
        "(e.g. query='Alexander'). For 1:1 chats, pick the room with type 'SINGLE'. "
        "To message someone you have NOT chatted with yet, use parro_get_contacts + "
        "parro_start_chat instead. Returns at most 20 chatrooms by default."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                **_QUERY,
                "description": (
                    "Filter by participant or group name. Use the first name "
                    "(e.g. 'Alexander', not 'Alexander Ettema'). Required for person lookups."
                ),
            },
            "unread_only": {
                "type": "boolean",
                "description": "Only return chatrooms with unread messages (default: false).",
                "default": False,
            },
            "limit": {
                **_LIMIT,
                "description": "Maximum chatrooms to return (default: 20).",
                "default": 20,
            },
        },
        "required": [],
    },
}

PARRO_GET_MESSAGES_SCHEMA = {
    "name": "parro_get_messages",
    "description": (
        "Read chat messages. Defaults to unread chatrooms only (max 20 messages). "
        "Pass chatroom_id when you already know the room (from parro_list_chats or "
        "parro_start_chat). Check parro_get_unread first to see if there is anything new."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chatroom_id": {
                "type": "integer",
                "description": "Specific chatroom ID to fetch. Omit to fetch all unread chatrooms.",
            },
            "unread_only": {
                "type": "boolean",
                "description": "Only fetch chatrooms with unread messages (default: true).",
                "default": True,
            },
            "since": _SINCE,
            "query": {
                **_QUERY,
                "description": "Filter messages by text content or chatroom name.",
            },
            "limit": {
                **_LIMIT,
                "description": "Maximum messages to return, newest first (default: 20).",
                "default": 20,
            },
        },
        "required": [],
    },
}

PARRO_GET_ANNOUNCEMENTS_SCHEMA = {
    "name": "parro_get_announcements",
    "description": (
        "List recent school announcement summaries (title + date, no body). "
        "Returns at most 10 by default. Use 'query' to search for a specific topic. "
        "Call parro_get_event_detail with the event_id when the user wants the full text."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "since": _SINCE,
            "query": {
                **_QUERY,
                "description": "Filter announcements by title or group name.",
            },
            "limit": {
                **_LIMIT,
                "description": "Maximum announcements to return across all groups (default: 10).",
                "default": 10,
            },
        },
        "required": [],
    },
}

PARRO_GET_CALENDAR_SCHEMA = {
    "name": "parro_get_calendar",
    "description": (
        "List upcoming school calendar events (title + date, no body). "
        "Defaults to events from today, max 10. Use 'query' to find a specific event. "
        "Call parro_get_event_detail with the event_id for full details."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "since": {
                "type": "string",
                "description": (
                    "Start date for calendar events (ISO 8601). "
                    "Defaults to today if omitted."
                ),
            },
            "query": {
                **_QUERY,
                "description": "Filter calendar events by title.",
            },
            "limit": {
                **_LIMIT,
                "description": "Maximum events to return (default: 10).",
                "default": 10,
            },
        },
        "required": [],
    },
}

PARRO_GET_EVENT_DETAIL_SCHEMA = {
    "name": "parro_get_event_detail",
    "description": (
        "Fetch the full content of a single Parro event (announcement or calendar item), "
        "including the body text. Use the event_id and event_type from "
        "parro_get_announcements or parro_get_calendar."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "event_id": {
                "type": "integer",
                "description": "The numeric event ID.",
            },
            "event_type": {
                "type": "string",
                "enum": ["announcement", "calendar"],
                "description": "Type of event — 'announcement' or 'calendar'.",
            },
        },
        "required": ["event_id", "event_type"],
    },
}

# ------------------------------------------------------------------ write / chat

PARRO_SEND_MESSAGE_SCHEMA = {
    "name": "parro_send_message",
    "description": (
        "Send a message in an existing Parro chatroom. Requires chatroom_id — NOT contact_id. "
        "Workflow for new conversations: parro_get_contacts → parro_start_chat → parro_send_message. "
        "Workflow for existing chats: parro_list_chats → parro_send_message."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chatroom_id": {
                "type": "integer",
                "description": (
                    "Chatroom ID from parro_start_chat or parro_list_chats. "
                    "Cannot use contact_id here."
                ),
            },
            "text": {"type": "string", "description": "The message text to send."},
        },
        "required": ["chatroom_id", "text"],
    },
}

PARRO_GET_CONTACTS_SCHEMA = {
    "name": "parro_get_contacts",
    "description": (
        "Look up teachers, children, and parents/guardians by name. "
        "ALWAYS pass 'query' when the user mentions a person — e.g. query='evan' for "
        "'who is Evan's dad?'. Without query this returns 90+ contacts and should only "
        "be used when the user explicitly asks for the full contact list. "
        "Matching parents are returned as GUARDIAN entries with contact_id. "
        "To message a parent: use their contact_id with parro_start_chat, then parro_send_message."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Person to look up (first name is enough, e.g. 'evan', 'Alexander'). "
                    "Matches children, parents/guardians, and teachers. "
                    "REQUIRED for questions like 'who is [child]'s dad/mom/parent'."
                ),
            },
        },
        "required": [],
    },
}

PARRO_START_CHAT_SCHEMA = {
    "name": "parro_start_chat",
    "description": (
        "Open a private 1:1 Parro chat with someone (does not send a message). "
        "Call this before parro_send_message when there is no existing chat yet. "
        "Get contact_id from parro_get_contacts — use the GUARDIAN entry for parents, "
        "not the child. Returns chatroom_id for use with parro_send_message."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "contact_id": {
                "type": "integer",
                "description": (
                    "contact_id of the person to chat with, from parro_get_contacts. "
                    "For parents, use the GUARDIAN entry's contact_id (e.g. Alexander's ID, "
                    "not Evan's)."
                ),
            },
        },
        "required": ["contact_id"],
    },
}

