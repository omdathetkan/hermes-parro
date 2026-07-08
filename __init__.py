"""Hermes Parro plugin — register tools."""
import logging

logger = logging.getLogger(__name__)


def register(ctx):
    from .schemas import (
        PARRO_GET_ANNOUNCEMENTS_SCHEMA,
        PARRO_GET_CALENDAR_SCHEMA,
        PARRO_GET_CONTACTS_SCHEMA,
        PARRO_GET_EVENT_DETAIL_SCHEMA,
        PARRO_GET_MESSAGES_SCHEMA,
        PARRO_GET_UNREAD_SCHEMA,
        PARRO_LIST_CHATS_SCHEMA,
        PARRO_SEND_MESSAGE_SCHEMA,
        PARRO_START_CHAT_SCHEMA,
    )
    from .tools import (
        check_parro_available,
        handle_parro_get_announcements,
        handle_parro_get_calendar,
        handle_parro_get_contacts,
        handle_parro_get_event_detail,
        handle_parro_get_messages,
        handle_parro_get_unread,
        handle_parro_list_chats,
        handle_parro_send_message,
        handle_parro_start_chat,
    )

    _kw = {"check_fn": check_parro_available, "toolset": "parro"}

    ctx.register_tool(name="parro_get_unread",      schema=PARRO_GET_UNREAD_SCHEMA,      handler=lambda a, **k: handle_parro_get_unread(a, **k),      **_kw)
    ctx.register_tool(name="parro_list_chats",      schema=PARRO_LIST_CHATS_SCHEMA,      handler=lambda a, **k: handle_parro_list_chats(a, **k),      **_kw)
    ctx.register_tool(name="parro_get_messages",    schema=PARRO_GET_MESSAGES_SCHEMA,    handler=lambda a, **k: handle_parro_get_messages(a, **k),    **_kw)
    ctx.register_tool(name="parro_get_announcements", schema=PARRO_GET_ANNOUNCEMENTS_SCHEMA, handler=lambda a, **k: handle_parro_get_announcements(a, **k), **_kw)
    ctx.register_tool(name="parro_get_calendar",    schema=PARRO_GET_CALENDAR_SCHEMA,    handler=lambda a, **k: handle_parro_get_calendar(a, **k),    **_kw)
    ctx.register_tool(name="parro_get_event_detail", schema=PARRO_GET_EVENT_DETAIL_SCHEMA, handler=lambda a, **k: handle_parro_get_event_detail(a, **k), **_kw)
    ctx.register_tool(name="parro_send_message",    schema=PARRO_SEND_MESSAGE_SCHEMA,    handler=lambda a, **k: handle_parro_send_message(a, **k),    **_kw)
    ctx.register_tool(name="parro_get_contacts",    schema=PARRO_GET_CONTACTS_SCHEMA,    handler=lambda a, **k: handle_parro_get_contacts(a, **k),    **_kw)
    ctx.register_tool(name="parro_start_chat",      schema=PARRO_START_CHAT_SCHEMA,      handler=lambda a, **k: handle_parro_start_chat(a, **k),      **_kw)

    if not check_parro_available():
        logger.warning("hermes-parro: credentials not set — Parro tools disabled. "
                       "Set PARRO_USERNAME and PARRO_PASSWORD via `hermes keys`.")

    logger.info("hermes-parro loaded (%s tools, authenticated: %s)",
                9, check_parro_available())

