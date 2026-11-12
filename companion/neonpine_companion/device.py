"""NeonPine USB protocol (firmware/neonpine/neonpine.c, usb_config.h).

Feature reports on 1209:D003:
  0xAA GET  status (64 bytes)
  0xAB SET  command [cmd][args...] (8 bytes)
  0xAC SET  live frame: 20 levels 0-255 (left electrodes LA1-10, then right)
  0xAE SET/GET store page [page][op/state][seq][64 bytes]
  0xFD SET  reboot into the USB bootloader (1209:B003)
"""
import struct
import time
from dataclasses import dataclass, field, fields

from . import hid_backend

VID = 0x1209
PID_APP = 0xD003
PID_BOOT = 0xB003

REPORT_STATUS, REPORT_COMMAND, REPORT_LIVE, REPORT_STORE, REPORT_REBOOT = 0xAA, 0xAB, 0xAC, 0xAE, 0xFD

CMD = dict(mode=1, hv=2, lamps=3, clear=4, ton=5, pause=6, touch=7, period=8, level=9, pwm=10, budget=11,
           style=12, show=13, bright=14, sleep=15, autolight=16, dim=17, wave=18, save=19)

MODE_OFF, MODE_AUTO, MODE_MANUAL = 0, 1, 2
ST_OP_READ, ST_OP_WRITE, ST_OP_APPLY, ST_OK, ST_ERR = 1, 2, 3, 0x80, 0x81

BUILTIN_NAMES = ["Candle", "Breathe", "Twinkle", "Garland", "Snowfall", "Heartbeat", "Drift", "Sleep"]
BUILTIN_HINTS = [
    "Every electrode flickers on its own, with occasional dips",
    "The whole tree breathes while the glow drifts left and right",
    "Random electrodes swell and fade",
    "A chase up the tiers, half a lamp at a time, then a star flash",
    "Soft pulses drifting down the tiers",
    "Steady tree, the star beats twice a second",
    "Cycles through the drift list, crossfading",
    "Candle that dims over the sleep time, then switches off",
]
BRINGUP_NAMES = {8: "Test sequence", 9: "Brightness sweep", 10: "Steady glow"}
SHOW_LIVE = 15
SHOW_CUSTOM0 = 16
N_CUSTOM_MAX = 8
N_BASIC = 6  # modes with speed / gain / offset
FAULTS = ["", "Overvoltage", "No rise (HV < 20 V for 1 s)"]
GESTURES = ["-", "tap", "double tap", "hold (ramp)", "hold 3 s (off/on)", "triple tap", "wave"]

STATUS_FMT = "<BBBBBBBBHHHHHHHHIIBBBBBBBBBBHHBBHHBBBBHHI"
STATUS_SIZE = struct.calcsize(STATUS_FMT)  # 64


class DeviceError(Exception):
    pass


@dataclass
class Status:
    report_id: int = 0
    fw_version: int = 0
    mode: int = 0
    step: int = 0
    fault: int = 0
    flags: int = 0
    hv_set: int = 0
    period_us: int = 0
    hv_cv: int = 0
    vdd_mv: int = 0
    adc_vfb: int = 0
    adc_ldr: int = 0
    touch: int = 0
    touch_base: int = 0
    ton: int = 0
    duty_pm: int = 0
    uptime_ms: int = 0
    lamps: int = 0
    level: int = 0
    budget: int = 0
    pwm_ms: int = 0
    pwm_min_10us: int = 0
    show: int = 0
    style: int = 0
    user_level: int = 0
    gesture: int = 0
    sleep_min: int = 0
    flags2: int = 0
    ambient: int = 0
    reflection: int = 0
    lux: int = 0
    adapt: int = 0
    late_us: int = 0
    late_peak_us: int = 0
    caps: int = 0
    store_pages: int = 0
    n_custom: int = 0
    cfg_flags: int = 0
    store_gen: int = 0
    stack_free: int = 0
    uid: int = 0

    @classmethod
    def parse(cls, raw):
        raw = bytes(raw).ljust(STATUS_SIZE, b"\0")[:STATUS_SIZE]
        return cls(*struct.unpack(STATUS_FMT, raw))

    hv = property(lambda s: s.hv_cv / 100)
    touched = property(lambda s: bool(s.flags & 1))
    boost_on = property(lambda s: bool(s.flags & 4))
    sleep_on = property(lambda s: bool(s.flags2 & 1))
    daylight_off = property(lambda s: bool(s.flags2 & 2))
    autolight = property(lambda s: bool(s.flags2 & 4))
    dim_rail = property(lambda s: bool(s.flags2 & 8))
    is_on = property(lambda s: s.mode != MODE_OFF)
    has_store = property(lambda s: bool(s.caps & 1))
    unsaved = property(lambda s: bool(s.cfg_flags & 0x80))

    def lamp_bits(self, i):
        return (self.lamps >> (2 * i)) & 3


