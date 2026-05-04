"""Shared helpers for Copilot CLI automation tasks.

DEPRECATED: This module is kept for backward compatibility.
New code should use cli_runner.py which supports Copilot, Claude, and Codex CLIs.
"""

from __future__ import annotations

# Re-export all functions from cli_runner for backward compatibility
from .cli_runner import (
    PROJECT_ROOT,
    resolve_project_path,
    resolve_data_path,
    get_configured_mcp_servers,
    write_run_log,
)


def validate_copilot_environment(
    *,
    command: str,
    required_mcp_servers: list[str] | None = None,
):
    """Ensure Copilot CLI and required MCP servers are available.

    DEPRECATED: Use cli_runner.validate_cli_environment instead.
    """
    from .cli_runner import validate_cli_environment
    validate_cli_environment(
        command=command,
        required_mcp_servers=required_mcp_servers,
    )


def build_copilot_command(
    *,
    command: str,
    prompt: str,
    configured_mcp_servers: list[str],
    required_mcp_servers: list[str] | None = None,
    add_dirs: list | None = None,
    model: str = "",
    reasoning_effort: str = "",
) -> list[str]:
    """Build a Copilot CLI command for a prompt task.

    DEPRECATED: Use cli_runner.build_cli_command instead.
    """
    from .cli_runner import build_cli_command
    return build_cli_command(
        command=command,
        prompt=prompt,
        configured_mcp_servers=configured_mcp_servers,
        required_mcp_servers=required_mcp_servers,
        add_dirs=add_dirs,
        model=model,
        reasoning_effort=reasoning_effort,
    )

