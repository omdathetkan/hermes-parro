"""Hermes Parro plugin — register tools and the /parro-auth command."""
import logging

logger = logging.getLogger(__name__)


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

    # /parro-auth — starts the local auth server and opens the browser
    def cmd_parro_auth(_args: str):
        from .auth_server import start_auth_server
        import webbrowser

        try:
            _server, url = start_auth_server()
            webbrowser.open(url)
            opened = True
        except Exception as exc:
            logger.warning("Could not start auth server: %s", exc)
            return f"❌ Failed to start auth server: {exc}"

        return (
            "**Parro Auth**\n\n"
            f"{'Browser opened automatically. If not, open this URL manually:' if opened else 'Open this URL in your browser:'}\n"
            f"**{url}**\n\n"
            "Enter your Parro username and password. "
            "Hermes will verify them immediately and save them locally.\n\n"
            "Your credentials are stored in `~/.hermes/parro.json` (mode 600) "
            "and never sent anywhere except to Parro's own login server.\n\n"
            "> **Running Hermes on a remote server?** SSH tunnel first: "
            "`ssh -L 9877:localhost:9877 user@your-server`, then open the link."
        )

    ctx.register_command(
        name="parro-auth",
        handler=cmd_parro_auth,
        description="Authenticate with Parro — opens a browser form for your username and password",
    )

    logger.info("hermes-parro loaded (authenticated: %s)", check_parro_available())
