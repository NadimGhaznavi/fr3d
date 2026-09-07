"""Choose a learning rate with an optional read-only historical report lookup."""

import asyncio
import json
import os
import logging
import time

import httpx

from fr3d.app_legacy.SnakeLabTool import LEARNING_RATE_TOOL, BEST_WORST_TOOL, validate_learning_rate
from fr3d.app_legacy.BestWorstReport import generate_best_worst_report
from fr3d.app_legacy.DecisionTrace import DecisionTrace


async def choose_learning_rate(report: str, *, trace: DecisionTrace | None = None) -> float:
    trace = trace if trace is not None else DecisionTrace()
    url = os.environ.get("LLAMA_URL", "http://127.0.0.1:51970").rstrip("/")
    headers = {}
    if key := os.environ.get("LLAMA_API_KEY"):
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": os.environ.get("LLAMA_MODEL", "local-model"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an ML experiment analyst for the Snake Lab system. "
                    "Analyze the experiment report and choose the next learning rate."
                ),
            },
            {
                "role": "user",
                "content": report,
            },
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
        "stream": False,
        "tools": [LEARNING_RATE_TOOL, BEST_WORST_TOOL],
        # This llama-server expects a string; one function call is required.
        "tool_choice": "required",
        "parallel_tool_calls": False,
    }
    # The whole request is bounded and cancellation closes the HTTP connection.
    async with asyncio.timeout(240), httpx.AsyncClient(timeout=240) as client:
        for turn in range(2):
            request_number = trace.next_request()
            trace.record("llm_request", request_number=request_number, payload=payload)
            started = time.monotonic()
            try:
                response = await client.post(url + "/v1/chat/completions", json=payload, headers=headers)
            except BaseException as error:
                trace.record("llm_request_interrupted", level="warning", request_number=request_number,
                             elapsed_s=round(time.monotonic() - started, 3), error_type=type(error).__name__)
                raise
            trace.record("llm_response", request_number=request_number,
                         elapsed_s=round(time.monotonic() - started, 3),
                         http_status=response.status_code, body=response.text)
            response.raise_for_status()
            try:
                choice = response.json()["choices"][0]
                calls = choice["message"]["tool_calls"]
                if choice.get("finish_reason") != "tool_calls" or len(calls) != 1:
                    raise ValueError("Expected exactly one completed tool call")
                call = calls[0]
                if call["type"] != "function":
                    raise ValueError("Unexpected LLM tool call")
                name = call["function"]["name"]
                arguments = json.loads(call["function"]["arguments"])
                trace.record("llm_tool_call", request_number=request_number,
                             finish_reason=choice.get("finish_reason"), tool=name, arguments=arguments)
                if name == "submit_learning_rate":
                    rate = validate_learning_rate(arguments)
                    trace.record("learning_rate_proposed", request_number=request_number, learning_rate=rate)
                    return rate
                if name != "view_best_worst_report" or turn != 0 or arguments != {}:
                    raise ValueError("Unexpected or repeated report tool call")
                call_id = call["id"]
                if not isinstance(call_id, str) or not call_id:
                    raise ValueError("Report tool call requires an ID")
            except (KeyError, IndexError, TypeError, AttributeError) as error:
                raise ValueError("LLM did not return a valid tool call") from error
            trace.record("lookup_started", request_number=request_number, tool=name, tool_call_id=call_id)
            try:
                ranking = await asyncio.to_thread(generate_best_worst_report)
                result = {"status": "ok", "report": ranking}
            except Exception as error:
                trace.record("lookup_failed", level="error", request_number=request_number,
                             tool_call_id=call_id, error_type=type(error).__name__, message=str(error))
                result = {"status": "error", "error": "Historical report unavailable. Choose using the comparison report already provided."}
            trace.record("lookup_result", request_number=request_number, tool=name,
                         tool_call_id=call_id, result=result)
            payload["messages"].extend([
                {**choice["message"], "role": "assistant"},
                {"role": "tool", "tool_call_id": call_id, "content": json.dumps(result)},
            ])
            payload["tools"] = [LEARNING_RATE_TOOL]
    raise ValueError("LLM did not submit a learning rate")
