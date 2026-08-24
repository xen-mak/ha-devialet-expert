"""Smoke tests for Home Assistant integration module imports."""

from __future__ import annotations

import importlib
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "custom_components"))


class ImportTestCase(unittest.TestCase):
    """Verify Home Assistant can load every integration module."""

    def test_component_modules_import(self) -> None:
        """Import the integration, config flow, platform, coordinator and diagnostics."""
        for module_name in (
            "devialet_expert",
            "devialet_expert.api",
            "devialet_expert.config_flow",
            "devialet_expert.coordinator",
            "devialet_expert.diagnostics",
            "devialet_expert.media_player",
        ):
            with self.subTest(module=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))


if __name__ == "__main__":
    unittest.main()
