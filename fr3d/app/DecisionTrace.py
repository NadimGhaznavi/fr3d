"""Correlate one decision's requests, tool results, and outcome."""

import json
import logging
import uuid


class DecisionTrace:
    def __init__(self, logger=None):
        self.log = logger if logger is not None else logging.getLogger("fr3d.app.LearningRateLLM")
        self.decision_id = uuid.uuid4().hex
        self.request_number = 0

    def next_request(self):
        self.request_number += 1
        return self.request_number

    def record(self, event, *, level="info", **fields):
        record = {"decision_id": self.decision_id, "event": event, **fields}
        getattr(self.log, level)(json.dumps(record, ensure_ascii=True))
