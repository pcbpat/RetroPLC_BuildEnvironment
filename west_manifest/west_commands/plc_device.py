"""RetroPLC device commands using the public mcumgr-toolkit Python API."""
import json
import time
from pathlib import Path

from west.commands import WestCommand


def emit(event, **fields):
    print(json.dumps({'event': event, **fields}, default=json_default), flush=True)


def firmware_path(args):
    return args.project.expanduser().resolve() / 'Build/Zephyr/app/zephyr/zephyr.signed.bin'


def json_default(value):
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(type(value).__name__)


def positive(value):
    number = int(value)
    if number <= 0:
        raise ValueError('must be positive')
    return number


class DeviceCommand(WestCommand):
    def do_add_parser(self, parser_adder):
        parser = parser_adder.add_parser(self.name, help=self.help, description=self.description)
        parser.add_argument('project', type=Path, help='RetroPLC project directory')
        transport = parser.add_mutually_exclusive_group(required=True)
        transport.add_argument('--serial', help='Framed SMP serial port, e.g. /dev/ttyACM0')
        transport.add_argument('--udp', help='SMP UDP host (requires runtime UDP support)')
        parser.add_argument('--port', type=positive, default=1337, help='UDP port')
        parser.add_argument('--baud', type=positive, default=115200)
        parser.add_argument('--timeout-ms', type=positive, default=10000)
        parser.add_argument('--frame-size', type=positive, help='Explicit SMP frame size instead of auto detection')
        self.add_options(parser)
        return parser

    def add_options(self, parser):
        pass

    def do_run(self, args, unknown):
        try:
            import mcumgr_toolkit as toolkit
            if args.port > 65535:
                raise ValueError('UDP port must be <= 65535')
            self.prepare(args, toolkit)
            connect = (lambda: toolkit.MCUmgrClient.serial(args.serial, baud_rate=args.baud, timeout_ms=args.timeout_ms)) if args.serial else (lambda: toolkit.MCUmgrClient.udp(args.udp, port=args.port, timeout_ms=args.timeout_ms))
            with connect() as client:
                if args.frame_size is None:
                    client.use_auto_frame_size()
                else:
                    client.set_frame_size(args.frame_size)
                self.execute(args, client)
        except KeyboardInterrupt:
            emit('error', success=False, code='interrupted', message='Interrupted')
            raise SystemExit(130) from None
        except Exception as exc:
            emit('error', success=False, code='device_error', command=self.name, message=str(exc))
            raise SystemExit(1) from None

    def prepare(self, args, toolkit):
        pass


class PlcUpload(DeviceCommand):
    def __init__(self):
        super().__init__('plc-upload', 'Upload PLC firmware', 'Upload and activate an MCUboot image using MCUmgr.')

    def add_options(self, parser):
        parser.add_argument('--skip-reboot', action='store_true')
        parser.add_argument('--upgrade-only', action='store_true')
        parser.add_argument('--force-confirm', action='store_true', help='Request permanent activation without test boot (best effort)')

    def prepare(self, args, toolkit):
        self.data = firmware_path(args).read_bytes()
        self.info = toolkit.mcuboot_get_image_info(self.data)

    def execute(self, args, client):
        def progress(step, counts):
            event = {'step': step}
            if counts is not None:
                event.update(transmitted=counts[0], total=counts[1])
            emit("progress", **event)

        active = next((s for s in client.image_get_state() if s.image == 0 and s.active and s.hash == self.info.hash), None)
        if active is not None:
            emit('result', success=True, status='already_installed', hash=self.info.hash.hex(), confirmed=active.confirmed)
            return
        client.firmware_update(self.data, bootloader_type='MCUboot', skip_reboot=args.skip_reboot,
                               force_confirm=args.force_confirm, upgrade_only=args.upgrade_only, progress=progress)
        emit('result', success=True, status='update_requested', hash=self.info.hash.hex(), reboot_requested=not args.skip_reboot)


class PlcVerify(DeviceCommand):
    def __init__(self):
        super().__init__('plc-verify', 'Verify running PLC firmware', 'Compare the active MCUboot hash against the local build.')

    def add_options(self, parser):
        parser.add_argument('--confirm', action='store_true', help='Confirm the matching active image after external functional checks')

    def prepare(self, args, toolkit):
        self.info = toolkit.mcuboot_get_image_info(firmware_path(args).read_bytes())

    def execute(self, args, client):
        def matching_active(states):
            return next((s for s in states if s.image == 0 and s.active and s.hash == self.info.hash), None)
        active = matching_active(client.image_get_state())
        if active is None:
            raise RuntimeError('Active image 0 does not match local firmware')
        if args.confirm and not active.confirmed:
            active = matching_active(client.image_set_state(confirm=True))
            if active is None or not active.confirmed:
                raise RuntimeError('Image confirmation not verified')
        emit('result', success=True, verified=True, hash=self.info.hash.hex(), version=active.version, confirmed=active.confirmed)


class PlcDebug(DeviceCommand):
    def __init__(self):
        super().__init__('plc-debug', 'Read symbolic PLC variables', 'Read paginated group 64 command 1 snapshots as JSON lines.')

    def add_options(self, parser):
        parser.add_argument('--limit', type=positive, default=8)
        parser.add_argument('--watch', action='store_true')
        parser.add_argument('--interval', type=float, default=0.5)

    def prepare(self, args, toolkit):
        if not 0 < args.limit <= 16 or not args.interval > 0:
            raise ValueError('limit must be 1..16 and interval must be positive')
        self.info = toolkit.mcuboot_get_image_info(firmware_path(args).read_bytes())

    def execute(self, args, client):
        if not any(s.image == 0 and s.active and s.hash == self.info.hash for s in client.image_get_state()):
            raise RuntimeError('Active firmware does not match local build; debug IDs may differ')
        while True:
            offset = 0
            while True:
                page = client.raw_command(False, 64, 1, {'offset': offset, 'limit': args.limit})
                total, following = page['total'], page['next']
                if page['offset'] != offset or not offset <= following <= total or (following == offset and offset < total):
                    raise RuntimeError('Invalid debug pagination response')
                emit('snapshot', **page)
                if following == total:
                    break
                offset = following
            if not args.watch:
                emit('result', success=True, status='snapshot_complete')
                return
            time.sleep(args.interval)
