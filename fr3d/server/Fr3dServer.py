#!/usr/bin/env python3
"""Serve Fr3d requests through the async ZMQ transport."""

from __future__ import annotations

import asyncio
import signal
import sys
import uuid
from pathlib import Path

import zmq

from fr3d.constants.DFr3d import DFr3d as FRED
from fr3d.constants.DModule import DModule
from fr3d.constants.DSnakeLab import DSnakeLab
from fr3d.zmq.ZMQClient import ZMQClient
from fr3d.zmq.ZMQServer import MsgHandler, ZMQServer


class Fr3dServer:
    """Accept and dispatch Fr3d service requests."""

    def __init__(
        self,
        address: str = FRED.HOST,
        port: int = FRED.PORT,
        log_file: str | Path | None = FRED.FRED_SERVER_LOG,
        *,
        srv_methods: dict[str, MsgHandler] | None = None,
    ) -> None:
        self.zmq_server = ZMQServer(
            address=address,
            port=port,
            identity=DModule.FR3D,
            log_file=log_file,
            srv_methods=srv_methods,
        )
        self.log = self.zmq_server.log
        self.endpoint = self.zmq_server.endpoint
        self._stop_event = asyncio.Event()
        self._running = False

    async def run(self) -> None:
        """Serve until stopped, cancelled, or the transport fails."""
        if self._running:
            raise RuntimeError("Fr3d server is already running")
        self._running = True
        stop_task = None
        try:
            if self._stop_event.is_set():
                return
            self.zmq_server.start()
            listener = self.zmq_server.listen_task
            assert listener is not None
            stop_task = asyncio.create_task(self._stop_event.wait(), name="fr3d-stop")
            completed, _ = await asyncio.wait(
                (listener, stop_task), return_when=asyncio.FIRST_COMPLETED
            )
            if listener in completed:
                await listener
        finally:
            self._stop_event.set()
            if stop_task is not None:
                stop_task.cancel()
                await asyncio.gather(stop_task, return_exceptions=True)
            try:
                await self.zmq_server.stop()
            finally:
                self._running = False

    def stop(self) -> None:
        """Request shutdown from the event loop or a signal handler."""
        self._stop_event.set()

    def is_simulation_running(self, context: zmq.Context | None = None) -> bool:
        """Return whether SnakeLab has an active or queued simulation."""
        request_id = str(uuid.uuid4())
        client = ZMQClient(DSnakeLab.ENDPOINT, timeout=DSnakeLab.TIMEOUT, context=context)
        response = client.request_json({
            "protocol_version": DSnakeLab.PROTOCOL_VERSION,
            "request_id": request_id,
            "method": "simulation.active",
            "payload": {},
        })

        if not isinstance(response, dict):
            raise ValueError("invalid SnakeLab response")
        if response.get("protocol_version") != DSnakeLab.PROTOCOL_VERSION:
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


async def amain() -> None:
    server = Fr3dServer()
    loop = asyncio.get_running_loop()
    registered_signals = []
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, server.stop)
            registered_signals.append(signum)
        await server.run()
    finally:
        for signum in registered_signals:
            loop.remove_signal_handler(signum)
        await server.zmq_server.stop()


def main() -> int:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError, ValueError, zmq.ZMQError) as error:
        print(f"Fr3dServer: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
