"""Hermes Parro plugin — register tools."""
import logging

logger = logging.getLogger(__name__)

_KEYS_HELP = (
    "Parro credentials are not configured.\n\n"
    "Set **PARRO_USERNAME** and **PARRO_PASSWORD** via Hermes:\n"
    "```\nhermes keys\n```\n"
    "or reinstall the plugin to be prompted again:\n"
    "```\nhermes plugins install omdathetkan/hermes-parro\n```"
)


def register(ctx):
    from .schemas import (
        PARRO_GET_ANNOUNCEMENTS_SCHEMA,
        PARRO_GET_MESSAGES_SCHEMA,
        PARRO_GET_UNREAD_SCHEMA,
        PARRO_SEND_MESSAGE_SCHEMA,
    )
    from .tools import (
        check_parro_available,
        handle_parro_get_announcements,
        handle_parro_get_messages,
        handle_parro_get_unread,
        handle_parro_send_message,
    )

    ctx.register_tool(
        name="parro_get_unread",
        toolset="parro",
        schema=PARRO_GET_UNREAD_SCHEMA,
        handler=lambda args, **kw: handle_parro_get_unread(args, **kw),
        check_fn=check_parro_available,
    )
    ctx.register_tool(
        name="parro_get_messages",
        toolset="parro",
        schema=PARRO_GET_MESSAGES_SCHEMA,
        handler=lambda args, **kw: handle_parro_get_messages(args, **kw),
        check_fn=check_parro_available,
    )
    ctx.register_tool(
        name="parro_get_announcements",
        toolset="parro",
        schema=PARRO_GET_ANNOUNCEMENTS_SCHEMA,
        handler=lambda args, **kw: handle_parro_get_announcements(args, **kw),
        check_fn=check_parro_available,
    )
    ctx.register_tool(
        name="parro_send_message",
        toolset="parro",
        schema=PARRO_SEND_MESSAGE_SCHEMA,
        handler=lambda args, **kw: handle_parro_send_message(args, **kw),
        check_fn=check_parro_available,
    )

    if not check_parro_available():
        logger.warning("hermes-parro: credentials not set — Parro tools are disabled. "
                       "Set PARRO_USERNAME and PARRO_PASSWORD via `hermes keys`.")

    logger.info("hermes-parro loaded (authenticated: %s)", check_parro_available())