def show_name(n, custom_names=()):
    if n < len(BUILTIN_NAMES):
        return BUILTIN_NAMES[n]
    if n in BRINGUP_NAMES:
        return BRINGUP_NAMES[n]
    if n == SHOW_LIVE:
        return "Live (from the app)"
    if SHOW_CUSTOM0 <= n < SHOW_CUSTOM0 + N_CUSTOM_MAX:
        k = n - SHOW_CUSTOM0
        return custom_names[k] if k < len(custom_names) and custom_names[k] else "Custom %d" % (k + 1)
    return "Show %d" % n


# ---- settings page (store page 0) ---------------------------------------------------------------

CFG_MAGIC, CFG_VERSION = 0x4350, 1
CFG_AUTOLIGHT, CFG_DIM_RAIL, CFG_REMEMBER = 1, 2, 4
CFG_FMT = "<HBBBBBBHHHBB18s16s12sH"


@dataclass
class ModeParams:
    speed: int = 64    # 64 = 1x
    gain: int = 128    # 128 = 1x
    offset: int = 0    # -128..127, 1/256 of full brightness


@dataclass
class Config:
    show: int = 0
    style: int = 0
    level: int = 255
    autolight: bool = True
    dim_rail: bool = False
    remember: bool = True
    sleep_min: int = 20
    tap_mask: int = 0x00FF
    drift_mask: int = 0x003F
    drift_s: int = 180
    fade_ds: int = 15
    params: list = field(default_factory=lambda: [ModeParams() for _ in range(N_BASIC)])
    name: str = ""

    def pack(self):
        flags = (CFG_AUTOLIGHT if self.autolight else 0) | (CFG_DIM_RAIL if self.dim_rail else 0) | (CFG_REMEMBER if self.remember else 0)
        pars = b"".join(struct.pack("<BBb", clamp(p.speed, 0, 255), clamp(p.gain, 0, 255), clamp(p.offset, -128, 127)) for p in self.params)
        name = self.name.encode("utf-8")[:16]
        body = struct.pack(CFG_FMT[:-1], CFG_MAGIC, CFG_VERSION, self.show & 255, self.style & 255, clamp(self.level, 8, 255), flags,
                           clamp(self.sleep_min, 1, 255), self.tap_mask & 0xFFFF, self.drift_mask & 0xFFFF,
                           clamp(self.drift_s, 5, 65535), clamp(self.fade_ds, 0, 255), 0, pars, name.ljust(16, b"\0"), bytes(12))
        return body + struct.pack("<H", sum(body) & 0xFFFF)

    @classmethod
    def unpack(cls, raw):
        (magic, version, show, style, level, flags, sleep_min, tap, drift, drift_s, fade_ds, _rsv, pars, name, _rsv1,
         csum) = struct.unpack(CFG_FMT, bytes(raw[:64]))
        if magic != CFG_MAGIC or version != CFG_VERSION or csum != sum(raw[:62]) & 0xFFFF:
            return None
        params = [ModeParams(*struct.unpack_from("<BBb", pars, 3 * i)) for i in range(N_BASIC)]
        return cls(show, style, level, bool(flags & CFG_AUTOLIGHT), bool(flags & CFG_DIM_RAIL), bool(flags & CFG_REMEMBER),
                   sleep_min, tap, drift, drift_s, fade_ds, params, name.split(b"\0")[0].decode("utf-8", "replace"))

    def copy(self):
        c = Config(**{f.name: getattr(self, f.name) for f in fields(self)})
        c.params = [ModeParams(p.speed, p.gain, p.offset) for p in self.params]
        return c


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else int(v)


# ---- device ------------------------------------------------------------------------------------

def find_trees():
    return hid_backend.enumerate_devices(VID, PID_APP)


def find_bootloaders():
    return hid_backend.enumerate_devices(VID, PID_BOOT)


