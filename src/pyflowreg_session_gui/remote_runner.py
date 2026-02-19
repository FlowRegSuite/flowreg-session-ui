from __future__ import annotations

import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from .model_utils import deep_copy_model
from .serialization import serialize_config_to_yaml
from .state import PathMapping, RemoteProfile, RemoteRunState

RunCommand = Callable[..., subprocess.CompletedProcess[str]]
SSH_COMMON_ARGS = ["-o", "BatchMode=yes"]
FALLBACK_ARRAY_TASKS = 2048


@dataclass(frozen=True)
class RemoteDirectoryListing:
    path: str
    children: list[str]


def map_path(path_value: str | Path, mappings: Sequence[PathMapping]) -> str:
    raw = str(path_value)

    best_mapping: PathMapping | None = None
    best_local_prefix = ""
    for mapping in mappings:
        local_prefix = mapping.local_prefix.rstrip("/\\")
        if not local_prefix:
            continue
        if (
            raw == local_prefix
            or raw.startswith(local_prefix + "/")
            or raw.startswith(local_prefix + "\\")
        ):
            if len(local_prefix) > len(best_local_prefix):
                best_mapping = mapping
                best_local_prefix = local_prefix

    if best_mapping is None:
        return raw

    suffix = raw[len(best_local_prefix) :].lstrip("/\\")
    remote_prefix = best_mapping.remote_prefix.rstrip("/")
    if not suffix:
        return remote_prefix
    normalized_suffix = suffix.replace("\\", "/")
    return f"{remote_prefix}/{normalized_suffix}"


def _common_sbatch_lines(profile: RemoteProfile) -> list[str]:
    lines: list[str] = ["#!/bin/bash", "#SBATCH -o slurm-%j.out"]
    if profile.sbatch.partition:
        lines.append(f"#SBATCH --partition={profile.sbatch.partition}")
    if profile.sbatch.time:
        lines.append(f"#SBATCH --time={profile.sbatch.time}")
    if profile.sbatch.mem:
        lines.append(f"#SBATCH --mem={profile.sbatch.mem}")
    if profile.sbatch.cpus:
        lines.append(f"#SBATCH --cpus-per-task={int(profile.sbatch.cpus)}")
    if profile.sbatch.gpus:
        lines.append(f"#SBATCH --gres=gpu:{int(profile.sbatch.gpus)}")
    return lines


def generate_stage1_sbatch_script(
    config_filename: str,
    num_tasks: int,
    profile: RemoteProfile,
) -> str:
    header = _common_sbatch_lines(profile)
    header.append(f"#SBATCH --array=1-{num_tasks}")
    body = [
        "",
        "set -euo pipefail",
    ]
    if profile.env_activation_cmd:
        body.append(profile.env_activation_cmd)
    body.extend(
        [
            "python - <<'PY'",
            "import os",
            "from pyflowreg.session.config import SessionConfig",
            "from pyflowreg.session.stage1_compensate import discover_input_files, run_stage1",
            f"config = SessionConfig.from_file('{config_filename}')",
            "task_index = int(os.environ['SLURM_ARRAY_TASK_ID']) - 1",
            "n_files = len(list(discover_input_files(config)))",
            "if task_index >= n_files:",
            "    print(f'Skipping task {task_index}: only {n_files} files discovered.')",
            "else:",
            "    run_stage1(config, task_index=task_index)",
            "PY",
            "",
        ]
    )
    return "\n".join(header + body)


def generate_stage23_sbatch_script(
    config_filename: str,
    stage1_jobid: str,
    profile: RemoteProfile,
) -> str:
    header = _common_sbatch_lines(profile)
    header.append(f"#SBATCH --dependency=afterok:{stage1_jobid}")

    body = [
        "",
        "set -euo pipefail",
    ]
    if profile.env_activation_cmd:
        body.append(profile.env_activation_cmd)
    body.extend(
        [
            "python - <<'PY'",
            "from pyflowreg.session.config import SessionConfig",
            "from pyflowreg.session.stage2_between_avgs import run_stage2",
            "from pyflowreg.session.stage3_valid_mask import run_stage3",
            f"config = SessionConfig.from_file('{config_filename}')",
            "middle_idx, avg, displacements = run_stage2(config)",
            "del avg",
            "run_stage3(config, middle_idx, displacements)",
            "PY",
            "",
        ]
    )
    return "\n".join(header + body)


