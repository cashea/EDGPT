import asyncio
import json
import sys
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))

import modules
from mcp.server.fastmcp import FastMCP


class ModuleRegistryTests(unittest.TestCase):
    def test_all_modules_load_with_unique_names(self):
        mods = modules.load_modules()
        names = [m.NAME for m in mods]
        self.assertEqual(names, list(modules.MODULE_NAMES))
        self.assertEqual(len(set(names)), len(names))

    def test_http_routes_are_unique_and_return_json(self):
        routes = modules.http_routes()
        self.assertEqual(set(routes), {"/exobio", "/cmdkeys", "/industry"})
        for path, handler in routes.items():
            payload = handler({})
            json.dumps(payload)  # must be serializable
            self.assertIn("module", payload)
        self.assertIsNone(modules.http_route("/nope"))

    def test_mcp_tools_register_with_unique_names(self):
        mcp = FastMCP("test")
        names = modules.register_mcp_tools(mcp)
        self.assertEqual(len(set(names)), len(names))
        listed = {t.name for t in asyncio.run(mcp.list_tools())}
        self.assertTrue(set(names) <= listed)

    def test_cmdkeys_never_enables_injection_by_default(self):
        self.assertFalse(modules.http_route("/cmdkeys")({})["injection_enabled"])

    def test_module_info_shape(self):
        for entry in modules.module_info():
            self.assertEqual(set(entry), {"name", "http_routes", "mcp_tools"})


if __name__ == "__main__":
    unittest.main()
