from __future__ import annotations

import unittest

import bootstrap  # noqa: F401

from pyflowreg_session_gui.remote_runner import (
    generate_stage1_sbatch_script,
    generate_stage23_sbatch_script,
)
from pyflowreg_session_gui.state import RemoteProfile, SbatchDefaults


def _profile() -> RemoteProfile:
    return RemoteProfile(
        host_alias="deigo",
        remote_base_dir="~/runs",
        env_activation_cmd="source ~/.bashrc && conda activate pyflowreg",
        sbatch=SbatchDefaults(
            partition="gpu",
            time="01:00:00",
            mem="16G",
            cpus=8,
            gpus=1,
        ),
    )


class SbatchGenerationTests(unittest.TestCase):
    def test_stage1_sbatch_generation(self) -> None:
        script = generate_stage1_sbatch_script("session_config.yaml", 42, _profile())
        self.assertIn("#SBATCH --array=1-42", script)
        self.assertIn("task_index = int(os.environ['SLURM_ARRAY_TASK_ID']) - 1", script)
        self.assertIn("n_files = len(list(discover_input_files(config)))", script)
        self.assertIn("if task_index >= n_files:", script)
        self.assertIn("run_stage1(config, task_index=task_index)", script)

    def test_stage23_sbatch_generation(self) -> None:
        script = generate_stage23_sbatch_script("session_config.yaml", "12345", _profile())
        self.assertIn("#SBATCH --dependency=afterok:12345", script)
        self.assertIn("middle_idx, avg, displacements = run_stage2(config)", script)
        self.assertIn("run_stage3(config, middle_idx, displacements)", script)
