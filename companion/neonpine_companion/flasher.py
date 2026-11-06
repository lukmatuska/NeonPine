"""Firmware updates over USB through the rv003usb bootloader (1209:B003) - a Python port of minichlink's
"b003boot" programmer (firmware/deps/rv003usb/ch32fun/minichlink/pgm-b003fun.c, MIT, (c) CNLohr et al.).

The bootloader runs small RISC-V routines that the host writes into its scratchpad together with their
arguments (feature report 0xAA = 128 bytes or 0xAB = 1152 bytes); report 0xA8 (8 bytes) polls for "done".
The blobs below are minichlink's, byte for byte.
"""
import struct
import time

from . import device, hid_backend

FLASH_BASE = 0x08000000
FLASH_SIZE = 16384
STORE_OFFSET = 15360          # firmware v3+: settings / custom animations live above this
FLASH_STATR = 0x4002200C
FLASH_CTLR = 0x40022010
SECTOR = 64

WORD_WISE_READ_BLOB = bytes([
    0x23, 0xa0, 0x05, 0x00, 0x13, 0x07, 0x45, 0x03, 0x0c, 0x43, 0x50, 0x43,
    0x2e, 0x96, 0x21, 0x07, 0x94, 0x41, 0x14, 0xc3, 0x91, 0x05, 0x11, 0x07,
    0xe3, 0xcc, 0xc5, 0xfe, 0x93, 0x06, 0xf0, 0xff, 0x14, 0xc1, 0x82, 0x80,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])
WORD_WISE_WRITE_BLOB = bytes([
    0x23, 0xa0, 0x05, 0x00, 0x13, 0x07, 0x45, 0x03, 0x0c, 0x43, 0x50, 0x43,
    0x2e, 0x96, 0x21, 0x07, 0x14, 0x43, 0x94, 0xc1, 0x91, 0x05, 0x11, 0x07,
    0xe3, 0xcc, 0xc5, 0xfe, 0x93, 0x06, 0xf0, 0xff, 0x14, 0xc1, 0x82, 0x80,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])
