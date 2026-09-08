"""Exercise launcher processes without creating real environments or installing packages."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")

# Each fake interpreter runs the launcher's real validation snippets. Only venv,
# pip and the GUI entry point are simulated; no package manager or GUI is run.
FAKE_PYTHON = r'''
import collections
import json
import os
from pathlib import Path
import shutil
import sys

executable = Path(sys.argv[0]).absolute()
arguments = sys.argv[1:]
while arguments and arguments[0].startswith("-3"):
    arguments = arguments[1:]
in_venv = ".venv" in executable.parts
action = "check"
if arguments[:2] == ["-m", "venv"]:
    action = "venv"
elif arguments[:2] == ["-m", "ensurepip"]:
    action = "ensurepip"
elif arguments[:2] == ["-m", "pip"]:
    action = "install" if "install" in arguments else "pip_check"
elif arguments and arguments[0].endswith("main.py"):
    action = "app"
event = {
    "action": action,
    "executable": str(executable),
    "arguments": arguments,
    "cwd": os.getcwd(),
    "environment": {key: os.environ.get(key) for key in (
        "MPLCONFIGDIR", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS",
        "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
    )},
}
with open(os.environ["SIM_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(event) + "\n")

if action == "venv":
    if os.environ.get("SIM_VENV_FAIL"):
        sys.exit(21)
    destination = Path(arguments[-1])
    for relative in ("bin/python", "Scripts/python.exe"):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(executable, target)
        target.chmod(0o755)
    sys.exit(0)
if action == "pip_check":
    missing = os.environ.get("SIM_PIP_MISSING")
    restored = Path(os.environ["SIM_PIP_MARKER"]).exists()
    sys.exit(1 if missing and not restored else 0)
if action == "ensurepip":
    if os.environ.get("SIM_ENSUREPIP_FAIL"):
        sys.exit(22)
    Path(os.environ["SIM_PIP_MARKER"]).touch()
    sys.exit(0)
if action == "install":
    sys.exit(23 if os.environ.get("SIM_INSTALL_FAIL") else 0)
if action == "app":
    sys.exit(int(os.environ.get("SIM_APP_EXIT", "0")))
if arguments and arguments[0] == "-c":
    version = os.environ.get("SIM_VENV_VERSION" if in_venv else "SIM_HOST_VERSION", "3.12.4")
    major, minor, micro = (int(part) for part in version.split("."))
    Version = collections.namedtuple("version_info", "major minor micro releaselevel serial")
    sys.version_info = Version(major, minor, micro, "final", 0)
    sys.executable = str(executable)
    sys.base_prefix = str(Path(os.environ["SIM_ROOT"]) / "host-python")
    sys.prefix = str(executable.parent.parent) if in_venv else sys.base_prefix
    if os.environ.get("SIM_BAD_PREFIX"):
        sys.prefix = sys.base_prefix
    sys.argv = ["-c", *arguments[2:]]
    exec(arguments[1], {"__name__": "__main__"})
    sys.exit(0)
raise SystemExit("Unexpected simulated Python invocation: " + repr(arguments))
'''


@unittest.skipUnless(BASH and os.name == "posix", "Bash launcher tests require a POSIX shell")
class BashLauncherTests(unittest.TestCase):
    launcher_name = "launch_desp_desktop_app.sh"

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="desp launcher tests ")
        self.addCleanup(self.temporary_directory.cleanup)
        self.sandbox = Path(self.temporary_directory.name)
        self.project = self.sandbox / "project with spaces"
        self.project.mkdir()
        self.launcher = self.project / self.launcher_name
        shutil.copyfile(PROJECT_ROOT / self.launcher_name, self.launcher)
        self.app = self.project / "desp_desktop_app" / "main.py"
        self.app.parent.mkdir()
        self.app.write_text("raise AssertionError('The GUI must not run in launcher tests')\n")
        self.requirements = self.app.with_name("requirements.txt")
        self.requirements.write_text("example-package==1.0\n")
        self.bin_directory = self.sandbox / "fake commands"
        self.bin_directory.mkdir()
        self.fake_python = self.bin_directory / "python3.12"
        self.fake_python.write_text(f"#!{sys.executable}\n" + FAKE_PYTHON)
        self.fake_python.chmod(0o755)
        for name in ("python3", "python", "py", "python.exe", "py.exe"):
            shutil.copyfile(self.fake_python, self.bin_directory / name)
            (self.bin_directory / name).chmod(0o755)
        for name in ("dirname", "mkdir", "uname"):
            command = shutil.which(name)
            if command:
                (self.bin_directory / name).symlink_to(command)
        self.log = self.sandbox / "python-events.jsonl"
        self.environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith("SIM_") and key not in (
                "MPLCONFIGDIR", "DESP_NUMERIC_THREADS", "PYTHONHOME", "PYTHONPATH",
                "VIRTUAL_ENV", "BASH_ENV", "ENV",
            )
        }
        self.environment.update({
            "PATH": str(self.bin_directory),
            "SIM_ROOT": str(self.sandbox),
            "SIM_LOG": str(self.log),
            "SIM_PIP_MARKER": str(self.sandbox / "pip-restored"),
            "DISPLAY": ":simulated",
        })

    def command(self, arguments: tuple[str, ...]) -> list[str]:
        return [BASH, str(self.launcher), *arguments]

    def run_launcher(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.command(arguments),
            cwd=self.sandbox,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def events(self, action: str | None = None) -> list[dict]:
        records = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return [event for event in records if action is None or event["action"] == action]

    def create_existing_venv(self) -> Path:
        environment = self.project / ".venv"
        for relative in ("bin/python", "Scripts/python.exe"):
            target = environment / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.fake_python, target)
            target.chmod(0o755)
        return environment

    def assert_succeeded(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_no_install_or_app(self) -> None:
        self.assertFalse(self.events("install"))
        self.assertFalse(self.events("app"))

    def test_creates_environment_installs_requirements_then_starts_app(self) -> None:
        self.assert_succeeded(self.run_launcher())
        self.assertTrue(self.events("venv"))
        self.assertTrue(self.events("pip_check"))
        installs = self.events("install")
        self.assertTrue(installs)
        self.assertIn("--disable-pip-version-check", installs[-1]["arguments"])
        requirement_index = installs[-1]["arguments"].index("-r") + 1
        self.assertEqual(Path(installs[-1]["arguments"][requirement_index]), self.requirements)
        actions = [event["action"] for event in self.events()]
        self.assertLess(actions.index("venv"), actions.index("install"))
        self.assertLess(actions.index("install"), actions.index("app"))

    def test_existing_environment_installs_requirements_without_recreation(self) -> None:
        environment = self.create_existing_venv()
        sentinel = environment / "user-data.txt"
        sentinel.write_text("keep me")
        self.assert_succeeded(self.run_launcher())
        self.assertFalse(self.events("venv"))
        self.assertTrue(self.events("install"))
        self.assertEqual(sentinel.read_text(), "keep me")

    def test_preserves_arguments_working_directory_environment_and_exit_code(self) -> None:
        self.environment.update({"SIM_APP_EXIT": "17", "DESP_NUMERIC_THREADS": "3"})
        arguments = ("--input", "record with spaces.csv", "literal;$value", "--label=áé")
        result = self.run_launcher(*arguments)
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        app = self.events("app")[-1]
        self.assertEqual(app["arguments"], [str(self.app), *arguments])
        self.assertEqual(Path(app["cwd"]), self.project)
        self.assertEqual(Path(app["environment"]["MPLCONFIGDIR"]), self.project / ".cache" / "desp-matplotlib")
        for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            self.assertEqual(app["environment"][variable], "3")

    def test_preserves_custom_matplotlib_cache(self) -> None:
        cache = self.sandbox / "custom cache"
        self.environment["MPLCONFIGDIR"] = str(cache)
        self.assert_succeeded(self.run_launcher())
        self.assertEqual(self.events("app")[-1]["environment"]["MPLCONFIGDIR"], str(cache))
        self.assertTrue(cache.is_dir())

    def test_missing_pip_is_restored_before_installation(self) -> None:
        self.create_existing_venv()
        self.environment["SIM_PIP_MISSING"] = "1"
        self.assert_succeeded(self.run_launcher())
        actions = [event["action"] for event in self.events()]
        self.assertIn("ensurepip", actions)
        self.assertLess(actions.index("ensurepip"), actions.index("install"))

    def test_install_failure_prevents_app_start(self) -> None:
        self.environment["SIM_INSTALL_FAIL"] = "1"
        self.assertNotEqual(self.run_launcher().returncode, 0)
        self.assertTrue(self.events("install"))
        self.assertFalse(self.events("app"))

    def test_venv_creation_failure_prevents_installation(self) -> None:
        self.environment["SIM_VENV_FAIL"] = "1"
        self.assertNotEqual(self.run_launcher().returncode, 0)
        self.assertTrue(self.events("venv"))
        self.assert_no_install_or_app()

    def test_ensurepip_failure_prevents_installation(self) -> None:
        self.create_existing_venv()
        self.environment.update({"SIM_PIP_MISSING": "1", "SIM_ENSUREPIP_FAIL": "1"})
        self.assertNotEqual(self.run_launcher().returncode, 0)
        self.assertTrue(self.events("ensurepip"))
        self.assert_no_install_or_app()

    def test_old_existing_python_is_preserved_without_installation(self) -> None:
        environment = self.create_existing_venv()
        sentinel = environment / "user-data.txt"
        sentinel.write_text("keep me")
        self.environment["SIM_VENV_VERSION"] = "3.11.9"
        self.assertNotEqual(self.run_launcher().returncode, 0)
        self.assertFalse(self.events("venv"))
        self.assert_no_install_or_app()
        self.assertEqual(sentinel.read_text(), "keep me")

    def test_newer_compatible_python_is_accepted(self) -> None:
        self.create_existing_venv()
        self.environment["SIM_VENV_VERSION"] = "3.13.2"
        self.assert_succeeded(self.run_launcher())
        self.assertTrue(self.events("app"))

    def test_existing_directory_without_interpreter_is_preserved(self) -> None:
        environment = self.project / ".venv"
        environment.mkdir()
        sentinel = environment / "user-data.txt"
        sentinel.write_text("keep me")
        self.assertNotEqual(self.run_launcher().returncode, 0)
        self.assertFalse(self.events("venv"))
        self.assert_no_install_or_app()
        self.assertEqual(sentinel.read_text(), "keep me")

    def test_interpreter_outside_virtual_environment_is_rejected(self) -> None:
        self.create_existing_venv()
        self.environment["SIM_BAD_PREFIX"] = "1"
        self.assertNotEqual(self.run_launcher().returncode, 0)
        self.assert_no_install_or_app()

    def test_old_system_python_does_not_create_environment(self) -> None:
        self.environment["SIM_HOST_VERSION"] = "3.11.9"
        self.assertNotEqual(self.run_launcher().returncode, 0)
        self.assertFalse(self.events("venv"))
        self.assert_no_install_or_app()

    def test_missing_requirements_prevents_environment_creation(self) -> None:
        self.requirements.unlink()
        self.assertNotEqual(self.run_launcher().returncode, 0)
        self.assertFalse((self.project / ".venv").exists())
        self.assert_no_install_or_app()

    def test_missing_app_prevents_environment_creation(self) -> None:
        self.app.unlink()
        self.assertNotEqual(self.run_launcher().returncode, 0)
        self.assertFalse((self.project / ".venv").exists())
        self.assert_no_install_or_app()

    def test_invalid_numeric_threads_prevents_environment_creation(self) -> None:
        self.environment["DESP_NUMERIC_THREADS"] = "0"
        self.assertNotEqual(self.run_launcher().returncode, 0)
        self.assertFalse((self.project / ".venv").exists())
        self.assert_no_install_or_app()


    def test_prefers_python_312_for_new_environment(self) -> None:
        self.assert_succeeded(self.run_launcher())
        self.assertEqual(Path(self.events("venv")[-1]["executable"]).name, "python3.12")

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux-specific display check")
    def test_missing_graphical_session_prevents_environment_creation(self) -> None:
        self.environment.pop("DISPLAY", None)
        self.environment.pop("WAYLAND_DISPLAY", None)
        self.assertNotEqual(self.run_launcher().returncode, 0)
        self.assertFalse((self.project / ".venv").exists())
        self.assert_no_install_or_app()


if __name__ == "__main__":
    unittest.main()
