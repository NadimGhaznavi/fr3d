"""Request one function call from the local llama-server."""

import asyncio
import json
import os

import httpx

from fr3d.app.SnakeLabTool import LEARNING_RATE_TOOL, validate_learning_rate


async def choose_learning_rate(report: str) -> float:
    url = os.environ.get("LLAMA_URL", "http://127.0.0.1:51970").rstrip("/")
    headers = {}
    if key := os.environ.get("LLAMA_API_KEY"):
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": os.environ.get("LLAMA_MODEL", "local-model"),
        "messages": [{"role": "user", "content": report}],
        "temperature": 0.2,
        "max_tokens": 4096,
        "stream": False,
        "tools": [LEARNING_RATE_TOOL],
        "tool_choice": {"type": "function", "function": {"name": "submit_learning_rate"}},
        "parallel_tool_calls": False,
    }
    # The whole request is bounded and cancellation closes the HTTP connection.
    async with asyncio.timeout(240), httpx.AsyncClient(timeout=240) as client:
        response = await client.post(url + "/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    try:
        choice = data["choices"][0]
        calls = choice["message"]["tool_calls"]
        if choice.get("finish_reason") != "tool_calls" or len(calls) != 1:
            raise ValueError("Expected exactly one completed tool call")
        call = calls[0]
        if call["type"] != "function" or call["function"]["name"] != "submit_learning_rate":
            raise ValueError("Unexpected LLM tool call")
        arguments = json.loads(call["function"]["arguments"])
        return validate_learning_rate(arguments)
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise ValueError("LLM did not return a valid submit_learning_rate call") from error