class Tree:
    """One connected NeonPine running the firmware. Not thread safe: use it from one thread."""

    def __init__(self, info):
        self.info = info
        self.dev = hid_backend.HidDevice(info)
        self._seq = 0
        self.status = self.read_status()

    def close(self):
        self.dev.close()

    # -- status / commands

    def read_status(self):
        self.status = Status.parse(self.dev.get_feature(REPORT_STATUS, STATUS_SIZE))
        return self.status

    def command(self, name, *args):
        payload = bytes([CMD[name]]) + bytes(args)
        self.dev.set_feature(bytes([REPORT_COMMAND]) + payload.ljust(7, b"\0"))

    def command16(self, name, value):
        self.command(name, value & 0xFF, (value >> 8) & 0xFF)

    def set_show(self, n):
        self.command("show", n)

    def set_power(self, on):
        self.command("mode", MODE_AUTO if on else MODE_OFF)

    def set_brightness(self, v):
        self.command("bright", clamp(v, 8, 255))

    def set_style(self, retro):
        self.command("style", 1 if retro else 0)

    def set_sleep(self, on):
        self.command("sleep", 1 if on else 0)

    def set_autolight(self, on):
        self.command("autolight", 1 if on else 0)

    def set_dim_rail(self, on):
        self.command("dim", 1 if on else 0)

    def save(self):
        self.command("save")

    def live_frame(self, left, right):
        """left / right: 10 levels each, 0.0-1.0 or 0-255."""
        def b(v):
            return clamp(round(v * 255) if isinstance(v, float) else v, 0, 255)
        self.dev.set_feature(bytes([REPORT_LIVE] + [b(v) for v in left] + [b(v) for v in right]))

    def reboot_to_bootloader(self):
        """Ask the firmware to restart into the USB bootloader. D- is pulled up for good (no pull-up switch),
        so the host doesn't notice the restart: keep this Tree open and call poke() until the bootloader
        (1209:B003) shows up - the failing transfers make the host reset the port (minichlink relies on the
        same), and then the bootloader enumerates."""
        try:
            self.dev.set_feature(bytes([REPORT_REBOOT, 0x12, 0x34, 0xAA, 0xBB, 0xCC, 0xDD]))
        except OSError:
            pass  # the device resets mid-transfer

    def poke(self):
        try:
            self.dev.get_feature(REPORT_STATUS, STATUS_SIZE)
        except OSError:
            pass

    # -- store

    def store(self, page, op, data=bytes(64), timeout=1.5):
        """One store transaction; returns the page's 64 bytes as the firmware sees them afterwards."""
        last = None
        for attempt in range(5):
            self._seq = (self._seq + 1) & 0xFF
            seq = self._seq
            try:
                self.dev.set_feature(bytes([REPORT_STORE, page, op, seq]) + bytes(data).ljust(64, b"\0")[:64])
            except OSError as e:
                # A flash write stalls the chip for ~5 ms; if the transfer's status stage fell into that, the
                # request still arrived. The sequence number in the reply tells: poll before sending again.
                last = e
            t0 = time.monotonic()
            time.sleep(0.003 if op == ST_OP_READ else 0.015)
            while time.monotonic() - t0 < timeout:
                try:
                    r = self.dev.get_feature(REPORT_STORE, 68)
                except OSError as e:
                    last = e
                    time.sleep(0.02)
                    continue
                if r[1] == page and r[3] == seq and r[2] & 0x80:
                    if r[2] == ST_ERR:
                        raise DeviceError("the tree refused store page %d (op %d)" % (page, op))
                    return bytes(r[4:68])
                if r[3] != seq or r[1] != page:
                    break  # dropped (the tree was saving its settings): send again
                time.sleep(0.005)
        raise DeviceError("no answer from the tree for store page %d%s" % (page, ": %s" % last if last else ""))

    def read_config(self):
        cfg = Config.unpack(self.store(0, ST_OP_READ))
        if cfg is None:
            raise DeviceError("the tree sent an invalid settings page")
        return cfg

    def write_config(self, cfg, persist=True):
        """persist=False only applies it (live preview); persist=True also saves it to flash."""
        r = Config.unpack(self.store(0, ST_OP_WRITE if persist else ST_OP_APPLY, cfg.pack()))
        if r is None:
            raise DeviceError("the tree sent an invalid settings page")
        return r

    def read_blob(self, progress=None):
        pages = max(1, self.status.store_pages or 16) - 1
        first = self.store(1, ST_OP_READ)
        length = first[2] | first[3] << 8
        if first[:2] != b"AN" or not 8 <= length <= pages * 64:
            return b""
        out = bytearray(first)
        n = (length + 63) // 64
        for p in range(2, n + 1):
            out += self.store(p, ST_OP_READ)
            if progress:
                progress(p, n)
        return bytes(out[:length])

    def write_blob(self, blob, progress=None):
        """Header page last: until it is written the old header's checksum fails, so the tree never
        plays a half-written blob."""
        pages = max(1, self.status.store_pages or 16) - 1
        if len(blob) > pages * 64:
            raise DeviceError("the animations need %d bytes, the tree has %d" % (len(blob), pages * 64))
        data = bytes(blob).ljust(((len(blob) + 63) // 64) * 64, b"\0")
        chunks = [data[i:i + 64] for i in range(0, len(data), 64)]
        order = list(range(1, len(chunks))) + [0]
        for done, k in enumerate(order, 1):
            if self.store(k + 1, ST_OP_READ) != chunks[k]:
                r = self.store(k + 1, ST_OP_WRITE, chunks[k])
                if r != chunks[k]:
                    raise DeviceError("store page %d did not verify" % (k + 1))
            if progress:
                progress(done, len(order))
        self.read_status()
