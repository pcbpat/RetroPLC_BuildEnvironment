import subprocess
from pathlib import Path

from west.commands import WestCommand


class PlcBuild(WestCommand):

    def __init__(self):
        super().__init__(
            "plc-build",
            "Build a RetroPLC project",
            "Transpile Structured Text and compile PLC firmware.",
        )

    def do_add_parser(self, parser_adder):
        parser = parser_adder.add_parser(
            self.name,
            help=self.help,
            description=self.description,
        )

        parser.add_argument(
            "project",
            type=Path,
            help="RetroPLC project directory",
        )

        return parser

    def do_run(self, args, unknown):
        project = args.project.expanduser().resolve()

        generated = project / "Build" / "Generated"
        build = project / "Build" / "Zephyr"
        runtime = Path(self.topdir) / "retroplc-runtime" / "app"

        try:
            self.inf("Transpiling Structured Text...")

            subprocess.run(
                ["west", "plc-transpile", str(project)],
                cwd=self.topdir,
                check=True,
            )

            self.inf("Building RetroPLC firmware...")

            subprocess.run(
                [
                    "west", "build",
                    "-p", "always",
                    "--sysbuild",
                    "-b", "arduino_opta/stm32h747xx/m7",
                    "-s", str(runtime),
                    "-d", str(build),
                    "--",
                    f"-DRETROPLC_GENERATED_DIR={generated}",
                ],
                cwd=self.topdir,
                check=True,
            )

        except subprocess.CalledProcessError as exc:
            self.die(f"PLC build failed: {exc.returncode}")

        except OSError as exc:
            self.die(str(exc))

        self.inf("PLC build completed successfully.")
