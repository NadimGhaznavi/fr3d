from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops_tool.ops import OpsError, get_uptime


def write_process(proc_root: Path, pid: int, name: str, ppid: int, start: int) -> None:
    process = proc_root / str(pid)
    process.mkdir()
    fields = ["S", str(ppid), *("0" for _ in range(17)), str(start)]
    (process / "stat").write_text(
        f"{pid} ({name}) {' '.join(fields)}\n",
        encoding="ascii",
    )


class OpsUptimeTest(unittest.TestCase):
    def test_os_uptime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            proc_root = Path(directory)
            (proc_root / "uptime").write_text("90061.75 0.00\n", encoding="ascii")
            result = json.loads(get_uptime("os", proc_root=proc_root))

        self.assertEqual(result, {
            "target": "os",
            "uptime_seconds": 90061,
            "uptime": "1d 1h 1m 1s",
        })

    def test_llm_server_uptime_uses_llama_server_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            proc_root = Path(directory)
            (proc_root / "uptime").write_text("1000.00 0.00\n", encoding="ascii")
            write_process(proc_root, 30, "python", 20, 90_000)
            write_process(proc_root, 20, "llama-server", 1, 75_000)
            with patch("ops_tool.ops.os.sysconf", return_value=100):
                result = json.loads(
                    get_uptime("llm-server", proc_root=proc_root, process_pid=30)
                )

        self.assertEqual(result["uptime_seconds"], 250)
        self.assertEqual(result["uptime"], "4m 10s")

    def test_unknown_target_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            get_uptime("database")

    def test_missing_llama_server_ancestor_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            proc_root = Path(directory)
            (proc_root / "uptime").write_text("1000.00 0.00\n", encoding="ascii")
            write_process(proc_root, 30, "python", 0, 90_000)
            with self.assertRaises(OpsError):
                get_uptime("llm-server", proc_root=proc_root, process_pid=30)


if __name__ == "__main__":
    unittest.main()
