"""Resume release initialization from persisted SnakeLab run history."""

import json
from collections import Counter
from copy import deepcopy

from fr3d.app_legacy.LearningRateReport import LearningRateReport


def release_replays(version, *, connection_factory=LearningRateReport.connect_snake_lab):
    """Return old configurations still missing from the new release queue.

    The first run on this version fixes the history boundary across restarts.
    Completed identical runs count individually, including repeated configurations.
    """
    connection = connection_factory()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, project_version, status, config FROM simulation_runs ORDER BY id"
            )
            rows = cursor.fetchall()
    finally:
        connection.close()
    completed = [row for row in rows if row["status"] == "completed"]
    if len(completed) >= 3 and all(
        row["project_version"] == version for row in completed[-3:]
    ):
        return []
    current = [row for row in rows if row["project_version"] == version]
    boundary = current[0]["id"] if current else float("inf")
    sources = [row for row in completed if row["id"] < boundary][-3:]
    if len(sources) != 3:
        raise ValueError("Release initialization requires three preceding completed Snake Lab runs")
    configs = [json.loads(row["config"]) for row in sources]
    fixed_configs = []
    for config in configs:
        fixed = deepcopy(config)
        if type(fixed.get("seed")) is not int:
            raise ValueError("Release initialization requires a fixed integer seed")
        del fixed["training"]["learning_rate"]
        fixed_configs.append(fixed)
    if any(fixed != fixed_configs[0] for fixed in fixed_configs[1:]):
        raise ValueError("Release initialization source runs differ in parameters other than learning_rate")

    def key(config):
        return json.dumps(config, sort_keys=True, separators=(",", ":"), allow_nan=False)

    available = Counter(
        key(json.loads(row["config"])) for row in current if row["status"] in {"completed", "queued", "running", "paused", "cancelling"}
    )
    missing = []
    for config in configs:
        identity = key(config)
        if available[identity]:
            available[identity] -= 1
        else:
            missing.append(config)
    return missing
