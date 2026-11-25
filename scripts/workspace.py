import sys
from pathlib import Path
from configparser import ConfigParser
from shutil import copytree

from environment import WORKSPACE, MANIFEST_SOURCE, MANIFEST, CONFIG, SDK, ZEPHYR, run

def init_workspace():
    if not (MANIFEST_SOURCE / "west.yml").is_file():
        raise RuntimeError(f"Parent manifest missing: {MANIFEST_SOURCE / 'west.yml'}")
    if not (MANIFEST_SOURCE / "west-commands.yml").is_file():
        raise RuntimeError(f"Extension descriptor missing: {MANIFEST_SOURCE / 'west-commands.yml'}")

    # Refuse to silently convert the old Runtime-owned workspace.
    config = ConfigParser(interpolation=None)
    if CONFIG.exists():
        config.read(CONFIG, encoding="utf-8")
        if config.get("manifest", "path", fallback="") != "manifest":
            raise RuntimeError("Old workspace detected. Move workspace to a backup before provisioning.")
        if config.get("manifest", "file", fallback="west.yml") != "west.yml":
            raise RuntimeError("Unexpected manifest file in existing workspace")

    copytree(MANIFEST_SOURCE, MANIFEST, dirs_exist_ok=True,
             ignore=lambda path, names: {name for name in names
                                         if name in {"__pycache__", ".git"}})
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG.exists():
        CONFIG.write_text(
            "[manifest]\n"
            "path = manifest\n"
            "file = west.yml\n",
            encoding="utf-8",
        )


def verify_workspace():
    if not CONFIG.is_file():
        raise RuntimeError("Local West configuration missing")

    actual = Path(
        run("west", "topdir", capture=True).stdout.strip()
    ).resolve()

    if actual != WORKSPACE:
        raise RuntimeError(f"Unexpected workspace: {actual}")

    manifest_path = run(
        "west", "config", "manifest.path", capture=True
    ).stdout.strip()

    manifest_file = run(
        "west", "config", "manifest.file", capture=True
    ).stdout.strip()

    if manifest_path != "manifest":
        raise RuntimeError("Unexpected manifest path")

    if manifest_file != "west.yml":
        raise RuntimeError("Unexpected manifest file")

    print(f"Verified workspace: {WORKSPACE}")


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
    print(f"Verified SDK {installed}: {SDK}")


def west_command():
    verify_workspace()
    run("west", *sys.argv[2:])


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

    COMMANDS[sys.argv[1]]()
