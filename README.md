# RetroPLC Build Environment

A self-contained, Pixi-managed build environment for the RetroPLC project. It provisions the host tools, Zephyr workspace, ARM toolchain and STruCpp compiler required to compile IEC 61131-3 Structured Text into firmware for the Arduino Opta.

The environment is intended for both standalone command-line development and integration with the RetroPLC IDE.

## Components

| Component | Purpose |
| --- | --- |
| [Pixi](https://pixi.sh/) | Host dependency management and task execution |
| [West](https://docs.zephyrproject.org/latest/develop/west/index.html) | Zephyr workspace and repository management |
| [Zephyr](https://www.zephyrproject.org/) | Embedded operating system and firmware build system |
| Zephyr SDK | ARM cross-compilation toolchain |
| [STruCpp](https://github.com/Autonomy-Logic/STruCpp) | Structured Text compiler and language server |
| [RetroPLC Runtime](https://github.com/pcbpat/RetroPLC_Runtime) | PLC execution environment and device firmware |
| [RetroPLC IDE](https://github.com/pcbpat/RetroPLC_IDE) | PLC project development environment |

## Prerequisites

- Linux x86-64 (`linux-64` is the currently configured Pixi platform).
- Git and [Pixi](https://pixi.sh/latest/installation/) available on the host.
- Internet access for the initial setup, including GitHub, conda-forge and npm downloads.
- Sufficient disk space for Zephyr, its modules, the SDK and build artifacts.

Python, Node.js, West, CMake, Ninja and the other host build dependencies are installed by Pixi. A separate system-wide Zephyr installation is not required.

## Getting started

```bash
git clone https://github.com/pcbpat/RetroPLC_BuildEnvironment.git
cd RetroPLC_BuildEnvironment
pixi run setup
```

The setup task provisions the West workspace, downloads the Runtime and its Zephyr dependencies, installs the ARM Zephyr SDK and installs STruCpp using `npm ci`.

Verify the installation:

```bash
pixi run verify-workspace
pixi run sdk-verify
pixi run verify-strucpp
pixi run west list
```

## Build a PLC project

A PLC project contains its Structured Text sources in a `ProjectFiles/` directory, including the PLC configuration and task declarations required by the Runtime.

```text
MyPLCProject/
└── ProjectFiles/
    ├── Main.st
    └── Configuration1.st
```

Build the project using its absolute path:

```bash
pixi run west plc-build /path/to/MyPLCProject
```

The build command first transpiles Structured Text into C++ and generates debug metadata. It then invokes the Zephyr build system with the generated sources and the RetroPLC Runtime.

```text
MyPLCProject/
├── ProjectFiles/
└── Build/
    ├── Generated/
    │   ├── ...                  # Generated C++ and header files
    │   ├── generated_debug.cpp
    │   └── debug_map.json
    └── Zephyr/                  # Zephyr sysbuild output
```

The current target is `arduino_opta/stm32h747xx/m7`. The signed application image is normally located at:

```text
Build/Zephyr/app/zephyr/zephyr.signed.bin
```

To generate C++ and debug metadata without compiling firmware:

```bash
pixi run west plc-transpile /path/to/MyPLCProject
```

To build the Runtime independently of a PLC project:

```bash
pixi run build-runtime
```

Runtime-only build output is written to `build/runtime/` inside the build environment.

## Available commands

Run commands from the BuildEnvironment repository root.

| Command | Description |
| --- | --- |
| `pixi run setup` | Provision the complete build environment |
| `pixi run init-workspace` | Initialize local West configuration |
| `pixi run setup-workspace` | Initialize and update West-managed repositories |
| `pixi run update-modules` | Update repositories according to the manifest |
| `pixi run verify-workspace` | Verify workspace root and manifest configuration |
| `pixi run setup-zephyr` | Provision repositories and the SDK |
| `pixi run setup-sdk` | Install and verify the SDK |
| `pixi run sdk-install` | Install the local ARM Zephyr SDK |
| `pixi run sdk-verify` | Verify SDK version and compiler location |
| `pixi run sdk-list` | List SDK installations detected by West |
| `pixi run setup-strucpp` | Install STruCpp and its npm dependencies |
| `pixi run verify-strucpp` | Install/check the STruCpp compiler version |
| `pixi run strucpp --help` | Access the STruCpp CLI |
| `pixi run strucpp-lsp` | Start the STruCpp language-server adapter over stdio |
| `pixi run west --help` | Access West and registered extensions |
| `pixi run west plc-transpile <project>` | Generate C++ and debug metadata |
| `pixi run west plc-build <project>` | Transpile and build PLC firmware |
| `pixi run build-runtime` | Build the standalone Runtime |

## Repository structure

```text
RetroPLC_BuildEnvironment/
├── pixi.toml                    # Host dependencies and tasks
├── pixi.lock                    # Locked host dependencies
├── scripts/
│   ├── environment.py           # Paths and subprocess isolation
│   └── workspace.py             # Workspace and SDK provisioning
├── west_manifest/
│   ├── west.yml                 # Parent West manifest
│   ├── west-commands.yml        # Custom West command declarations
│   └── west_commands/
│       ├── plc_transpile.py
│       └── plc_build.py
├── strucpp/
│   ├── package.json
│   ├── package-lock.json
│   ├── generate-strucpp-debug.mjs
│   └── language-server.mjs
├── .west/                       # Generated workspace configuration
├── .pixi/                       # Pixi-managed host tools
├── .home/                       # Private subprocess configuration
├── workspace/                  # West-managed repositories
│   ├── retroplc-runtime/
│   ├── zephyr/
│   ├── modules/
│   └── bootloader/
├── sdk/                        # Local Zephyr SDK
├── cache/                      # Local package caches
└── build/                      # Runtime-only build output
```

Generated directories and installed dependencies are excluded from version control. Both dependency lockfiles are kept in Git.

## Workspace management

The parent manifest in `west_manifest/west.yml` imports the RetroPLC Runtime manifest. The Runtime defines its Zephyr revision and required modules, while `path-prefix: workspace` places managed repositories below `workspace/`.

The environment initializes `.west/config` using West's Python configuration API (`Configuration.set()`), rather than invoking `west init`. This avoids the native initialization restriction when the installation is located beneath an existing West workspace. The manifest and custom commands are used directly from their source directory without copying them.

The provisioning scripts verify the workspace root and configuration paths before managed West operations. Existing incompatible local configuration is rejected rather than silently overwritten. Managed subprocesses use a private home directory and explicit toolchain/configuration paths to reduce interference from system installations.

The current layout places `.west/` alongside the Git repository. This is a nonstandard West topology; compatibility should be checked before upgrading West. The initialization workaround uses public West APIs, but nested initialization is not a native `west init` feature.

## Dependency updates and reproducibility

- `pixi.lock` locks the host environment.
- `strucpp/package-lock.json` locks the compiler package and npm dependencies.
- The Runtime manifest controls Zephyr and its imported module revisions.
- The parent manifest currently tracks the Runtime's `main` branch. Pin it to a commit or release tag for reproducible firmware builds.

To update West-managed repositories:

```bash
pixi run update-modules
```

For a complete setup or after changing dependency definitions, rerun `pixi run setup`. Review and commit intentional lockfile changes when updating dependencies.

## Troubleshooting

**Old workspace metadata detected:** Earlier versions stored `.west/` under `workspace/`. Back up that directory before provisioning the current layout:

```bash
mv workspace workspace.backup
pixi run setup-workspace
```

Choose another backup name if `workspace.backup` already exists.

**Unexpected workspace or configuration:** Run `pixi run verify-workspace` from the repository root. Check that `.west/config` references `west_manifest` and that no obsolete `workspace/.west/` exists. Do not delete unrelated West workspaces elsewhere on the host.

**External SDK detected:** SDK provisioning deliberately rejects a detected SDK outside the configured local SDK directory. Review the detected SDK registration before retrying; do not remove an unrelated SDK indiscriminately.

**Missing custom West commands:** Check that `west_manifest/west-commands.yml` and both Python extension files are present, then run `pixi run setup-workspace` and `pixi run west --help`.

## Project status

RetroPLC is under active development. The current build environment targets Linux x86-64 and the Arduino Opta M7 core. Other host platforms and targets require additional configuration and validation. Firmware deployment and live device debugging are outside the scope of this build environment's current provisioning commands.
