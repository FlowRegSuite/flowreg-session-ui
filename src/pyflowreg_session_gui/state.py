from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PathMapping:
    local_prefix: str
    remote_prefix: str


@dataclass
class SbatchDefaults:
    partition: str = ""
    time: str = ""
    mem: str = ""
    cpus: int = 1
    gpus: int = 0


@dataclass
class RemoteProfile:
    host_alias: str = "deigo"
    remote_base_dir: str = "~/pyflowreg_runs"
    env_activation_cmd: str = ""
    sbatch: SbatchDefaults = field(default_factory=SbatchDefaults)


@dataclass
class RemoteRunState:
    run_name: str | None = None
    remote_run_dir: str | None = None
    local_bundle_dir: Path | None = None
    config_filename: str = "session_config.yaml"
    num_tasks: int = 0
    stage1_job_id: str | None = None
    stage23_job_id: str | None = None
    upload_warnings: list[str] = field(default_factory=list)

    def job_ids(self) -> list[str]:
        ids: list[str] = []
        if self.stage1_job_id:
            ids.append(self.stage1_job_id)
        if self.stage23_job_id:
            ids.append(self.stage23_job_id)
        return ids


@dataclass
class AppState:
    config: Any | None = None
    config_path: Path | None = None
    remote_profile: RemoteProfile = field(default_factory=RemoteProfile)
    path_mappings: list[PathMapping] = field(default_factory=list)
    remote_run: RemoteRunState = field(default_factory=RemoteRunState)
