"""West extension for the RetroPLC Structured Text compiler."""
import os
import subprocess
from pathlib import Path

from west.commands import WestCommand


class PlcTranspile(WestCommand):
    def __init__(self):
        super().__init__(
            "plc-transpile",
            "Transpile a RetroPLC project",
            "Generate C++ sources and debug symbols from ProjectFiles/.",
        )

    def do_add_parser(self, parser_adder):
        parser = parser_adder.add_parser(
            self.name, help=self.help, description=self.description
        )
        parser.add_argument("project", type=Path, help="RetroPLC project directory (absolute path recommended)")
        return parser

    def do_run(self, args, unknown):
        project = args.project.expanduser().resolve()
        root = os.environ.get("PIXI_PROJECT_ROOT")
        if not root:
            self.die("Pixi environment is not activated.")

        strucpp = Path(root).resolve() / "strucpp"
        script = strucpp / "generate-strucpp-debug.mjs"
        source = project / "ProjectFiles"
        output = project / "Build" / "Generated"

        if not source.is_dir():
            self.die(f"Source directory not found: {source}")
        if not script.is_file():
            self.die(f"Compiler helper not found: {script}")
        if not (strucpp / "node_modules" / "strucpp").is_dir():
            self.die("Strucpp is not installed. Run pixi run setup-strucpp.")
        if output.resolve().is_relative_to(source.resolve()) or source.resolve().is_relative_to(output.resolve()):
            self.die("Source and generated output directories must not overlap.")

        self.inf(f"Source: {source}")
        self.inf(f"Output: {output}")
        try:
            subprocess.run(
                ["node", str(script), str(output), str(source)],
                cwd=strucpp,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            self.die(f"Transpilation failed: exit code {exc.returncode}")
        except OSError as exc:
            self.die(f"Could not execute compiler helper: {exc}")
        self.inf("PLC transpilation successful.")