HALT_WAIT_BLOB = bytes([
    0x81, 0x46, 0x94, 0xc1, 0xfd, 0x56, 0x14, 0xc1, 0x82, 0x80,
])
RUN_APP_BLOB = bytes([
    0xb7, 0xf5, 0xff, 0x1f, 0x93, 0x87, 0xc5, 0x77, 0x03, 0xa7, 0x07, 0x00,
    0x13, 0x57, 0x07, 0x01, 0x83, 0x96, 0x07, 0x00, 0x93, 0xc7, 0xc6, 0x77,
    0x63, 0x16, 0xf7, 0x00, 0x33, 0x87, 0xb6, 0x00, 0x67, 0x00, 0x07, 0x00,
    0xb7, 0x27, 0x02, 0x40, 0x93, 0x87, 0x87, 0x02, 0x37, 0x07, 0x67, 0x45,
    0x13, 0x07, 0x37, 0x12, 0x23, 0xa0, 0xe7, 0x00, 0xb7, 0x27, 0x02, 0x40,
    0x93, 0x87, 0x87, 0x02, 0x37, 0x97, 0xef, 0xcd, 0x13, 0x07, 0xb7, 0x9a,
    0x23, 0xa0, 0xe7, 0x00, 0xb7, 0x27, 0x02, 0x40, 0x93, 0x87, 0xc7, 0x00,
    0x23, 0xa0, 0x07, 0x00, 0xb7, 0x27, 0x02, 0x40, 0x93, 0x87, 0x07, 0x01,
    0x13, 0x07, 0x00, 0x08, 0x23, 0xa0, 0xe7, 0x00, 0xb7, 0xf7, 0x00, 0xe0,
    0x93, 0x87, 0x07, 0xd1, 0x37, 0x07, 0x00, 0x80, 0x23, 0xa0, 0xe7, 0x00,
])
WRITE_BLOCK_BIN = bytes([
    0x13, 0x07, 0x45, 0x05, 0x0c, 0x43, 0x5c, 0x43, 0x83, 0x12, 0x87, 0x00,
    0x03, 0x13, 0xa7, 0x00, 0x2e, 0x93, 0xb7, 0x06, 0x01, 0x00, 0xd4, 0xc3,
    0x33, 0x86, 0x55, 0x00, 0xb7, 0x06, 0x09, 0x00, 0xd4, 0xc3, 0x94, 0x41,
    0x54, 0x47, 0x94, 0xc1, 0xb7, 0x06, 0x05, 0x00, 0xd4, 0xc3, 0x94, 0x41,
    0x91, 0x05, 0x11, 0x07, 0xe3, 0xc8, 0xc5, 0xfe, 0xb7, 0x06, 0x01, 0x00,
    0x93, 0x86, 0x06, 0x04, 0xd4, 0xc3, 0x83, 0xa6, 0xc5, 0xff, 0xe3, 0xc9,
    0x65, 0xfc, 0xfd, 0x56, 0x14, 0xc1, 0x82, 0x80,
])
ERASE_BLOCK_BIN = bytes([
    0x13, 0x07, 0x85, 0x03, 0x0c, 0x43, 0x5c, 0x43, 0x83, 0x12, 0x87, 0x00,
    0x03, 0x16, 0xa7, 0x00, 0x2e, 0x96, 0xb7, 0x06, 0x02, 0x00, 0xd4, 0xc3,
    0x93, 0x86, 0x06, 0x04, 0x8c, 0xc7, 0xd4, 0xc3, 0x98, 0x43, 0x05, 0x8b,
    0x75, 0xff, 0x96, 0x95, 0xe3, 0xca, 0xc5, 0xfe, 0xfd, 0x56, 0x14, 0xc1,
    0x01, 0x00, 0x82, 0x80,
])
WRITE64_FLASH = bytes([
    0x13, 0x07, 0x45, 0x03, 0x0c, 0x43, 0x13, 0x86, 0x05, 0x04, 0x5c, 0x43,
    0x8c, 0xc7, 0x14, 0x47, 0x94, 0xc1, 0xb7, 0x06, 0x05, 0x00, 0xd4, 0xc3,
    0x94, 0x41, 0x91, 0x05, 0x11, 0x07, 0xe3, 0xc8, 0xc5, 0xfe, 0xc1, 0x66,
    0x93, 0x86, 0x06, 0x04, 0xd4, 0xc3, 0xfd, 0x56, 0x14, 0xc1, 0x82, 0x80,
])


class FlashError(Exception):
    pass


