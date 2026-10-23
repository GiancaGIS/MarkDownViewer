from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import build_setup


class BuildSetupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.root_patch = patch.object(build_setup, "ROOT", self.root)
        self.root_patch.start()
        self.console = contextlib.redirect_stdout(io.StringIO())
        self.console.__enter__()
        for relative, text in {
            "src/config.py": 'VERSION = "1.1.0"',
            "src/app.py": "",
            "MarkdownStudio.spec": "# custom build configuration",
            "installer.iss": '#define MyAppVersion "1.1.0"',
            "requirements.txt": "",
            "assets/app_icon.ico": "icon",
            "LICENSE": "MIT",
            "dist/keep.txt": "unrelated output",
            "build/keep.txt": "previous diagnostics",
            "installer/previous.exe": "previous installer",
        }.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def tearDown(self):
        self.console.__exit__(None, None, None)
        self.root_patch.stop()
        self.directory.cleanup()

    def test_missing_compiler_fails_before_install_and_preserves_outputs_with_log(self):
        with patch.object(build_setup, "find_compiler", side_effect=build_setup.BuildError("Compiler unavailable")), patch.object(build_setup.BuildLog, "run") as run, patch.object(sys, "argv", ["build_setup.py"]):
            self.assertEqual(build_setup.main(), 1)
            run.assert_not_called()
        self.assertIn("Compiler unavailable", (self.root / "build/setup.log").read_text(encoding="utf-8"))
        self.assertTrue((self.root / "installer/previous.exe").exists())
        self.assertTrue((self.root / "dist/keep.txt").exists())

    def test_success_uses_existing_spec_without_wholesale_cleanup(self):
        calls = []

        def command(arguments, env):
            calls.append(arguments)
            self.assertTrue(Path(env["PYINSTALLER_CONFIG_DIR"]).is_relative_to(self.root))
            if "PyInstaller" in arguments:
                exe = self.root / "dist/MarkdownStudio/MarkdownStudio.exe"
                exe.parent.mkdir(parents=True)
                exe.write_bytes(b"exe")
            else:
                (self.root / "installer/MarkdownStudioSetup-1.1.0.exe").write_bytes(b"setup")

        log = build_setup.BuildLog(io.StringIO())
        with patch.object(build_setup, "find_compiler", return_value=Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe")), patch.object(log, "run", side_effect=command):
            build_setup.build(log, skip_install=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][-1], str(self.root / "MarkdownStudio.spec"))
        self.assertNotIn("--collect-all", calls[0])
        self.assertEqual((self.root / "MarkdownStudio.spec").read_text(), "# custom build configuration")
        for relative in ("dist/keep.txt", "build/keep.txt", "installer/previous.exe"):
            self.assertTrue((self.root / relative).exists())

    def test_child_failure_keeps_original_output_in_log(self):
        stream = io.StringIO()
        log = build_setup.BuildLog(stream)
        with self.assertRaisesRegex(build_setup.BuildError, "codice 7"):
            log.run([sys.executable, "-c", "import sys; print('specific build failure'); sys.exit(7)"], dict(os.environ))
        self.assertIn("specific build failure", stream.getvalue())

    def test_version_mismatch_and_paths_outside_workspace_are_rejected(self):
        (self.root / "installer.iss").write_text('#define MyAppVersion "1.0.0"')
        log = build_setup.BuildLog(io.StringIO())
        with patch.object(build_setup, "find_compiler", return_value=Path("ISCC.exe")), patch.object(log, "run") as run:
            with self.assertRaisesRegex(build_setup.BuildError, "versione"):
                build_setup.build(log)
            run.assert_not_called()
        with self.assertRaises(build_setup.BuildError):
            build_setup.workspace_path("../outside")
