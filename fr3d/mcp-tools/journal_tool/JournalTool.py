"""Validate journal operations and render their results as Markdown."""

from __future__ import annotations

import asyncio
import json
import re

from fr3d.constants.DFr3d import DFr3d as FR3D
from fr3d.constants.DMethod import DMethod

from fr3d.zmq.ZMQClient import ZMQClient
from fr3d.zmq.ZMQMsg import ZMQMsg


class JournalTool:

    def __init__(self) -> None:
        self.client = ZMQClient(f"tcp://127.0.0.1:{FR3D.PORT}")

    async def add_entry(self, title: str, entry: str) -> str:
        request = ZMQMsg(
            sender="mcp-journal",
            target="journal",
            method=DMethod.ADD_JOURNAL_ENTRY,
            payload={
                "title": title,
                "entry": entry,
            },
        )

        response = await asyncio.to_thread(
            self.client.request,
            request,
        )

        return json.dumps(response.payload)

    async def view_entries(self, url: str = "/") -> str:
        response = await asyncio.to_thread(
            self.client.request,
            ZMQMsg(sender="mcp-journal", target="journal",
                   method=DMethod.VIEW_JOURNAL_ENTRIES, payload={"url": url}),
        )
        page = response.payload
        if page.get("status") != "ok":
            message = page.get("error", {}).get("message", "Unable to load journal entries")
            return f"# Journal Entries\n\n{message}\n\n- [Journal Entries](/)\n"
        if page["kind"] == "entry":
            entry = page["entry"]
            return (f"# {self._title(entry['title'])}\n\n"
                    f"Created: {entry['created_at']}\n\n{entry['entry']}\n\n"
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
