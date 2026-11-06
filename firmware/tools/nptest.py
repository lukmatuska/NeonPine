#!/usr/bin/env python3
"""NeonPine test firmware – USB monitor / control (Linux hidraw, no extra packages).

  nptest.py                 status once
  nptest.py watch           status every 0.2 s
  nptest.py mode auto|manual|off
  nptest.py hv 90           HV setpoint in volts (0 = boost off, max 105)
  nptest.py lamps 1k 2a 3ac all=off ...   manual lamp states (k = pad 1, a = pad 2, ac = both)
  nptest.py pause on|off    hold / resume the auto sequence
  nptest.py level 128       brightness 0-255 for manual mode (gamma ~2)
  nptest.py ton 15          boost gate on-time in us (1-20, default 15)
  nptest.py freq 30         boost frequency in kHz (5 .. 1/(t_on + 4 us), default 30)
  nptest.py touch 40        touch threshold above baseline (0 = auto)
  nptest.py clear           clear a fault
  nptest.py bootloader      reboot into the USB bootloader (minichlink does this by itself)
"""
import fcntl
import glob
import os
import re
import struct
import sys
import time

VID, PID = 0x1209, 0xD003
REPORT_STATUS, REPORT_COMMAND, REPORT_REBOOT = 0xAA, 0xAB, 0xFD
CMD = dict(mode=1, hv=2, lamps=3, clear=4, ton=5, pause=6, touch=7, period=8, level=9)
MODES = ["off", "auto", "manual"]
FAULTS = ["none", "OVERVOLTAGE", "NO RISE (HV < 20 V for 1 s)"]
LAMP = ["--", "K", "A", "AC"]
STATUS_FMT = "<BBBBBBBBHHHHHHHHIIB3x"  # see struct np_status in neonpine_test.c


def ioc(nr, size):
    return (3 << 30) | (size << 16) | (ord("H") << 8) | nr  # _IOC(_IOC_READ|_IOC_WRITE, 'H', nr, size)


def find_device():
    want = "HID_ID=0003:%08X:%08X" % (VID, PID)
    for d in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(d, "device/uevent")) as f:
                if want in f.read().upper():
                    return "/dev/" + os.path.basename(d)
        except OSError:
            pass
    sys.exit("NeonPine test firmware (%04x:%04x) not found – still in the bootloader, or no udev rule?" % (VID, PID))


def get_status(fd):
    buf = bytearray(struct.calcsize(STATUS_FMT))
    buf[0] = REPORT_STATUS
    fcntl.ioctl(fd, ioc(0x07, len(buf)), buf)  # HIDIOCGFEATURE
    return struct.unpack(STATUS_FMT, bytes(buf))


def send(fd, report_id, payload):
    buf = bytearray([report_id]) + bytes(payload)
    fcntl.ioctl(fd, ioc(0x06, len(buf)), buf)  # HIDIOCSFEATURE


def command(fd, cmd, args=b""):
    send(fd, REPORT_COMMAND, (bytes([CMD[cmd]]) + bytes(args)).ljust(7, b"\0"))


def show(s):
    (rid, ver, mode, step, fault, flags, hv_set, period_us, hv_cv, vdd, vfb, ldr, touch, tbase, ton, duty, up, lamps, level) = s
    if step == 0:
        stp = "charge"
    elif step <= 20:
        stp = "LA%d %s" % ((step + 1) // 2, "K" if step % 2 else "A")
    else:
        stp = {21: "all K", 22: "all A", 23: "all AC", 24: "sweep"}.get(step, str(step))
    lamp_txt = " ".join("%d:%s" % (i + 1, LAMP[(lamps >> 2 * i) & 3]) for i in range(10))
    print("fw v%d  up %7.1f s  mode %-6s step %-7s%s%s" % (
        ver, up / 1000, MODES[mode] if mode < 3 else mode, stp, "  PAUSED" if flags & 2 else "",
        "  FAULT: " + FAULTS[fault] if fault else ""))
    print("  HV %6.1f V (set %d V, boost %s, t_on %.1f us, %.1f kHz, pulsing %4.1f %%)  VDD %.2f V  VFB adc %d" % (
        hv_cv / 100, hv_set, "on " if flags & 4 else "off", ton / 48, 1000 / period_us if period_us else 0,
        duty / 10, vdd / 1000, vfb))
    print("  light %4d   touch %5d (base %5d)%s" % (ldr, touch, tbase, "  TOUCHED" if flags & 1 else ""))
    print("  lamps " + lamp_txt + "   brightness %3d/255" % level)


def parse_lamps(args):
    word = 0
    for a in args:
        m = re.fullmatch(r"(\d+|all)=?(k|a|ac|off)", a.lower())
        if not m or (m[1] != "all" and not 1 <= int(m[1]) <= 10):
            sys.exit("bad lamp spec %r – use e.g. 3k, 7a, 10ac, all=off" % a)
        st = {"off": 0, "k": 1, "a": 2, "ac": 3}[m[2]]
        for i in range(10) if m[1] == "all" else [int(m[1]) - 1]:
            word = (word & ~(3 << 2 * i)) | (st << 2 * i)
    return word


def main():
    args = sys.argv[1:]
    fd = os.open(find_device(), os.O_RDWR)
    try:
        if not args:
            show(get_status(fd))
        elif args[0] == "watch":
            while True:
                print("\033[H\033[J", end="")
                show(get_status(fd))
                time.sleep(0.2)
        elif args[0] == "mode":
            command(fd, "mode", [MODES.index(args[1])])
        elif args[0] == "hv":
            command(fd, "hv", [int(args[1])])
        elif args[0] == "lamps":
            command(fd, "lamps", struct.pack("<I", parse_lamps(args[1:])))
        elif args[0] == "pause":
            command(fd, "pause", [args[1] in ("on", "1")])
        elif args[0] == "ton":
            command(fd, "ton", struct.pack("<H", round(float(args[1]) * 48)))
        elif args[0] == "level":
            command(fd, "level", [int(args[1])])
        elif args[0] == "freq":
            command(fd, "period", struct.pack("<H", round(48000 / float(args[1]))))
        elif args[0] == "touch":
            command(fd, "touch", struct.pack("<H", int(args[1])))
        elif args[0] == "clear":
            command(fd, "clear")
        elif args[0] == "bootloader":
            try:
                send(fd, REPORT_REBOOT, b"\x12\x34\xaa\xbb\xcc\xdd")
            except OSError:
                pass  # the device resets mid-transfer
        else:
            sys.exit(__doc__)
        if args and args[0] not in ("watch", "bootloader"):
            time.sleep(0.05)
            show(get_status(fd))
    except KeyboardInterrupt:
        pass
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
