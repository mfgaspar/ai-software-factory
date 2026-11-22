"""``compose serve``: the HTTP API."""

from __future__ import annotations

import typer

from compose.cli.common import err_console, handle_errors, open_store
from compose.core.config import load_config

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


@handle_errors
def serve(
    host: str | None = typer.Option(None, "--host", help="Address to bind (default: config)."),
    port: int | None = typer.Option(None, "--port", help="Port (default: config, 8765)."),
    log_level: str = typer.Option("info", "--log-level", help="uvicorn log level."),
) -> None:
    """Serve the compose API (OpenAPI document at /openapi.json, docs at /docs)."""
    import uvicorn

    from compose.api.app import create_app

    with open_store() as (home, _):
        config = load_config(home)
    bind = host or config.server.host
    if bind not in LOCAL_HOSTS and not config.server.token:
        err_console.print(
            f"[yellow]warning:[/yellow] serving on {bind} without a token; anyone who can"
            " reach it can start runs. Set server.token in config.yml or COMPOSE_API_TOKEN.",
            highlight=False,
        )
    uvicorn.run(
        create_app(home),
        host=bind,
        port=port or config.server.port,
        log_level=log_level,
    )
