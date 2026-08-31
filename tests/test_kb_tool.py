from __future__ import annotations

import unittest
import json
from pathlib import Path

from kb_tool.browser import DOCUMENT_ROOT, load_page, resolve_url


class KnowledgeBaseBrowserTest(unittest.TestCase):
    def test_mcp_namespace_produces_kb_tool_name(self) -> None:
        config_path = Path(__file__).resolve().parent.parent / "server" / "mcp.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertIn("kb", config["mcpServers"])

    def test_root_resolves_to_fr3dnet_index(self) -> None:
        self.assertEqual(resolve_url("/"), DOCUMENT_ROOT / "index.md")

    def test_root_page_loads(self) -> None:
        self.assertIn("Fr3d Knowledge Base", load_page())

    def test_traversal_and_non_internal_urls_are_rejected(self) -> None:
        for url in ("/../README", "README", "//example", "/page?query=1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                resolve_url(url)

    def test_missing_page_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            load_page("/missing")


if __name__ == "__main__":
    unittest.main()
