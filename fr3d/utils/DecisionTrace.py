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

    def next_request(self):
        self.request_number += 1
        return self.request_number

    @staticmethod
    def _short(value):
        return " ".join(str(value).split())[:200]

    def record(self, event, *, level="info", **fields):
        record = {"decision_id": self.decision_id, "event": event, **fields}
        summary = {k: v for k, v in fields.items() if k not in ("payload", "body", "result", "arguments")}
        if event == "llm_request":
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
            try:
                response = json.loads(fields["body"])
                messages = [c.get("message", {}) for c in response.get("choices", [])]
                reasoning = [m.get("reasoning_content") or m.get("reasoning") for m in messages]
                record["reasoning_status"] = "returned" if any(reasoning) else "No separate reasoning returned"
                for index, message in enumerate(messages):
                    for key in ("reasoning_content", "reasoning"):
                        if isinstance(message.get(key), str) and message[key]:
                            reasoning_blocks.append(f"choice={index} {key}:\n{message.pop(key)}")
                record["response"] = response
                del record["body"]
            except (ValueError, TypeError, AttributeError):
                record["reasoning_status"] = "No separate reasoning returned; response is not valid chat JSON"
            self.reasoning_log.info("\n".join([json.dumps(record, ensure_ascii=True), *reasoning_blocks]))
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
