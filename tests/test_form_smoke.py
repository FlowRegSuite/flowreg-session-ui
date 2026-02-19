from __future__ import annotations

import os
import unittest
from pathlib import Path
from typing import Literal

import bootstrap  # noqa: F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    from pyflowreg_session_gui.config_form import SessionConfigForm

    HAVE_PYSIDE6 = True
except Exception:
    QApplication = None  # type: ignore[assignment]
    SessionConfigForm = None  # type: ignore[assignment]
    HAVE_PYSIDE6 = False


class FakeField:
    def __init__(self, annotation, default=None, required=False):
        self.annotation = annotation
        self.default = default
        self._required = required

    def is_required(self) -> bool:
        return self._required


class FakeSessionConfig:
    model_fields = {
        "root": FakeField(Path, default="/tmp/root"),
        "output_root": FakeField(Path, default="/tmp/root/out"),
        "final_results": FakeField(Path, default="/tmp/root/results"),
        "center": FakeField(Path, default="/tmp/root/center.npy"),
        "enabled": FakeField(bool, default=True),
        "scheduler": FakeField(Literal["local", "array", "dask"], default="local"),
        "flow_backend": FakeField(Literal["flowreg", "torch", "jax"], default="flowreg"),
        "n_iters": FakeField(int, default=4),
        "alpha": FakeField(float, default=1.5),
        "mode": FakeField(Literal["fast", "accurate"], default="fast"),
        "backend_params": FakeField(dict[str, object], default={}),
        "flow_options": FakeField(dict, default={"levels": 3}),
    }

    def __init__(self, **kwargs):
        self.values = kwargs


class FormSmokeTests(unittest.TestCase):
    @unittest.skipUnless(HAVE_PYSIDE6, "PySide6 is required for GUI smoke test.")
    def test_form_generation_smoke(self) -> None:
        app = QApplication.instance() or QApplication([])
        form = SessionConfigForm(FakeSessionConfig)

        values = form.get_form_data()
        self.assertIn("root", values)
        self.assertIn("flow_options", values)
        self.assertIsInstance(values["backend_params"], dict)
        self.assertIn("scheduler", values)
        self.assertIn("flow_backend", values)
        self.assertNotIn("scheduler", form._bindings)
        self.assertNotIn("flow_backend", form._bindings)

        cfg = form.to_session_config()
        self.assertIsInstance(cfg, FakeSessionConfig)

        app.processEvents()
