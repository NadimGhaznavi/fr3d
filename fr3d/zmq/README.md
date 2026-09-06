# ZMQClient

`ZMQClient` provides synchronous request/reply calls. It connects to an endpoint
and creates a fresh REQ socket per call, closing it with zero linger even when
a send, receive, or JSON decode fails. Send and receive each default to a
`DFr3d.ZMQ_TIMEOUT` second timeout; pass `timeout=` to override it. Timeout errors
(`zmq.Again`) propagate. The client does not automatically retry requests.

Use `request()` to exchange Fr3d `ZMQMsg` messages:

```python
from fr3d.zmq.ZMQClient import ZMQClient
from fr3d.zmq.ZMQMsg import ZMQMsg

client = ZMQClient("tcp://127.0.0.1:41972")
response = client.request(ZMQMsg("mcp", "echo", payload={"value": 42}))
print(response.payload)
```

The server must register the requested method. Application error replies remain
messages; callers inspect their payloads. `request_json(dict)` exchanges plain
JSON for protocols such as SnakeLab's, leaving protocol, request ID, status, and
payload validation to the caller. `Fr3dServer.is_simulation_running()` uses this
method and retains SnakeLab-specific validation.

By default, each call also owns and terminates its context. A supplied
`context=` must be synchronous and remains owned by the caller. For async MCP
handlers or other event-loop code, use `await asyncio.to_thread(client.request,
message)` with the default context management so the call does not block the
event loop. Cancelling that await does not interrupt the worker; the configured
socket timeouts still bound its wait.

# ZMQServer

`ZMQServer` binds an async REP socket at construction. It receives a single
JSON frame encoded by `ZMQMsg` and dispatches requests serially by `method`.
Clients use REQ sockets and alternate sending a request and receiving a reply.

```python
import asyncio

from fr3d.zmq.ZMQServer import ZMQServer


async def main():
    server = ZMQServer(
        address="127.0.0.1",
        port=41972,
        srv_methods={"echo": lambda request: request.payload},
    )
    await server.run()


asyncio.run(main())
```

Handlers may be synchronous or async. Return a `ZMQMsg` for an explicit reply,
a dictionary for a reply payload, or `None` for an empty reply payload. Generated
replies use the server identity as sender, the request sender as target, and the
original method. A handler may instead `await server.send(reply)` itself.

Unknown methods, invalid messages, and handler failures receive a `ZMQMsg` with
`payload.status = "error"` and a nested `error` containing `code` and `message`.
Invalid multipart requests are fully consumed before replying. Handler exception
details are logged locally, not sent to clients.

Use `server.start()` in a running event loop for background serving, then
`await server.stop()` in a `finally` block. Alternatively, `await server.run()`
serves until cancelled and closes resources automatically. A stopped instance
cannot be restarted. Stopping cancels any active handler; it does not drain work.
Socket failures terminate the listener rather than repeatedly retrying a broken
socket. Await `server.listen_task` when supervising a background listener.

For manual request/reply handling, use `await server.recv()` followed by
`await server.send(reply)` without starting the background listener. Even a
received malformed request needs an error reply before another receive. An idle
receive times out after `DFr3d.ZMQ_TIMEOUT`; no reply is needed after a timeout.

Each `ZMQMsg` contains `protocol_version`, `sender`, `target`, `method`, and
`payload`. The protocol version is an integer, sender and method are nonempty
strings, target is an optional string, and payload is a JSON object.

## Fr3d server integration

`Fr3dServer` owns a `ZMQServer` and delegates socket binding, message validation,
method dispatch, and replies to it. Supply the server-side handlers at construction:

```python
from fr3d.server.Fr3dServer import Fr3dServer


async def serve():
    server = Fr3dServer(srv_methods={"echo": lambda request: request.payload})
    await server.run()
```

`server.stop()` requests shutdown from the running event loop. Awaiting `run()`
ensures the listener and socket have closed; cancellation also closes them.
Transport failures propagate to the caller. Replies identify the server as `Fr3d`.

The service entry point, `python -m fr3d.server.Fr3dServer`, runs the async server
and handles SIGINT/SIGTERM. No application RPC methods are registered by default;
unregistered methods receive an `unknown_method` error. This integration does
not implement an LLM client, MCP bridge, or background LLM requests.
