from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .message_dialogs import show_exception, show_warning
from .remote_browser_dialog import RemoteDirectoryBrowserDialog
from .remote_runner import RemoteRunner
from .state import AppState, PathMapping, RemoteProfile, SbatchDefaults


class RunRemoteTab(QWidget):
    def __init__(
        self,
        state: AppState,
        config_provider: Callable[[], Any | None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._config_provider = config_provider
        self._runner = RemoteRunner()

        self.host_edit = QLineEdit(self)
        self.remote_base_dir_edit = QLineEdit(self)
        self.list_remote_dirs_button = QPushButton("Browse...", self)
        self.env_edit = QLineEdit(self)

        self.partition_edit = QLineEdit(self)
        self.time_edit = QLineEdit(self)
        self.mem_edit = QLineEdit(self)

        self.cpus_spin = QSpinBox(self)
        self.cpus_spin.setRange(1, 256)

        self.gpus_spin = QSpinBox(self)
        self.gpus_spin.setRange(0, 32)

        remote_base_row = QHBoxLayout()
        remote_base_row.setContentsMargins(0, 0, 0, 0)
        remote_base_row.addWidget(self.remote_base_dir_edit)
        remote_base_row.addWidget(self.list_remote_dirs_button)

        remote_base_widget = QWidget(self)
        remote_base_widget.setLayout(remote_base_row)

        profile_layout = QFormLayout()
        profile_layout.addRow("SSH host alias", self.host_edit)
        profile_layout.addRow("Remote base dir", remote_base_widget)
        profile_layout.addRow("Env activation cmd", self.env_edit)
        profile_layout.addRow("Partition", self.partition_edit)
        profile_layout.addRow("Time", self.time_edit)
        profile_layout.addRow("Mem", self.mem_edit)
        profile_layout.addRow("CPUs", self.cpus_spin)
        profile_layout.addRow("GPUs", self.gpus_spin)

        self.mapping_table = QTableWidget(0, 2, self)
        self.mapping_table.setHorizontalHeaderLabels(["Local prefix", "Remote prefix"])

        add_mapping_button = QPushButton("Add Mapping", self)
        remove_mapping_button = QPushButton("Remove Mapping", self)
        add_mapping_button.clicked.connect(self._add_mapping_row)
        remove_mapping_button.clicked.connect(self._remove_selected_mapping_rows)

        mapping_buttons = QHBoxLayout()
        mapping_buttons.addWidget(add_mapping_button)
        mapping_buttons.addWidget(remove_mapping_button)

        self.test_ssh_button = QPushButton("Test SSH", self)
        self.upload_button = QPushButton("Upload Config", self)
        self.submit_button = QPushButton("Submit", self)
        self.refresh_button = QPushButton("Refresh Status", self)
        self.cancel_button = QPushButton("Cancel Job", self)

        self.test_ssh_button.clicked.connect(self._on_test_ssh)
        self.list_remote_dirs_button.clicked.connect(self._on_list_remote_dirs)
        self.upload_button.clicked.connect(self._on_upload)
        self.submit_button.clicked.connect(self._on_submit)
        self.refresh_button.clicked.connect(self._on_refresh)
        self.cancel_button.clicked.connect(self._on_cancel)

        actions = QHBoxLayout()
        actions.addWidget(self.test_ssh_button)
        actions.addWidget(self.upload_button)
        actions.addWidget(self.submit_button)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.cancel_button)

        self.cancel_job_edit = QLineEdit(self)
        self.cancel_job_edit.setPlaceholderText("Optional specific job id(s), comma-separated")

        self.status_view = QPlainTextEdit(self)
        self.status_view.setReadOnly(True)
        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addLayout(profile_layout)
        layout.addWidget(QLabel("Path Mapping"))
        layout.addWidget(self.mapping_table)
        layout.addLayout(mapping_buttons)
        layout.addLayout(actions)
        layout.addWidget(self.cancel_job_edit)
        layout.addWidget(QLabel("Status"))
        layout.addWidget(self.status_view)
        layout.addWidget(QLabel("Logs"))
        layout.addWidget(self.log_view)

        self._restore_state()

    def _restore_state(self) -> None:
        profile = self._state.remote_profile
        self.host_edit.setText(profile.host_alias)
        self.remote_base_dir_edit.setText(profile.remote_base_dir)
        self.env_edit.setText(profile.env_activation_cmd)
        self.partition_edit.setText(profile.sbatch.partition)
        self.time_edit.setText(profile.sbatch.time)
        self.mem_edit.setText(profile.sbatch.mem)
        self.cpus_spin.setValue(profile.sbatch.cpus)
        self.gpus_spin.setValue(profile.sbatch.gpus)

        for mapping in self._state.path_mappings:
            self._add_mapping_row(mapping.local_prefix, mapping.remote_prefix)

    def _collect_profile(self) -> RemoteProfile:
        return RemoteProfile(
            host_alias=self.host_edit.text().strip() or "deigo",
            remote_base_dir=self.remote_base_dir_edit.text().strip() or "~/pyflowreg_runs",
            env_activation_cmd=self.env_edit.text().strip(),
            sbatch=SbatchDefaults(
                partition=self.partition_edit.text().strip(),
                time=self.time_edit.text().strip(),
                mem=self.mem_edit.text().strip(),
                cpus=int(self.cpus_spin.value()),
                gpus=int(self.gpus_spin.value()),
            ),
        )

    def _collect_mappings(self) -> list[PathMapping]:
        mappings: list[PathMapping] = []
        for row in range(self.mapping_table.rowCount()):
            local_item = self.mapping_table.item(row, 0)
            remote_item = self.mapping_table.item(row, 1)
            local_prefix = (local_item.text() if local_item else "").strip()
            remote_prefix = (remote_item.text() if remote_item else "").strip()
            if not local_prefix or not remote_prefix:
                continue
            mappings.append(PathMapping(local_prefix=local_prefix, remote_prefix=remote_prefix))
        return mappings

    def _sync_state_profile(self) -> RemoteProfile:
        profile = self._collect_profile()
        mappings = self._collect_mappings()
        self._state.remote_profile = profile
        self._state.path_mappings = mappings
        return profile

    def _add_mapping_row(self, local_prefix: str = "", remote_prefix: str = "") -> None:
        row = self.mapping_table.rowCount()
        self.mapping_table.insertRow(row)
        self.mapping_table.setItem(row, 0, QTableWidgetItem(local_prefix))
        self.mapping_table.setItem(row, 1, QTableWidgetItem(remote_prefix))

    def _remove_selected_mapping_rows(self) -> None:
        rows = sorted({index.row() for index in self.mapping_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.mapping_table.removeRow(row)

    def _set_status(self, text: str) -> None:
        self.status_view.setPlainText(text)

    def _append_status(self, text: str) -> None:
        existing = self.status_view.toPlainText().strip()
        merged = f"{existing}\n{text}".strip() if existing else text
        self.status_view.setPlainText(merged)

    def _on_test_ssh(self) -> None:
        profile = self._sync_state_profile()
        try:
            result = self._runner.test_ssh(profile)
        except Exception as exc:
            show_exception(self, "SSH Error", exc)
            return
        self._append_status(f"SSH test succeeded: {result}")

    def _on_list_remote_dirs(self) -> None:
        profile = self._sync_state_profile()
        start_dir = profile.remote_base_dir or "~"

        try:
            dialog = RemoteDirectoryBrowserDialog(
                fetch_listing=lambda path: self._runner.list_remote_directory(profile, path),
                start_dir=start_dir,
                parent=self,
            )
        except Exception as exc:
            show_exception(self, "Remote Directory Listing Error", exc)
            return

        if dialog.exec() != QDialog.Accepted:
            return

        value = dialog.selected_path().strip()
        if not value:
            show_warning(self, "Remote Directory", "No directory selected.")
            return

        self.remote_base_dir_edit.setText(value)
        self._append_status(f"Remote base dir set to: {value}")

    def _on_upload(self) -> None:
        config = self._config_provider()
        if config is None:
            return

        profile = self._sync_state_profile()
        try:
            run_state = self._runner.prepare_and_upload(config, profile, self._state.path_mappings)
        except Exception as exc:
            show_exception(self, "Upload Error", exc)
            return

        self._state.remote_run = run_state
        self._append_status(
            "\n".join(
                [
                    f"Uploaded run: {run_state.run_name}",
                    f"Remote dir: {run_state.remote_run_dir}",
                    f"Stage1 array size: {run_state.num_tasks}",
                ]
            )
        )
        if run_state.upload_warnings:
            warning_text = "\n".join(run_state.upload_warnings)
            self._append_status(f"Warnings:\n{warning_text}")
            show_warning(self, "Upload Warning", warning_text)

    def _on_submit(self) -> None:
        profile = self._sync_state_profile()

        if not self._state.remote_run.remote_run_dir:
            self._on_upload()
            if not self._state.remote_run.remote_run_dir:
                return

        try:
            stage1_jobid, stage23_jobid = self._runner.submit(profile, self._state.remote_run)
        except Exception as exc:
            show_exception(self, "Submission Error", exc)
            return

        self._append_status(f"Submitted jobs: stage1={stage1_jobid}, stage23={stage23_jobid}")

    def _on_refresh(self) -> None:
        profile = self._sync_state_profile()
        if not self._state.remote_run.remote_run_dir:
            show_warning(self, "No Run", "Upload a run before refreshing status.")
            return

        status_chunks: list[str] = []
        if self._state.remote_run.job_ids():
            try:
                status_chunks.append(self._runner.refresh_status(profile, self._state.remote_run))
            except Exception as exc:
                status_chunks.append(f"Status query failed: {exc}")
        else:
            status_chunks.append("No submitted jobs yet.")

        try:
            logs = self._runner.tail_latest_log(profile, self._state.remote_run)
        except Exception as exc:
            logs = f"Log tail failed: {exc}"

        self._set_status("\n\n".join(status_chunks))
        self.log_view.setPlainText(logs)

    def _on_cancel(self) -> None:
        profile = self._sync_state_profile()
        explicit = self.cancel_job_edit.text().replace(",", " ").split()
        job_ids = explicit if explicit else self._state.remote_run.job_ids()
        if not job_ids:
            show_warning(self, "No Job IDs", "No job ids available to cancel.")
            return

        try:
            self._runner.cancel_jobs(profile, job_ids)
        except Exception as exc:
            show_exception(self, "Cancel Error", exc)
            return

        self._append_status(f"Requested cancel for: {', '.join(job_ids)}")
