"""Unified CLI runner supporting Copilot CLI, Claude CLI, and Codex CLI."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class CLIType:
    """Supported CLI types."""
    COPILOT = "copilot"
    CLAUDE = "claude"
    CODEX = "codex"

    ALL = {COPILOT, CLAUDE, CODEX}


def detect_cli_type(command: str) -> str:
    """Detect CLI type from command name."""
    command_lower = command.lower().strip()

    if "claude" in command_lower:
        return CLIType.CLAUDE
    elif "codex" in command_lower:
        return CLIType.CODEX
    elif "copilot" in command_lower:
        return CLIType.COPILOT
    else:
        # Default to copilot for backward compatibility
        return CLIType.COPILOT


def resolve_project_path(path_value: str | Path) -> Path:
    """Resolve a path inside the project root."""
    root = PROJECT_ROOT.resolve()
    path = Path(path_value)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"路径必须位于项目目录内: {resolved}") from exc

    return resolved


def resolve_data_path(path_value: str | Path) -> Path:
    """Resolve data paths that may be absolute or project-relative."""
    path = Path(path_value)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def get_configured_mcp_servers(command: str) -> list[str]:
    """List configured MCP servers for the current CLI."""
    cli_type = detect_cli_type(command)

    try:
        if cli_type == CLIType.COPILOT:
            result = subprocess.run(
                [command, "mcp", "list"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        elif cli_type == CLIType.CLAUDE:
            # Claude CLI uses /mcp command
            result = subprocess.run(
                [command, "mcp", "list"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        elif cli_type == CLIType.CODEX:
            # Codex CLI MCP listing (assuming similar to Claude)
            result = subprocess.run(
                [command, "mcp", "list"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        else:
            raise RuntimeError(f"不支持的 CLI 类型: {cli_type}")

    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{command} MCP 配置检查超时（>30 秒）") from exc

    output = "\n".join(
        part
        for part in [(result.stdout or "").strip(), (result.stderr or "").strip()]
        if part
    )
    if result.returncode != 0:
        raise RuntimeError(f"{command} MCP 配置检查失败:\n{output}")

    servers: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.endswith(":"):
            continue
        server_name = stripped.split(" ", 1)[0].split(":")[0]
        if server_name:
            servers.append(server_name)
            print(f"检测到 MCP 服务器: {server_name}")

    return servers


def validate_cli_environment(
    *,
    command: str,
    required_mcp_servers: Sequence[str] | None = None,
):
    """Ensure CLI and required MCP servers are available."""
    if not shutil.which(command):
        raise RuntimeError(f"未找到 CLI 命令: {command}")

    configured_servers = get_configured_mcp_servers(command)
    missing_servers = [
        server for server in (required_mcp_servers or []) if server not in configured_servers
    ]
    if missing_servers:
        raise RuntimeError(
            f"{command} 缺少所需 MCP 服务器: " + ", ".join(sorted(missing_servers))
        )


def build_cli_command(
    *,
    command: str,
    prompt: str,
    configured_mcp_servers: Sequence[str],
    required_mcp_servers: Sequence[str] | None = None,
    add_dirs: Iterable[Path] | None = None,
    model: str = "",
    reasoning_effort: str = "",
) -> list[str]:
    """Build a CLI command for a prompt task."""
    cli_type = detect_cli_type(command)

    if cli_type == CLIType.COPILOT:
        return _build_copilot_command(
            command=command,
            prompt=prompt,
            configured_mcp_servers=configured_mcp_servers,
            required_mcp_servers=required_mcp_servers,
            add_dirs=add_dirs,
            model=model,
            reasoning_effort=reasoning_effort,
        )
    elif cli_type == CLIType.CLAUDE:
        return _build_claude_command(
            command=command,
            prompt=prompt,
            configured_mcp_servers=configured_mcp_servers,
            required_mcp_servers=required_mcp_servers,
            add_dirs=add_dirs,
            model=model,
            # reasoning_effort=reasoning_effort,
        )
    elif cli_type == CLIType.CODEX:
        return _build_codex_command(
            command=command,
            prompt=prompt,
            configured_mcp_servers=configured_mcp_servers,
            required_mcp_servers=required_mcp_servers,
            add_dirs=add_dirs,
            model=model,
            reasoning_effort=reasoning_effort,
        )
    else:
        raise RuntimeError(f"不支持的 CLI 类型: {cli_type}")


def _build_copilot_command(
    *,
    command: str,
    prompt: str,
    configured_mcp_servers: Sequence[str],
    required_mcp_servers: Sequence[str] | None = None,
    add_dirs: Iterable[Path] | None = None,
    model: str = "",
    reasoning_effort: str = "",
) -> list[str]:
    """Build a Copilot CLI command."""
    cmd = [
        command,
        "-p",
        prompt,
        "--allow-all-tools",
        "--no-custom-instructions",
        "--no-ask-user",
        "--stream",
        "off",
    ]

    for add_dir in add_dirs or []:
        cmd.extend(["--add-dir", str(add_dir)])

    # allowed_servers = set(required_mcp_servers or [])
    # for server_name in configured_mcp_servers:
    #     if server_name not in allowed_servers:
    #         cmd.extend(["--disable-mcp-server", server_name])

    if model.strip():
        cmd.extend(["--model", model.strip()])

    if reasoning_effort.strip():
        cmd.extend(["--reasoning-effort", reasoning_effort.strip()])

    return cmd


def _build_claude_command(
    *,
    command: str,
    prompt: str,
    configured_mcp_servers: Sequence[str],
    required_mcp_servers: Sequence[str] | None = None,
    add_dirs: Iterable[Path] | None = None,
    model: str = "",
    reasoning_effort: str = "",
) -> list[str]:
    """Build a Claude CLI command."""
    cmd = [command]

    # Claude CLI uses -p or --prompt for prompt input
    cmd.extend(["-p", prompt])

    # Add directories to context
    for add_dir in add_dirs or []:
        cmd.extend(["--add-dir", str(add_dir)])

    # Disable non-required MCP servers
    # allowed_servers = set(required_mcp_servers or [])
    # for server_name in configured_mcp_servers:
    #     if server_name not in allowed_servers:
    #         cmd.extend(["--disable-mcp-server", server_name])

    # Model selection
    if model.strip():
        cmd.extend(["--model", model.strip()])

    # Reasoning effort (if supported)
    if reasoning_effort.strip():
        cmd.extend(["--reasoning-effort", reasoning_effort.strip()])

    # Non-interactive mode
    cmd.extend(["--dangerously-skip-permissions"])

    return cmd


def _build_codex_command(
    *,
    command: str,
    prompt: str,
    configured_mcp_servers: Sequence[str],
    required_mcp_servers: Sequence[str] | None = None,
    add_dirs: Iterable[Path] | None = None,
    model: str = "",
    reasoning_effort: str = "",
) -> list[str]:
    """Build a Codex CLI command."""
    cmd = [command]

    # Codex CLI prompt input
    cmd.extend(["-p", prompt])

    # Add directories to context
    for add_dir in add_dirs or []:
        cmd.extend(["--add-dir", str(add_dir)])

    # Disable non-required MCP servers
    # allowed_servers = set(required_mcp_servers or [])
    # for server_name in configured_mcp_servers:
    #     if server_name not in allowed_servers:
    #         cmd.extend(["--disable-mcp-server", server_name])

    # Model selection
    if model.strip():
        cmd.extend(["--model", model.strip()])

    # Reasoning effort (if supported)
    if reasoning_effort.strip():
        cmd.extend(["--reasoning-effort", reasoning_effort.strip()])

    # Non-interactive mode
    cmd.extend(["--no-ask-user"])

    return cmd


def write_run_log(
    *,
    log_dir: Path,
    filename_prefix: str,
    timestamp: str,
    command: list[str],
    prompt: str,
    stdout: str | None,
    stderr: str | None,
    exit_code: int | None,
) -> Path:
    """Persist a CLI task execution log."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{filename_prefix}_{timestamp}.log"
    content = [
        f"timestamp: {timestamp}",
        f"cwd: {PROJECT_ROOT}",
        f"exit_code: {exit_code if exit_code is not None else 'timeout'}",
        f"command: {shlex.join(command)}",
        "",
        "=== PROMPT ===",
        prompt,
        "",
        "=== STDOUT ===",
        stdout or "",
        "",
        "=== STDERR ===",
        stderr or "",
        "",
    ]
    log_path.write_text("\n".join(content), encoding="utf-8")
    return log_path
