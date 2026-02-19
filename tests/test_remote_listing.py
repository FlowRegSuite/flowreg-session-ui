from __future__ import annotations

import subprocess
import unittest

import bootstrap  # noqa: F401

from pyflowreg_session_gui.remote_runner import RemoteRunner
from pyflowreg_session_gui.state import RemoteProfile


class RemoteListingTests(unittest.TestCase):
    def test_list_remote_directories_parses_unique_lines(self) -> None:
        calls: list[list[str]] = []

        def fake_run(
            argv: list[str],
            *,
            check: bool,
            capture_output: bool,
            text: bool,
        ) -> subprocess.CompletedProcess[str]:
            self.assertTrue(check)
            self.assertTrue(capture_output)
            self.assertTrue(text)
            calls.append(argv)
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=(
                    "/home/test/runs\n"
                    "/home/test/runs/a\n"
                    "/home/test/runs/a\n\n"
                    "/home/test/runs/b\n"
                ),
                stderr="",
            )

        runner = RemoteRunner(run_command=fake_run)
        profile = RemoteProfile(host_alias="deigo", remote_base_dir="~/runs")

        directories = runner.list_remote_directories(profile)
        self.assertEqual(
            directories,
            ["/home/test/runs", "/home/test/runs/a", "/home/test/runs/b"],
        )
        self.assertTrue(calls)
        self.assertEqual(calls[0][0], "ssh")
        self.assertIn("find", calls[0][-1])

    def test_list_remote_directory_returns_base_and_children(self) -> None:
        calls: list[list[str]] = []

        def fake_run(
            argv: list[str],
            *,
            check: bool,
            capture_output: bool,
            text: bool,
        ) -> subprocess.CompletedProcess[str]:
            self.assertTrue(check)
            self.assertTrue(capture_output)
            self.assertTrue(text)
            calls.append(argv)
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=(
                    "__BASE__:/home/test/runs\n"
                    "/home/test/runs/z\n"
                    "/home/test/runs/a\n"
                    "/home/test/runs/a\n"
                ),
                stderr="",
            )

        runner = RemoteRunner(run_command=fake_run)
        profile = RemoteProfile(host_alias="deigo", remote_base_dir="~/runs")
        listing = runner.list_remote_directory(profile, "~/runs")

        self.assertEqual(listing.path, "/home/test/runs")
        self.assertEqual(listing.children, ["/home/test/runs/a", "/home/test/runs/z"])
        self.assertEqual(calls[0][0], "ssh")
        self.assertIn("BatchMode=yes", " ".join(calls[0]))

    def test_parse_directory_listing_raises_for_missing_base_marker(self) -> None:
        with self.assertRaises(RuntimeError):
            RemoteRunner._parse_directory_listing("/tmp/a\n/tmp/b\n")

    def test_ssh_argv_wraps_command_in_sh_lc(self) -> None:
        argv = RemoteRunner._ssh_argv("deigo", 'echo "hello"')
        self.assertEqual(argv[0], "ssh")
        self.assertEqual(argv[3], "deigo")
        self.assertIn("sh -lc", argv[4])

    def test_parse_directory_listing_ignores_warn_marker(self) -> None:
        listing = RemoteRunner._parse_directory_listing(
            "__WARN_NOT_DIR__:/bad/path\n" "__BASE__:/home/test\n" "/home/test/a\n"
        )
        self.assertEqual(listing.path, "/home/test")
        self.assertEqual(listing.children, ["/home/test/a"])
