"""JSON schemas for Parro tools (what the LLM sees)."""

PARRO_GET_UNREAD_SCHEMA = {
    "name": "parro_get_unread",
    "description": (
        "Check Parro for unread activity. Returns unread counts for chat messages "
        "and announcements, plus a list of which chatrooms have unread messages."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

PARRO_GET_MESSAGES_SCHEMA = {
    "name": "parro_get_messages",
    "description": (
        "Fetch messages from Parro chatrooms. By default returns messages from all "
        "chatrooms that have unread messages. Pass chatroom_id to fetch a specific room. "
        "Each message includes the sender, text, and timestamp."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chatroom_id": {
                "type": "integer",
                "description": (
                    "ID of a specific chatroom to fetch. "
                    "Omit to fetch all chatrooms with unread messages."
                ),
            },
            "unread_only": {
                "type": "boolean",
                "description": "When true (default), only fetch chatrooms with unread messages.",
                "default": True,
            },
        },
        "required": [],
    },
}

PARRO_GET_ANNOUNCEMENTS_SCHEMA = {
    "name": "parro_get_announcements",
    "description": (
        "Fetch announcements from all school groups in Parro. "
        "Returns title, body, group name, and timestamps sorted by most recent first."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum announcements to return per group (default: 10).",
                "default": 10,
            },
        },
        "required": [],
    },
}

PARRO_SEND_MESSAGE_SCHEMA = {
    "name": "parro_send_message",
    "description": "Send a reply to a Parro chatroom.",
    "parameters": {
        "type": "object",
        "properties": {
            "chatroom_id": {
                "type": "integer",
                "description": "ID of the chatroom to send the message to.",
            },
            "text": {
                "type": "string",
                "description": "The message text to send.",
            },
        },
        "required": ["chatroom_id", "text"],
    },
}
