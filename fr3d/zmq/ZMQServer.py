"""Async request/reply server for single-frame ZMQMsg messages."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import zmq
import zmq.asyncio

from fr3d.constants.DFr3d import DFr3d as FR3D
from fr3d.constants.DModule import DModule as MODULE
from fr3d.constants.DMyLog import DMyLogDef as DEFLOG
from fr3d.utils.MyLog import MyLog
from fr3d.zmq.ZMQMsg import ZMQMsg

Response = ZMQMsg | dict[str, Any] | None
MsgHandler = Callable[[ZMQMsg], Response | Awaitable[Response]]


class ZMQServer:
    """Dispatch requests serially; handlers return a message, payload, or None."""

    def __init__(
        self,
        log_file: str | Path | None = None,
        identity: str = MODULE.ZMQ_SERVER,
        port: int = FR3D.PORT,
        srv_methods: dict[str, MsgHandler] | None = None,
        *,
        address: str = FR3D.ZMQ_HOST,
    ) -> None:
        self.log = MyLog(
            client_id=identity,
            log_level=DEFLOG.DEFAULT_LOG_LEVEL,
            log_file=str(log_file) if log_file is not None else None,
            to_console=True,
        )
        self.identity = identity
        self._port = port
        self.srv_methods = srv_methods if srv_methods is not None else {}
        self.ctx = zmq.asyncio.Context()
        self.socket = self.ctx.socket(zmq.REP)
        self.socket.setsockopt(zmq.LINGER, 0)
        try:
            if port == 0:
                self._port = self.socket.bind_to_random_port(f"tcp://{address}")
            else:
                self.socket.bind(f"tcp://{address}:{port}")
        except BaseException:
            self.socket.close(linger=0)
            self.ctx.term()
            raise
        self.endpoint = f"tcp://{address}:{self._port}"
        self.listen_task: asyncio.Task[None] | None = None
        self.listen_stop_event = asyncio.Event()
        self._closed = False
        self._receiving = False
        self._reply_pending = False

    def _check_access(self) -> None:
        if self._closed:
            raise RuntimeError("ZMQ server is closed")
        if (
            self.listen_task is not None
            and not self.listen_task.done()
            and asyncio.current_task() is not self.listen_task
        ):
            raise RuntimeError("The background listener owns the server socket")

    async def recv(self) -> ZMQMsg:
        """Receive one request; direct callers must reply before receiving again."""
        self._check_access()
        if self._receiving or self._reply_pending:
            raise RuntimeError("A request is already being received or awaiting a reply")
        self._receiving = True
        try:
            frames = await asyncio.wait_for(
                self.socket.recv_multipart(copy=True), timeout=FR3D.ZMQ_TIMEOUT
            )
        finally:
            self._receiving = False
        self._reply_pending = True
        if len(frames) != 1:
            raise ValueError("Expected a single-frame ZMQMsg request")
        return ZMQMsg.from_json(frames[0])

    async def send(self, msg: ZMQMsg) -> None:
        """Reply to the most recently received request."""
        self._check_access()
        if not self._reply_pending:
            raise RuntimeError("No request is awaiting a reply")
        await asyncio.wait_for(self.socket.send(msg.to_json()), timeout=FR3D.ZMQ_TIMEOUT)
        self._reply_pending = False

    def _error(self, code: str, message: str, request: ZMQMsg | None = None) -> ZMQMsg:
        return ZMQMsg(
            sender=self.identity,
            target=request.sender if request is not None else None,
            method=request.method if request is not None else "error",
            payload={"status": "error", "error": {"code": code, "message": message}},
        )

    async def _dispatch(self, request: ZMQMsg) -> None:
        handler = self.srv_methods.get(request.method)
        if handler is None:
            await self.send(self._error("unknown_method", "Unknown method", request))
            return
        try:
            result = handler(request)
            if inspect.isawaitable(result):
                result = await result
            if not self._reply_pending:
                return
            if result is None or isinstance(result, dict):
                result = ZMQMsg(
                    sender=self.identity,
                    target=request.sender,
                    method=request.method,
                    payload=result,
                )
            if not isinstance(result, ZMQMsg):
                raise TypeError("Handlers must return ZMQMsg, dict, or None")
            result.to_json()
        except Exception as error:
            self.log.error(f"Handler {request.method!r} failed: {error}")
            result = self._error("handler_error", "Request handler failed", request)
        if self._reply_pending:
            await self.send(result)

    async def bg_listen(self) -> None:
        """Serve until stopped; malformed requests receive an error reply."""
        try:
            while not self.listen_stop_event.is_set():
                try:
                    request = await self.recv()
                except asyncio.TimeoutError:
                    continue
                except (ValueError, TypeError, KeyError) as error:
                    self.log.warning(f"Invalid ZMQ request: {error}")
                    await self.send(self._error("invalid_request", "Invalid ZMQMsg request"))
                    continue
                await self._dispatch(request)
        finally:
            self._close()

    def start(self) -> None:
        """Start one listener task in the currently running event loop."""
        if self._closed:
            raise RuntimeError("ZMQ server is closed")
        if self.listen_task is None:
            if self._receiving or self._reply_pending:
                raise RuntimeError("Finish the manual request/reply before starting")
            loop = asyncio.get_running_loop()
            self.listen_task = loop.create_task(self.bg_listen(), name=f"{self.identity}-listen")
            self.log.info(f"Listening on {self.endpoint}")

    async def run(self) -> None:
        """Serve in the foreground, closing resources on cancellation or failure."""
        self.start()
        try:
            await self.listen_task
        finally:
            await self.stop()

    def _close(self) -> None:
        if not self._closed:
            self.listen_stop_event.set()
            self._closed = True
            self.socket.close(linger=0)
            self.ctx.term()

    async def stop(self) -> None:
        """Cancel the listener and release the bound socket; safe to repeat."""
        self.listen_stop_event.set()
        try:
            if self.listen_task is not None and self.listen_task is not asyncio.current_task():
                self.listen_task.cancel()
                try:
                    await self.listen_task
                except asyncio.CancelledError:
                    pass
        finally:
            self._close()
