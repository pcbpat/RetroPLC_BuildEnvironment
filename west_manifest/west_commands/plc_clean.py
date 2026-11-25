"""Remove only RetroPLC-generated build directories."""
import shutil
from pathlib import Path
from west.commands import WestCommand


class PlcClean(WestCommand):
    def __init__(self):
        super().__init__('plc-clean', 'Clean PLC build outputs', 'Remove Build/Generated and Build/Zephyr only.')

    def do_add_parser(self, parser_adder):
        parser = parser_adder.add_parser(self.name, help=self.help, description=self.description)
        parser.add_argument('project', type=Path)
        return parser

    def do_run(self, args, unknown):
        project = args.project.expanduser().resolve()
        if not (project / 'ProjectFiles').is_dir():
            self.die('ProjectFiles directory missing')
        build = project / 'Build'
        paths = [build / name for name in ('Generated', 'Zephyr')]
        if build.is_symlink() or any(p.is_symlink() or (p.exists() and not p.is_dir()) for p in paths):
            self.die('Refusing to clean symlinked or non-directory build paths')
        for path in paths:
            if path.exists():
                shutil.rmtree(path)
                self.inf(f'Removed {path}')
