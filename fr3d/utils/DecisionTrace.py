"""Separate skimmable decision activity from prompt and model-response details."""

import json
import logging
import uuid


class DecisionTrace:
    def __init__(self, logger=None, *, prompt_logger=None, reasoning_logger=None):
        self.log = logger if logger is not None else logging.getLogger("fr3d.learning_rate")
        self.prompt_log = prompt_logger if prompt_logger is not None else logging.getLogger("Fr3dPrompts")
        self.reasoning_log = reasoning_logger if reasoning_logger is not None else logging.getLogger("Fr3dReasoning")
        self.decision_id = uuid.uuid4().hex[:3]
        self.request_number = 0
        self.current_task = "Learning-rate selection"

    def next_request(self):
        self.request_number += 1
        return self.request_number

    @staticmethod
    def _short(value):
        return " ".join(str(value).split())[:200]

    def record(self, event, *, level="info", **fields):
        record = {"decision_id": self.decision_id, "event": event, **fields}
        summary = {k: v for k, v in fields.items() if k not in ("payload", "body", "result", "arguments")}
        if event == "prompt_started":
            self.current_task = self._short(fields.get("task", "Learning-rate selection"))
            self.reasoning_log.info(
                f"decision={self.decision_id} prompt={fields.get('prompt', '?')}\n"
                f"Task: {self.current_task}"
            )
        elif event == "llm_request":
            self.prompt_log.info(json.dumps(record, ensure_ascii=True))
            try:
                content = next(m["content"] for m in fields["payload"]["messages"] if m["role"] == "user")
                report = json.loads(content)
                report = report.get("report", report)
                summary["runs"] = ",".join(str(r["run_id"]) for r in report.get("runs", []))
            except (ValueError, TypeError, KeyError, StopIteration, AttributeError):
                pass
        elif event == "llm_response":
            reasoning_blocks = []
            response_blocks = []
            try:
                response = json.loads(fields["body"])
                if isinstance(response, dict) and response.get("error"):
                    error = response["error"]
                    message = error.get("message", "Unspecified server error") if isinstance(error, dict) else error
                    # A short error belongs in the readable log, not its full envelope.
                    response_blocks.append(
                        f"Server error (HTTP {fields.get('http_status', '?')}): "
                        + " ".join(str(message).split())[:500]
                    )
                messages = [c.get("message", {}) for c in response.get("choices", [])]
                reasoning = [m.get("reasoning_content") or m.get("reasoning") for m in messages]
                record["reasoning_status"] = "returned" if any(reasoning) else "No separate reasoning returned"
                for index, message in enumerate(messages):
                    for key in ("reasoning_content", "reasoning"):
                        if isinstance(message.get(key), str) and message[key]:
                            heading = "Reasoning:" if len(messages) == 1 else f"Reasoning (choice {index + 1}):"
                            reasoning_blocks.append(f"{heading}\n{message.pop(key)}")
                    answer = []
                    if isinstance(message.get("content"), str) and message["content"]:
                        answer.append(message["content"])
                    for call in message.get("tool_calls") or []:
                        if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
                            continue
                        function = call["function"]
                        answer.append(f"Tool: {function.get('name', 'unknown')}\n"
                                      f"Arguments: {function.get('arguments', '{}')}")
                    if answer:
                        heading = "Response:" if len(messages) == 1 else f"Response (choice {index + 1}):"
                        response_blocks.append("\n".join([heading, *answer]))
                record["response"] = response
                del record["body"]
            except (ValueError, TypeError, AttributeError):
                record["reasoning_status"] = "No separate reasoning returned; response is not valid chat JSON"
            if not response_blocks and fields.get("http_status", 200) >= 400:
                response_blocks.append(
                    f"Server error (HTTP {fields['http_status']}); see llm-server.log for the response body."
                )
            # Keep the full response envelope with the interactions; show the
            # actual answer and tool selections as readable text in the human log.
            self.prompt_log.info(json.dumps(record, ensure_ascii=True))
            self.reasoning_log.info("\n".join([
                f"decision={self.decision_id} request={fields.get('request_number', self.request_number)}",
                f"Task: {self.current_task}",
                *(reasoning_blocks or ["No separate reasoning returned."]),
                *(response_blocks or ["No response content returned."]),
            ]))
        elif event in ("lookup_result", "submission_result"):
            self.prompt_log.info(json.dumps(record, ensure_ascii=True))
            result = fields.get("result", {})
            summary.update({k: result[k] for k in ("status", "learning_rate", "run_id") if k in result})
            report = result.get("report", {})
            if isinstance(report, dict) and "top_10" in report:
                summary.update(top=len(report["top_10"]), bottom=len(report.get("bottom_10", [])))
        elif event == "llm_tool_call":
            arguments = fields.get("arguments", {})
            if isinstance(arguments, dict) and "learning_rate" in arguments:
                summary["learning_rate"] = arguments["learning_rate"]
        prefix = f"decision={self.decision_id}"
        details = " ".join(f"{key}={self._short(value)}" for key, value in summary.items())
        getattr(self.log, level)(f"{prefix} {event} {details}".rstrip())
