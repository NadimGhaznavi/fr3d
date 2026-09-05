#!/usr/bin/env python3
"""Poll SnakeLab before performing the next agent action."""

from __future__ import annotations

import time
import uuid

import zmq


from constants.DFr3d import DFr3d
from constants.DModule import DModule
from constants.DMyLog import DMyLogDef
from utils.MyLog import MyLog


def is_simulation_running(context: zmq.Context) -> bool:
    """Return whether SnakeLab has an active or queued simulation."""
    request_id = str(uuid.uuid4())
    with context.socket(zmq.REQ) as socket:
        socket.setsockopt(zmq.LINGER, 0)
        socket.setsockopt(zmq.SNDTIMEO, DFr3d.SNAKE_LAB_TIMEOUT * 1000)
        socket.setsockopt(zmq.RCVTIMEO, DFr3d.SNAKE_LAB_TIMEOUT * 1000)
        socket.connect(DFr3d.SNAKE_LAB_ENDPOINT)
        socket.send_json({
            "protocol_version": DFr3d.SNAKE_LAB_PROTOCOL_VERSION,
            "request_id": request_id,
            "method": "simulation.active",
            "payload": {},
        })
        response = socket.recv_json()

    if not isinstance(response, dict):
        raise ValueError("invalid SnakeLab response")
    if response.get("protocol_version") != DFr3d.SNAKE_LAB_PROTOCOL_VERSION:
        raise ValueError("unsupported SnakeLab protocol")
    if response.get("request_id") != request_id:
        raise ValueError("SnakeLab request_id mismatch")
    if response.get("status") != "ok":
        raise RuntimeError(f"SnakeLab request failed: {response.get('error')}")
    payload = response.get("payload")
    if not isinstance(payload, dict) or "run" not in payload:
        raise ValueError("invalid SnakeLab active simulation payload")
    run = payload["run"]
    if run is None:
        return False
    if not isinstance(run, dict) or run.get("state") not in (
        "running", "paused", "cancelling", "queued"
    ):
        raise ValueError("invalid SnakeLab active simulation state")
    return True


def main() -> int:
    log = MyLog(
        client_id=DModule.FR3D,
        log_level=DMyLogDef.DEFAULT_LOG_LEVEL,
        log_file=str(DFr3d.FRED_SERVER_LOG),
        to_console=True,
    )
    log.info("Fr3d LLM backed Agent: Starting...")

    with zmq.Context() as context:
        while True:
            try:
                running = is_simulation_running(context)
            except (zmq.ZMQError, ValueError, RuntimeError) as error:
                log.error(f"Fr3d: failed to query SnakeLab: {error}")
            else:
                if not running:
                    log.info("Fr3d: no simulation is running; LLM query pending.")
            time.sleep(DFr3d.FR3D_POLL_INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
