from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import bootstrap  # noqa: F401
import yaml

from pyflowreg_session_gui.config_io import load_config_from_file, save_config_to_yaml


class FakeSessionConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def model_dump(self, mode: str = "python"):
        del mode
        return dict(self.__dict__)

    @classmethod
    def from_file(cls, path: str):
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(**data)


class ConfigIoRoundtripTests(unittest.TestCase):
    def test_yaml_roundtrip_with_relative_paths(self) -> None:
        root = Path.cwd() / "tmp_dataset_root"
        cfg = FakeSessionConfig(
            root=str(root),
            output_root=str(root / "output"),
            final_results=str(root / "final"),
            center=str(root / "center.npy"),
            flow_options=str(root / "flow_options.json"),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_path = Path(tmp_dir) / "session_config.yaml"
            save_config_to_yaml(cfg, yaml_path, prefer_relative=True)

            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            self.assertEqual(raw["output_root"], "output")
            self.assertEqual(raw["final_results"], "final")
            self.assertEqual(raw["center"], "center.npy")
            self.assertEqual(raw["flow_options"], "flow_options.json")

            loaded = load_config_from_file(yaml_path, session_config_cls=FakeSessionConfig)
            self.assertEqual(loaded.output_root, "output")
            self.assertEqual(loaded.final_results, "final")
