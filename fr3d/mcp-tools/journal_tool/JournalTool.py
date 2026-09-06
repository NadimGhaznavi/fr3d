"""Validate journal operations and render their results as Markdown."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from fr3d.constants.DFr3d import DFr3d as FR3D
from fr3d.constants.DMethod import DMethod as METHOD
from fr3d.constants.DModule import DModule as MODULE
from fr3d.constants.DMyLog import DMyLogDef as DEFLOG
from fr3d.constants.DFile import DFileDef as DEFFILE
from fr3d.constants.DDir import DDirDef as DEFDIR

from fr3d.zmq.ZMQClient import ZMQClient
from fr3d.zmq.ZMQMsg import ZMQMsg
from fr3d.utils.MyLog import MyLog


class JournalTool:

    def __init__(self) -> None:
        self.client = ZMQClient(f"tcp://127.0.0.1:{FR3D.PORT}")
        server_log = Path(DEFDIR.SERVER_LOGS / DEFFILE.LLM_SERVER_LOG)
        self.log = MyLog(client_id=MODULE.JOURNAL_TOOL, log_file=server_log, to_console=False)

    async def add_entry(self, title: str, entry: str) -> str:
        self.log.info(f"add_entry(title={title}, entry=...): processing it")
        request = ZMQMsg(
            sender="mcp-journal",
            target="journal",
            method=METHOD.ADD_JOURNAL_ENTRY,
            payload={
                "title": title,
                "entry": entry,
            },
        )

        response = await asyncio.to_thread(
            self.client.request,
            request,
        )

        self.log.info("add_entry(): Completed")

        return json.dumps(response.payload)

    async def view_entries(self, url: str = "/") -> str:
        self.log.info("view_entries(): Called")
        response = await asyncio.to_thread(
            self.client.request,
            ZMQMsg(sender="mcp-journal", target="journal",
                   method=METHOD.VIEW_JOURNAL_ENTRIES, payload={"url": url}),
        )
        page = response.payload
        if page.get("status") != "ok":
            message = page.get("error", {}).get("message", "Unable to load journal entries")
            return f"# Journal Entries\n\n{message}\n\n- [Journal Entries](/)\n"
        if page["kind"] == "entry":
            entry = page["entry"]
            return (f"# {self._title(entry['title'])}\n\n"
                    f"Created: {entry['created_at']}\n\n{entry['entry']}\n\n"
                    "    --Fr3d\n\n"
                    "- [Journal Entries](/)\n")
        lines = ["# Journal Entries", ""]
        lines.extend(f"- [{self._title(row['title'])}](/entries/{row['id']})"
                     for row in page["entries"])
        if not page["entries"]:
            lines.append("No journal entries found." if page["page"] == 1 else "No entries on this page.")
        lines.extend(["", f"Page {page['page']}", ""])
        if page["page"] > 1:
            previous = "/" if page["page"] == 2 else f"/page/{page['page'] - 1}"
            lines.append(f"- [Previous Page]({previous})")
        if page["has_next"]:
            lines.append(f"- [Next Page](/page/{page['page'] + 1})")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _title(title: str) -> str:
        # Keep user-supplied titles on one line and escape Markdown link syntax.
        title = " ".join(title.split())
        return re.sub(r"([\\`*_{}\[\]()<>#!|&])", r"\\\1", title)
