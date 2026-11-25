import json
import subprocess
import os
import sys
from pathlib import Path

from west.configuration import Configuration, ConfigFile
from west.util import west_topdir

from environment import WEST_ROOT, WORKSPACE, MANIFEST, CONFIG, SDK, ZEPHYR, run, managed_env

EXPECTED = {"manifest.path": "west_manifest", "manifest.file": "west.yml"}


def local_configuration():
    # WEST_CONFIG_LOCAL overrides topdir in West; validate before accessing it.
    for key, expected in {
        "WEST_CONFIG_LOCAL": CONFIG,
        "WEST_CONFIG_SYSTEM": WEST_ROOT / ".home/west-system.ini",
        "WEST_CONFIG_GLOBAL": WEST_ROOT / ".home/west-global.ini",
    }.items():
        if os.environ.get(key) != str(expected):
            raise RuntimeError(f"Invalid {key}; expected {expected}")
    if CONFIG.is_symlink() or CONFIG.parent.is_symlink():
        raise RuntimeError("Refusing symlinked West configuration")
    return Configuration(topdir=WEST_ROOT)


def init_workspace():
    for name in ("west.yml", "west-commands.yml"):
        if not (MANIFEST / name).is_file():
            raise RuntimeError(f"Manifest source missing: {MANIFEST / name}")
    if (WORKSPACE / ".west").exists():
        raise RuntimeError("Old workspace metadata detected. Move workspace to a backup before provisioning.")

    config = local_configuration()
    if CONFIG.exists():
        for key, expected in EXPECTED.items():
            actual = config.get(key, configfile=ConfigFile.LOCAL)
            if actual not in (None, expected):
                raise RuntimeError(f"Unexpected {key}: {actual!r}; refusing to overwrite")
    for key, expected in EXPECTED.items():
        config.set(key, expected, configfile=ConfigFile.LOCAL)
    verify_workspace()


def verify_workspace():
    if not CONFIG.is_file():
        raise RuntimeError("Local West configuration missing; run pixi run init-workspace")
    if (WORKSPACE / ".west").exists():
        raise RuntimeError("Old nested workspace metadata detected; move workspace to a backup")
    config = local_configuration()
    actual = Path(west_topdir(start=WEST_ROOT, fall_back=False)).resolve()
    if actual != WEST_ROOT:
        raise RuntimeError(f"Unexpected workspace: {actual}")
    for key, expected in EXPECTED.items():
        if config.get(key, configfile=ConfigFile.LOCAL) != expected:
            raise RuntimeError(f"Unexpected {key}; expected {expected}")
    # print(f"Verified workspace: {WEST_ROOT}", file=sys.stderr)


def update_modules():
    verify_workspace()
    run("west", "update")


def install_sdk():
    verify_workspace()
    # West may reuse an external SDK even with --install-dir.
    result = run("cmake", "-P", ZEPHYR / "scripts/west_commands/sdk/listsdk.cmake", capture=True)
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        if "Zephyr-sdk," in line and ", dir=" in line:
            candidate = Path(line.split(", dir=", 1)[1].strip()).resolve()
            if candidate != SDK.resolve():
                raise RuntimeError(f"External SDK detected: {candidate}; refusing installation")
    run("west", "sdk", "install", "--gnu-toolchains", "arm-zephyr-eabi", "--install-dir", SDK)
    verify_sdk()


def verify_sdk():
    expected = (ZEPHYR / "SDK_VERSION").read_text().strip()
    installed = (SDK / "sdk_version").read_text().strip()
    if expected != installed:
        raise RuntimeError(f"Expected SDK {expected}, found {installed}")
    compiler = SDK / "gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc"
    if not compiler.is_file() or not compiler.resolve().is_relative_to(SDK.resolve()):
        raise RuntimeError("Local ARM compiler missing")
    run(compiler, "--version")
    print(f"Verified SDK {installed}: {SDK}", file=sys.stderr)


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}), flush=True)


def plc_command(args):
    command = args[0]
    device = command in {"plc-upload", "plc-verify", "plc-debug"}
    terminal = False
    try:
        verify_workspace()
        with subprocess.Popen(["west", *args], cwd=WEST_ROOT,
                              env=managed_env(), text=True,
                              stdout=subprocess.PIPE if device else sys.stderr) as process:
            try:
                if device:
                    for line in process.stdout:
                        try:
                            record = json.loads(line)
                            if not isinstance(record, dict):
                                raise ValueError("Expected JSON object")
                        except ValueError:
                            print(line, end="", file=sys.stderr, flush=True)
                            continue
                        print(json.dumps(record), flush=True)
                        terminal = record.get("event") in {"result", "error"}
                status = process.wait()
            except KeyboardInterrupt:
                process.terminate()
                process.wait()
                raise
        if status:
            if not terminal:
                emit("error", success=False, command=command, code="west_failed",
                     message="West command failed; see stderr for details", exit_code=status)
            raise SystemExit(status if status > 0 else 128 - status)
        if not terminal:
            emit("result", success=True, command=command, status="completed")
    except KeyboardInterrupt:
        emit("error", success=False, command=command, code="interrupted", message="Interrupted")
        raise SystemExit(130) from None
    except Exception as exc:
        emit("error", success=False, command=command, code="execution_failed", message=str(exc))
        raise SystemExit(1) from None


def west_command():
    args = sys.argv[2:]
    if args and args[0].startswith("plc-") and not any(a in {"-h", "--help"} for a in args):
        plc_command(args)
        return
    verify_workspace()
    run("west", *args)


COMMANDS = {
    "init": init_workspace,
    "verify": verify_workspace,
    "update": update_modules,
    "west": west_command,
    "sdk-install": install_sdk,
    "sdk-verify": verify_sdk,
}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit(
            "Available commands: " + ", ".join(COMMANDS)
        )

    try:
        COMMANDS[sys.argv[1]]()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from None
