"""Shared paths and process isolation for the Pixi-managed platform."""
import os
import subprocess
from pathlib import Path

ROOT = Path(os.environ["PIXI_PROJECT_ROOT"]).resolve()
WORKSPACE = ROOT / "workspace"
RUNTIME = WORKSPACE / "retroplc-runtime"
MANIFEST_SOURCE = ROOT / "west_manifest"
MANIFEST = WORKSPACE / "manifest"
CONFIG = WORKSPACE / ".west/config"
ZEPHYR = WORKSPACE / "zephyr"
SDK = ROOT / "sdk"
HOME = ROOT / ".home"


def run(*args, capture=False):
    HOME.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    # Keep HOME private only for managed subprocesses, not the Pixi shell.
    env["HOME"] = str(HOME)
    for key in ("PYTHONPATH", "PYTHONHOME", "GIT_DIR", "GIT_WORK_TREE",
                "Zephyr_DIR", "Zephyr-sdk_DIR", "CMAKE_TOOLCHAIN_FILE",
                "ZEPHYR_TOOLCHAIN_PATH", "CMAKE_PREFIX_PATH"):
        env.pop(key, None)
    # Validate activation rather than silently falling back to host paths.
    for key, expected in {"ZEPHYR_BASE": ZEPHYR,
                          "ZEPHYR_SDK_INSTALL_DIR": SDK,
                          "WEST_CONFIG_LOCAL": CONFIG}.items():
        if env.get(key) != str(expected):
            raise RuntimeError(f"Invalid {key}: {env.get(key)!r}; expected {expected}")
    if not ZEPHYR.is_dir():
        env.pop("ZEPHYR_BASE", None)
    return subprocess.run([str(arg) for arg in args], cwd=WORKSPACE,
                          env=env, check=True, text=True, capture_output=capture)