class RemoteRunner:
    def __init__(self, run_command: RunCommand | None = None) -> None:
        self._run_command = run_command or subprocess.run

    def _run(self, argv: Sequence[str]) -> str:
        try:
            completed = self._run_command(
                list(argv),
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            error_output = (exc.stderr or exc.stdout or "").strip()
            command = " ".join(argv)
            if argv and argv[0] == "ssh" and exc.returncode == 255:
                host_alias = self._extract_ssh_host(argv)
                ssh_hint_lines = [
                    "SSH interactive prompts are disabled in the GUI (BatchMode=yes).",
                    "",
                    "Run one of these once in a terminal, then retry from the GUI:",
                    (
                        "1) Accept key + test login: "
                        f"ssh -o StrictHostKeyChecking=accept-new {host_alias} "
                        '"echo connected"'
                    ),
                ]
                if "Host key verification failed" in error_output:
                    ssh_hint_lines.extend(
                        [
                            f"2) If key changed, clear stale key: ssh-keygen -R {host_alias}",
                            (
                                "3) Retry login test: "
                                f"ssh -o StrictHostKeyChecking=accept-new {host_alias} "
                                '"echo connected"'
                            ),
                        ]
                    )
                ssh_hint = "\n".join(ssh_hint_lines)
                combined = "\n".join(part for part in [error_output, ssh_hint] if part).strip()
                raise RuntimeError(f"Command failed: {command}\n{combined}") from exc

            raise RuntimeError(f"Command failed: {command}\n{error_output}") from exc
        return (completed.stdout or "").strip()

    @staticmethod
    def _ssh_argv(host_alias: str, remote_command: str) -> list[str]:
        wrapped = f"sh -lc {shlex.quote(remote_command)}"
        return ["ssh", *SSH_COMMON_ARGS, host_alias, wrapped]

    @staticmethod
    def _extract_ssh_host(argv: Sequence[str]) -> str:
        # For our generated argv this is the second-to-last token:
        # ssh [opts...] <host> <remote_command>
        if len(argv) >= 3 and not str(argv[-2]).startswith("-"):
            return str(argv[-2])
        return str(argv[1]) if len(argv) > 1 else "<host>"

    def test_ssh(self, profile: RemoteProfile) -> str:
        return self._run(self._ssh_argv(profile.host_alias, "echo connected"))

    def list_remote_directory(
        self,
        profile: RemoteProfile,
        directory: str,
    ) -> RemoteDirectoryListing:
        requested_dir = directory.strip() or "~"
        command = (
            f"requested={shlex.quote(requested_dir)}; "
            'case "$requested" in '
            '"~") requested="$HOME" ;; "~/"*) requested="$HOME/${requested#??}" ;; '
            "esac; "
            'if [ ! -d "$requested" ]; then '
            'echo "__WARN_NOT_DIR__:$requested"; '
            'requested="$HOME"; '
            "fi; "
            'printf "__BASE__:%s\\n" "$requested"; '
            'find "$requested" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort'
        )
        output = self._run(self._ssh_argv(profile.host_alias, command))
        return self._parse_directory_listing(output)

    def list_remote_directories(
        self,
        profile: RemoteProfile,
        start_dir: str | None = None,
        *,
        max_depth: int = 2,
        limit: int = 200,
    ) -> list[str]:
        requested_dir = (start_dir or profile.remote_base_dir or "~").strip() or "~"
        safe_depth = max(1, int(max_depth))
        safe_limit = max(1, int(limit))

        command = (
            f"base={shlex.quote(requested_dir)}; "
            'case "$base" in "~") base="$HOME" ;; "~/"*) base="$HOME/${base#??}" ;; esac; '
            'mkdir -p "$base" >/dev/null 2>&1 || true; '
            'printf "%s\\n" "$base"; '
            f'find "$base" -mindepth 1 -maxdepth {safe_depth} -type d 2>/dev/null '
            f"| sort | head -n {safe_limit}"
        )

        output = self._run(self._ssh_argv(profile.host_alias, command))
        directories: list[str] = []
        seen: set[str] = set()
        for line in output.splitlines():
            value = line.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            directories.append(value)
        return directories

    @staticmethod
    def _parse_directory_listing(output: str) -> RemoteDirectoryListing:
        base_path = ""
        children: list[str] = []
        for line in output.splitlines():
            text = line.strip()
            if not text:
                continue
            if text.startswith("__BASE__:"):
                base_path = text.split(":", 1)[1]
                continue
            if text.startswith("__WARN_NOT_DIR__:"):
                continue
            children.append(text)

        if not base_path:
            raise RuntimeError(f"Could not parse remote directory listing output:\n{output}")

        deduped_children = sorted(set(children))
        return RemoteDirectoryListing(path=base_path, children=deduped_children)

    def map_config_paths(self, config: Any, mappings: Sequence[PathMapping]) -> Any:
        mapped = deep_copy_model(config)
        for field_name in ("root", "output_root", "final_results", "center"):
            if not hasattr(mapped, field_name):
                continue
            value = getattr(mapped, field_name)
            if value is None or value == "":
                continue
            translated = map_path(value, mappings)
            if isinstance(value, Path):
                setattr(mapped, field_name, Path(translated))
            else:
                setattr(mapped, field_name, translated)

        flow_options = getattr(mapped, "flow_options", None)
        if isinstance(flow_options, (str, Path)):
            translated = map_path(flow_options, mappings)
            if isinstance(flow_options, Path):
                setattr(mapped, "flow_options", Path(translated))
            else:
                setattr(mapped, "flow_options", translated)

        return mapped

    def prepare_and_upload(
        self,
        config: Any,
        profile: RemoteProfile,
        mappings: Sequence[PathMapping],
    ) -> RemoteRunState:
        from .pyflowreg_api import discover_input_files_for_config

        run_name = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        remote_run_dir = f"{profile.remote_base_dir.rstrip('/')}/{run_name}"

        upload_warnings: list[str] = []
        num_tasks = 0

        try:
            num_tasks = len(discover_input_files_for_config(config))
        except Exception as exc:
            upload_warnings.append(f"Local input discovery failed: {exc}")

        if num_tasks < 1:
            if not upload_warnings:
                upload_warnings.append("Local input discovery found 0 files.")
            num_tasks = FALLBACK_ARRAY_TASKS
            upload_warnings.append(
                "Using fallback Stage1 array size "
                f"{FALLBACK_ARRAY_TASKS}. "
                "Tasks beyond discovered files will auto-skip on the cluster."
            )

        local_bundle_dir = Path(tempfile.mkdtemp(prefix="pyflowreg_session_gui_"))
        config_filename = "session_config.yaml"

        mapped_config = self.map_config_paths(config, mappings)
        serialize_config_to_yaml(
            mapped_config, local_bundle_dir / config_filename, prefer_relative=False
        )

        stage1_script = generate_stage1_sbatch_script(config_filename, num_tasks, profile)
        (local_bundle_dir / "stage1_array.sbatch").write_text(stage1_script, encoding="utf-8")

        quoted_remote_dir = shlex.quote(remote_run_dir)
        self._run(self._ssh_argv(profile.host_alias, f"mkdir -p {quoted_remote_dir}"))
        self._run(
            [
                "rsync",
                "-az",
                f"{local_bundle_dir}/",
                f"{profile.host_alias}:{remote_run_dir}/",
            ]
        )

        return RemoteRunState(
            run_name=run_name,
            remote_run_dir=remote_run_dir,
            local_bundle_dir=local_bundle_dir,
            config_filename=config_filename,
            num_tasks=num_tasks,
            upload_warnings=upload_warnings,
        )

    def submit(self, profile: RemoteProfile, run_state: RemoteRunState) -> tuple[str, str]:
        if not run_state.remote_run_dir:
            raise RuntimeError("No remote run directory available. Upload first.")

        quoted_remote_dir = shlex.quote(run_state.remote_run_dir)
        stage1_submit = self._run(
            self._ssh_argv(
                profile.host_alias,
                f"cd {quoted_remote_dir} && sbatch stage1_array.sbatch",
            )
        )
        stage1_jobid = self._parse_job_id(stage1_submit)

        if run_state.local_bundle_dir is None:
            raise RuntimeError("Local bundle directory is missing.")

        stage23_script = generate_stage23_sbatch_script(
            run_state.config_filename,
            stage1_jobid,
            profile,
        )
        stage23_path = run_state.local_bundle_dir / "stage23.sbatch"
        stage23_path.write_text(stage23_script, encoding="utf-8")

        self._run(
            [
                "rsync",
                "-az",
                str(stage23_path),
                f"{profile.host_alias}:{run_state.remote_run_dir}/stage23.sbatch",
            ]
        )

        stage23_submit = self._run(
            self._ssh_argv(
                profile.host_alias,
                (
                    f"cd {quoted_remote_dir} && "
                    f"sbatch --dependency=afterok:{stage1_jobid} stage23.sbatch"
                ),
            )
        )
        stage23_jobid = self._parse_job_id(stage23_submit)

        run_state.stage1_job_id = stage1_jobid
        run_state.stage23_job_id = stage23_jobid
        return stage1_jobid, stage23_jobid

    def refresh_status(self, profile: RemoteProfile, run_state: RemoteRunState) -> str:
        job_ids = run_state.job_ids()
        if not job_ids:
            raise RuntimeError("No submitted jobs to query.")

        joined_job_ids = ",".join(job_ids)
        squeue_output = self._run(
            self._ssh_argv(
                profile.host_alias,
                f"squeue -j {joined_job_ids} -o '%i %T %M %R'",
            )
        )

        sacct_output = ""
        try:
            sacct_output = self._run(
                self._ssh_argv(
                    profile.host_alias,
                    f"sacct -j {joined_job_ids} --format=JobID,State,Elapsed,MaxRSS --noheader",
                )
            )
        except RuntimeError:
            sacct_output = "(sacct unavailable)"

        return (
            "squeue:\n"
            f"{squeue_output or '(no rows)'}\n\n"
            "sacct:\n"
            f"{sacct_output or '(no rows)'}"
        )

    def tail_latest_log(
        self, profile: RemoteProfile, run_state: RemoteRunState, lines: int = 200
    ) -> str:
        if not run_state.remote_run_dir:
            raise RuntimeError("No remote run directory available.")

        quoted_remote_dir = shlex.quote(run_state.remote_run_dir)
        command = (
            f"cd {quoted_remote_dir} && "
            "latest=$(ls -1t slurm*.out 2>/dev/null | head -n 1); "
            f'if [ -n "$latest" ]; then tail -n {int(lines)} "$latest"; '
            "else echo 'No slurm logs found.'; fi"
        )
        return self._run(self._ssh_argv(profile.host_alias, command))

    def cancel_jobs(self, profile: RemoteProfile, job_ids: Sequence[str]) -> None:
        filtered_job_ids = [job_id for job_id in job_ids if job_id]
        if not filtered_job_ids:
            return
        self._run(self._ssh_argv(profile.host_alias, f"scancel {' '.join(filtered_job_ids)}"))

    @staticmethod
    def _parse_job_id(output: str) -> str:
        match = re.search(r"Submitted batch job (\d+)", output)
        if not match:
            raise RuntimeError(f"Could not parse sbatch output: {output}")
        return match.group(1)
