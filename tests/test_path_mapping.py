from __future__ import annotations

import unittest

import bootstrap  # noqa: F401

from pyflowreg_session_gui.remote_runner import map_path
from pyflowreg_session_gui.state import PathMapping


class PathMappingTests(unittest.TestCase):
    def test_map_path_uses_longest_matching_prefix(self) -> None:
        mappings = [
            PathMapping(local_prefix="/data", remote_prefix="/remote/data"),
            PathMapping(local_prefix="/data/project", remote_prefix="/remote/project"),
        ]

        mapped = map_path("/data/project/session/input.tif", mappings)
        self.assertEqual(mapped, "/remote/project/session/input.tif")

    def test_map_path_returns_original_when_no_mapping_matches(self) -> None:
        mappings = [PathMapping(local_prefix="/data", remote_prefix="/remote/data")]
        original = "/other/location/file.tif"

        self.assertEqual(map_path(original, mappings), original)
