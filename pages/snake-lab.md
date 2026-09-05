---
title: Developer Integration
author_profile: true
layout: single
---

External services submit simulations through a ZeroMQ `REQ` socket connected to
`tcp://wintermute:41970`. Messages are JSON objects using protocol version 1.

Install the Python client dependency:

```sh
pip install pyzmq
```

## Submit a Configuration

The submission payload contains the configuration object itself, not a filename:

```json
{
  "protocol_version": 1,
  "request_id": "4d76309f-7734-49cc-a1b2-ddecd9fc9664",
  "method": "simulation.submit",
  "payload": {
    "config": {
      "epochs": 100,
      "seed": 1970
    }
  }
}
```

Partial configurations are accepted. SnakeLab applies the defaults and validates
the result against the [JSON Schema](/snake_lab/schemas/simulation-config-v1.schema.json).

## Python Client Stub

```python
import asyncio
import json
import sys
import uuid
from pathlib import Path

import zmq
import zmq.asyncio


PROTOCOL_VERSION = 1
ENDPOINT = "tcp://wintermute:41970"
TIMEOUT_SECONDS = 3


class SnakeLabClient:
    def __init__(self, endpoint: str = ENDPOINT) -> None:
        self.endpoint = endpoint
        self.context = zmq.asyncio.Context()

    async def request(self, method: str, payload: dict) -> dict:
        socket = self.context.socket(zmq.REQ)
        socket.setsockopt(zmq.LINGER, 0)
        socket.connect(self.endpoint)
        request_id = str(uuid.uuid4())
        message = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "method": method,
            "payload": payload,
        }

        try:
            await asyncio.wait_for(
                socket.send_json(message), TIMEOUT_SECONDS
            )
            response = await asyncio.wait_for(
                socket.recv_json(), TIMEOUT_SECONDS
            )
        finally:
            socket.close()

        if not isinstance(response, dict):
            raise RuntimeError("invalid SnakeLab response")
        if response.get("protocol_version") != PROTOCOL_VERSION:
            raise RuntimeError("unsupported SnakeLab protocol")
        if response.get("request_id") != request_id:
            raise RuntimeError("SnakeLab request_id mismatch")
        if response.get("status") != "ok":
            error = response.get("error", {})
            code = error.get("code", "request_failed")
            message = error.get("message", "SnakeLab request failed")
            raise RuntimeError(f"{code}: {message}")
        return response["payload"]

    async def submit(self, config: dict) -> dict:
        return await self.request(
            "simulation.submit", {"config": config}
        )

    def close(self) -> None:
        self.context.term()


async def main(config_path: str) -> None:
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise TypeError("simulation config must be a JSON object")

    client = SnakeLabClient()
    try:
        result = await client.submit(config)
        print(json.dumps(result, indent=2))
    finally:
        client.close()


asyncio.run(main(sys.argv[1]))
```

Run it with:

```sh
python submit_simulation.py config.json
```

## Responses

Every response echoes `protocol_version` and `request_id`. The example client
validates that envelope and returns only `payload`.

A new submission payload contains its run identifier and queue position:

```json
{
  "run_id": "f6e72cb3-9bcf-4669-b368-a17c656bad79",
  "state": "queued",
  "queue_position": 1
}
```

Every valid submission returns `state: "queued"` and a new `run_id`, even when
the same resolved configuration has already been submitted on this project
version. Earlier runs and their results are preserved. Callers are responsible
for duplicate detection or result reuse if needed. Repeating a request,
including retrying after a timeout, submits another run.

Protocol and configuration failures use this raw response shape:

```json
{
  "protocol_version": 1,
  "request_id": "4d76309f-7734-49cc-a1b2-ddecd9fc9664",
  "status": "error",
  "error": {
    "code": "invalid_config",
    "message": "$.epochs: 10 is less than the minimum of 50"
  }
}
```

The example client converts this into a `RuntimeError`.

## Other Automation Methods

| Method | Payload |
| --- | --- |
| `health` | `{}` |
| `simulation.active` | `{}` |
| `simulation.status` | `{"run_id": "<run UUID>"}` |

Use the same `request()` method from the example for each operation.

## Live Telemetry

Live telemetry is published on `tcp://wintermute:41971`. Connect a ZeroMQ `SUB`
socket and subscribe to one or more topics:

- `snake_lab.run`
- `snake_lab.episode`
- `snake_lab.frame`

Each publication is a two-part message: the UTF-8 topic followed by a JSON
envelope containing `protocol_version`, `sequence`, `run_id`, and `payload`.
Subscribe before submitting a run when the initial lifecycle events are needed.

The project's
[control client](https://github.com/NadimGhaznavi/snake-lab/blob/main/snake_lab/control_client.py)
and
[telemetry client](https://github.com/NadimGhaznavi/snake-lab/blob/main/snake_lab/telemetry_zmq.py)
are the reference implementations.

## Simulation Events

Simulation events are published on `tcp://wintermute:41972`. The server's
`--events-port` option changes this port; `--address` selects the bind address
for all three ZeroMQ interfaces.

Connect a ZeroMQ `SUB` socket and subscribe to `snake_lab.simulation.ended`.
Each publication contains two frames: the UTF-8 topic followed by this JSON
envelope:

```json
{
  "protocol_version": 1,
  "run_id": "f6e72cb3-9bcf-4669-b368-a17c656bad79",
  "payload": {
    "state": "completed"
  }
}
```

The state is `completed`, `failed`, or `cancelled`. Failed runs also include
an `error` string inside `payload`. The server publishes the event after
storing the final run state and results. Cancellation events include queued
cancellations and runs cancelled during orderly server shutdown. A
`cancelling` state is not terminal and does not emit this event.

Messages are sent individually. Every submission has its own run identifier
and emits its own ended event when it reaches a terminal state, including
repeated configurations and new attempts after a failed or cancelled run.

Establish the subscription before submitting work. This is a live PUB/SUB
notification stream with no acknowledgement or replay. Pending events are
sent before the publisher closes during orderly shutdown.
