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
    "description": "Case-insensitive search term to filter results. Omit to return all matches.",
}

_LIMIT = {
    "type": "integer",
    "description": "Maximum number of items to return after filtering and sorting.",
}

# ------------------------------------------------------------------ read

PARRO_GET_UNREAD_SCHEMA = {
    "name": "parro_get_unread",
    "description": (
        "Check Parro for unread activity. Returns counts for unread chat messages, "
        "announcements, and calendar items, plus which chatrooms have unread messages."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

PARRO_LIST_CHATS_SCHEMA = {
    "name": "parro_list_chats",
    "description": (
        "List Parro chatrooms with their IDs, names, and unread counts. "
        "Use 'query' to find a chatroom by participant or group name. "
        "Use this to find a chatroom_id before sending a message or reading messages."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                **_QUERY,
                "description": "Filter chatrooms by name (participant or group names).",
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
        "Fetch chat messages from Parro. By default returns messages from chatrooms "
        "with unread messages. Pass chatroom_id to fetch a specific room. "
        "Use 'since' to limit to recent messages only."
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
        "Fetch school announcement summaries from all groups in Parro, sorted newest first. "
        "Returns titles and metadata only — use parro_get_event_detail for the full body. "
        "Use 'query' to search by title or group name."
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
        "Fetch upcoming calendar event summaries from Parro. "
        "Returns titles and metadata only — use parro_get_event_detail for the full body. "
        "Use 'query' to search by title."
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
    "description": "Send a reply to a Parro chatroom.",
    "parameters": {
        "type": "object",
        "properties": {
            "chatroom_id": {
                "type": "integer",
                "description": "ID of the chatroom to send to (get from parro_list_chats).",
            },
            "text": {"type": "string", "description": "The message text to send."},
        },
        "required": ["chatroom_id", "text"],
    },
}

PARRO_GET_CONTACTS_SCHEMA = {
    "name": "parro_get_contacts",
    "description": (
        "Search or list people you can start a new private Parro chat with: teachers, children "
        "(classmates), and their parents/guardians. Each child entry includes guardian_names "
        "(parent display names) and guardians (with contact_id for use with parro_start_chat). "
        "Pass 'query' to search by name (e.g. a child's name like 'evan', or a parent/teacher name). "
        "Omit 'query' to return all contacts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Case-insensitive search term matched against contact names, guardian names, "
                    "and child names. Use for questions like 'who is the parent of [child]'. "
                    "Omit to return all contacts."
                ),
            },
        },
        "required": [],
    },
}

PARRO_START_CHAT_SCHEMA = {
    "name": "parro_start_chat",
    "description": (
        "Start a new private Parro chat with a contact. "
        "Get the contact_id from parro_get_contacts first."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "contact_id": {
                "type": "integer",
                "description": "The numeric contact ID from parro_get_contacts.",
            },
        },
        "required": ["contact_id"],
    },
}