class Bootloader:
    def __init__(self, info, log=print):
        self.dev = hid_backend.HidDevice(info)
        self.log = log
        self.scratchpad = 128
        self.data_size = 0
        self.eight_byte = True
        self.long_op = 0
        self.buf = bytearray(1152)
        self.place = 4

    def close(self):
        self.dev.close()

    # -- minichlink ResetOp / WriteOpArb / WriteOp4 / CommitOp

    def _reset(self):
        self.buf = bytearray(max(self.scratchpad, 128))
        self.buf[0:4] = b"\xaa\x00\x00\x00"
        self.place = 4

    def _arb(self, data):
        self.buf[self.place:self.place + len(data)] = data
        self.place += len(data)

    def _op4(self, v):
        self._arb(struct.pack("<I", v & 0xFFFFFFFF))

    def _commit(self, send_len, recv_len, no_reply=False):
        feature, pad = 0xAA, 128
        if self.place + send_len <= 124:
            self.buf[124:128] = struct.pack("<I", 0x1234ABCD)
        elif self.place + send_len + 4 <= self.scratchpad:
            self.place = max(1024, self.place + send_len)
            k = self.place // 1024
            feature = 0xAA + k
            self.buf[124 + 1024 * k:128 + 1024 * k] = struct.pack("<I", 0x1234ABCD)
            self.buf[0] = feature
            pad = 128 + 1024 * k
        else:
            raise FlashError("command bigger than the bootloader's buffer")

        for attempt in range(11):
            try:
                self.dev.set_feature(bytes(self.buf[:pad]))
                break
            except OSError:
                if attempt == 10:
                    raise
                time.sleep(0.005)
        if no_reply:
            return b""

        retries_max, timeout_max = (100, 200) if self.long_op else (10, 20)
        if pad > 512:
            time.sleep(pad * 100e-6)
        elif self.long_op > 1:
            time.sleep(self.long_op * 100e-6)

        if recv_len:
            size = recv_len + self.place + 4
            if 128 < size < 128 + 1024:
                size = 128 + 1024
            feature, size = 0xAA + size // 1024, 128 + 1024 * (size // 1024)
        elif self.eight_byte:
            feature, size = 0xA8, 8
        else:
            feature, size = 0xAA, 128

        retries = timeout = 0
        while True:
            try:
                resp = self.dev.get_feature(feature, size)
            except OSError:
                retries += 1
                if retries > retries_max:
                    raise
                if self.long_op:
                    time.sleep(0.005)
                continue
            if resp[1] == 0xFF:
                break
            timeout += 1
            if timeout > timeout_max:
                raise FlashError("the bootloader didn't finish an operation")
            if self.long_op:
                time.sleep(0.005)
        self.long_op = 0
        return resp

    # -- operations

    def setup(self):
        self._reset()
        self._arb(HALT_WAIT_BLOB)
        self._commit(0, 0)  # stop the 5 s countdown into the application
        try:
            self.eight_byte = len(self.dev.get_feature(0xA8, 8)) == 8
        except OSError:
            self.eight_byte = False
        try:
            if len(self.dev.get_feature(0xAB, 1152)) == 1152:
                self.scratchpad, self.data_size = 1152, 1024
        except OSError:
            self.scratchpad, self.data_size = 128, 0

    def read(self, addr, size):
        out = bytearray()
        chunk = self.data_size or 64
        while size > 0:
            n = min(size, chunk)
            self._reset()
            self._arb(WORD_WISE_READ_BLOB)
            self._op4(addr)
            self._op4(n)
            resp = self._commit(0, n)
            out += resp[60:60 + n]
            addr += n
            size -= n
        return bytes(out)

    def read_word(self, addr):
        return struct.unpack("<I", self.read(addr, 4))[0]

    def write_word(self, addr, value):
        self._reset()
        self._arb(WORD_WISE_WRITE_BLOB)
        self._op4(addr)
        self._op4(4)
        self.buf[60:64] = struct.pack("<I", value)
        self._commit(4, 0)

    def unlock(self):
        if self.read_word(FLASH_CTLR) & 0x8080:
            for reg in (0x40022004, 0x40022008, 0x40022024):  # KEYR, OBKEYR, MODEKEYR
                self.write_word(reg, 0x45670123)
                self.write_word(reg, 0xCDEF89AB)
            if self.read_word(FLASH_CTLR) & 0x8080:
                raise FlashError("flash didn't unlock")
        if self.read_word(0x4002201C) & 2:
            raise FlashError("the chip is read-protected")

    def erase(self, addr, length):
        self._reset()
        self._arb(ERASE_BLOCK_BIN)
        self._op4(addr)
        self._op4(FLASH_STATR)
        self._op4(SECTOR | length << 16)
        self.long_op = length
        self._commit(0, 0)

    def write(self, addr, data, progress=None):
        if self.data_size:
            for pos in range(0, len(data), self.data_size):
                chunk = data[pos:pos + self.data_size]
                self._reset()
                self._arb(WRITE_BLOCK_BIN)
                self._op4(addr + pos)
                self._op4(FLASH_STATR)
                self._op4(SECTOR | len(chunk) << 16)
                self.buf[self.place:self.place + len(chunk)] = chunk
                self.long_op = 1
                self._commit(len(chunk), 0)
                if progress:
                    progress(pos + len(chunk), len(data))
        else:  # small HID buffer: 64-byte pages
            for pos in range(0, len(data), SECTOR):
                self.write_word(FLASH_CTLR, 0x00010000)            # CR_PAGE_PG
                self.write_word(FLASH_CTLR, 0x00010000 | 0x80000)  # | CR_BUF_RST
                self._reset()
                self._arb(WRITE64_FLASH)
                self._op4(addr + pos)
                self._op4(FLASH_STATR)
                self.buf[60:60 + SECTOR] = data[pos:pos + SECTOR]
                self.long_op = 1
                self._commit(SECTOR, 0)
                if progress:
                    progress(pos + SECTOR, len(data))

    def boot(self):
        self._reset()
        self._arb(RUN_APP_BLOB)
        self._commit(0, 0, no_reply=True)


