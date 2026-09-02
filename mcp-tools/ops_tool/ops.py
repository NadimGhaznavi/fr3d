"""Read bounded uptime information from the Linux proc filesystem."""

from __future__ import annotations

import json
import os
from pathlib import Path

from constants.DOps import DOps


class OpsError(RuntimeError):
    """Raised when operational information cannot be read safely."""


def _read_uptime_seconds(proc_root: Path) -> float:
    try:
        value = (proc_root / "uptime").read_text(encoding="ascii").split()[0]
        uptime = float(value)
    except (OSError, IndexError, ValueError) as error:
        raise OpsError("unable to read OS uptime") from error
    if uptime < 0:
        raise OpsError("OS returned an invalid uptime")
    return uptime


def _process_details(proc_root: Path, pid: int) -> tuple[str, int, int]:
    """Return a process name, parent PID, and start time in clock ticks."""
    try:
        stat = (proc_root / str(pid) / "stat").read_text(encoding="ascii")
        closing_parenthesis = stat.rfind(")")
        if closing_parenthesis < 0:
            raise ValueError("missing process name terminator")
        name = stat[stat.find("(") + 1 : closing_parenthesis]
        fields = stat[closing_parenthesis + 2 :].split()
        return name, int(fields[1]), int(fields[19])
    except (OSError, IndexError, ValueError) as error:
        raise OpsError(f"unable to read process information for PID {pid}") from error


def _qwen_uptime_seconds(proc_root: Path, start_pid: int) -> float:
    """Find llama-server in this MCP process's ancestry and return its uptime."""
    pid = start_pid
    visited: set[int] = set()
    while pid > 0 and pid not in visited:
        visited.add(pid)
        name, parent_pid, start_ticks = _process_details(proc_root, pid)
        if name == DOps.LLAMA_SERVER_PROCESS:
            try:
                clock_ticks = os.sysconf("SC_CLK_TCK")
            except (OSError, ValueError) as error:
                raise OpsError("unable to read the system clock frequency") from error
            uptime = _read_uptime_seconds(proc_root) - (start_ticks / clock_ticks)
            if uptime < 0:
                raise OpsError("llama-server returned an invalid start time")
            return uptime
        pid = parent_pid
    raise OpsError("llama-server is not an ancestor of the ops tool process")


def _format_duration(seconds: float) -> str:
    total_seconds = int(seconds)
    days, remainder = divmod(total_seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, remaining_seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{remaining_seconds}s")
    return " ".join(parts)


def get_uptime(
    target: str,
    *,
    proc_root: Path = Path("/proc"),
    process_pid: int | None = None,
) -> str:
    """Return JSON uptime data for the OS or the parent llama-server process."""
    if target == DOps.OS:
        seconds = _read_uptime_seconds(proc_root)
    elif target == DOps.LLM:
        seconds = _qwen_uptime_seconds(
            proc_root,
            os.getppid() if process_pid is None else process_pid,
        )
    else:
        raise ValueError(f"target must be {DOps.LLM!r} or {DOps.OS!r}")

    rounded_seconds = int(seconds)
    return json.dumps(
        {
            "target": target,
            "uptime_seconds": rounded_seconds,
            "uptime": _format_duration(rounded_seconds),
        },
        separators=(",", ":"),
    )
