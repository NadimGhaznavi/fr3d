"""Synchronous JSON request/reply transport for SnakeLab and Fr3d."""

from __future__ import annotations

import math
from typing import Any

import zmq
import zmq.asyncio

from fr3d.constants.DFr3d import DFr3d
from fr3d.zmq.ZMQMsg import ZMQMsg


class ZMQClient:
    """Connect for each request; leave application protocol checks to callers.

    An optional synchronous context belongs to the caller and is never terminated.
    Otherwise, each request creates and terminates its own context. No socket is
    kept between calls, including after a timeout or malformed response.
    """

    def __init__(
        self,
        endpoint: str,
        timeout: float = DFr3d.ZMQ_TIMEOUT,
        *,
        context: zmq.Context | None = None,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be a positive, finite number of seconds")
        if isinstance(context, zmq.asyncio.Context):
            raise TypeError("ZMQClient requires a synchronous ZMQ context")
        self.endpoint = endpoint
        self.timeout = timeout
        self._timeout_ms = math.ceil(timeout * 1000)
        self._context = context

    def request_json(self, message: dict[str, Any]) -> Any:
        """Send JSON and return decoded JSON without application validation.

        Send and receive each have the configured timeout (in seconds).
        ZMQ errors, including ``zmq.Again`` on timeout, and JSON errors propagate.
        Requests are never retried automatically because they may have side effects.
        """
        context = self._context if self._context is not None else zmq.Context()
        try:
            with context.socket(zmq.REQ) as socket:
                socket.setsockopt(zmq.LINGER, 0)
                socket.setsockopt(zmq.SNDTIMEO, self._timeout_ms)
                socket.setsockopt(zmq.RCVTIMEO, self._timeout_ms)
                socket.connect(self.endpoint)
                socket.send_json(message)
                return socket.recv_json()
        finally:
            if self._context is None:
                context.term()

    def request(self, message: ZMQMsg) -> ZMQMsg:
        """Exchange Fr3d messages; error replies remain messages for callers to inspect."""
        return ZMQMsg.from_dict(self.request_json(message.to_dict()))