def wait_for(find, timeout, cancel=lambda: False, poke=None):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cancel():
            return None
        found = find()
        if found:
            return found[0]
        if poke:
            poke()
        time.sleep(0.1)
    return None


def flash_firmware(image, log=print, progress=None, wait_s=8.0, cancel=lambda: False, allow_store_overwrite=False):
    """Write `image` (a .bin for 0x08000000) and start it. If the application is running it is asked to
    reboot into the bootloader first; otherwise this waits wait_s for one (plug the tree in now)."""
    image = bytes(image)
    if not image:
        raise FlashError("empty image")
    if len(image) > FLASH_SIZE:
        raise FlashError("the image is %d bytes, the chip has %d" % (len(image), FLASH_SIZE))
    if len(image) > STORE_OFFSET and not allow_store_overwrite:
        raise FlashError("the image (%d bytes) would overwrite the settings / custom animation store above %d bytes"
                         % (len(image), STORE_OFFSET))

    step = lambda text, frac: (log(text), progress and progress(text, frac))
    info = (device.find_bootloaders() or [None])[0]
    if not info:
        trees = device.find_trees()
        old = None
        if trees:
            step("Restarting the tree into its bootloader", 0.02)
            try:
                old = device.Tree(trees[0])
                old.reboot_to_bootloader()
            except OSError:
                old = None
        else:
            step("Waiting for the bootloader - plug the tree in now", 0.02)
        try:
            info = wait_for(device.find_bootloaders, wait_s, cancel, old.poke if old else None)
        finally:
            if old:
                try:
                    old.close()
                except OSError:
                    pass
        if not info:
            raise FlashError("the bootloader (1209:B003) didn't show up")
    for attempt in range(30):  # a fresh node belongs to root until udev has applied the rule
        try:
            bl = Bootloader(info, log)
            break
        except PermissionError:
            if attempt == 29:
                raise
            time.sleep(0.05)
    try:
        step("Connecting to the bootloader", 0.05)
        bl.setup()
        bl.unlock()
        padded = image.ljust(-(-len(image) // SECTOR) * SECTOR, b"\0")
        step("Erasing %d bytes" % len(padded), 0.1)
        bl.erase(FLASH_BASE, len(padded))
        step("Writing", 0.15)
        bl.write(FLASH_BASE, padded, lambda done, total: progress and progress("Writing %d / %d bytes" % (done, total), 0.15 + 0.6 * done / total))
        step("Verifying", 0.8)
        back = bl.read(FLASH_BASE, len(padded))
        if back != padded:
            bad = next(i for i in range(len(padded)) if back[i] != padded[i])
            raise FlashError("verify failed at 0x%04x - the old firmware is gone; flash again (the bootloader stays)" % bad)
        step("Starting the new firmware", 0.9)
        bl.boot()
    finally:
        bl.close()

    if wait_for(device.find_trees, 8.0, cancel):
        step("Done - the tree is running the new firmware", 1.0)
        return True
    step("Written and verified, but the tree didn't come back on USB - replug it", 1.0)
    return False
