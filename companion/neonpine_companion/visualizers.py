"""Live sources that drive the tree from the PC: music (an input, or what the computer plays) and CPU load."""
import array
import math
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal

from . import audio_capture
from .custom import LAMP_X, ROW
from .platform_utils import CpuMeter

try:
    from PySide6.QtMultimedia import QAudioFormat, QAudioSource
except ImportError:  # Qt without multimedia: only the native backends (audio_capture lists no "qt" devices then)
    pass

TIERS = [[i for i in range(10) if ROW[i] == r] for r in range(4)]  # star .. bottom


def _goertzel(samples, rate, freq):
    k = 2 * math.cos(2 * math.pi * freq / rate)
    s1 = s2 = 0.0
    for x in samples:
        s1, s2 = x + k * s1 - s2, s1
    return math.sqrt(max(0.0, s1 * s1 + s2 * s2 - k * s1 * s2)) / len(samples)


class MusicSource(QObject):
    """Audio levels (an input, or what the computer plays) -> tree frames. Styles: 'meter' (fills up from the bottom),
    'bands' (bass at the bottom .. treble at the star), 'pulse' (whole tree on the beat)."""
    level = Signal(float)

    # bottom tier .. star: (window length at 16 kHz, frequencies). The frequencies sit one bin (rate / length) apart, so
    # a tone anywhere in the band counts; higher bands use shorter windows (wider bins), averaged over the whole frame.
    BANDS = ((512, (45, 75, 105, 135)),
             (256, (180, 250, 320, 390, 460, 530)),
             (96, (650, 820, 990, 1160, 1330, 1500, 1670, 1840, 2010, 2180)),
             (48, (2500, 2830, 3170, 3500, 3830, 4170, 4500, 4830, 5170, 5500, 5830, 6170, 6500, 6830, 7170)))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.src = None  # Qt Multimedia
        self.io = None
        self.cap = None  # native capture (audio_capture)
        self.lock = threading.Lock()
        self.buf = array.array("h")
        self.last_push = 0.0
        self.rate = 16000
        self.style = "bands"
        self.gain = 1.0
        self.env = [0.0] * 4
        self.peak = [1e-3] * 4
        self.rms_env = 0.0
        self.rms_peak = 1e-3
        self.beat = 0.0
        self._hann = {}

    @staticmethod
    def inputs():
        return audio_capture.list_devices()

    def start(self, spec=None):
        self.stop()
        if spec is None:
            devs = self.inputs()
            if not devs:
                raise RuntimeError("No audio device found")
            spec = devs[0][1]
        if spec[0] != "qt":
            self.cap = audio_capture.open_capture(spec, self._push)
            self.rate = self.cap.rate
            return
        dev = spec[1]
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.Int16)
        if not dev.isFormatSupported(fmt):
            fmt = dev.preferredFormat()
            fmt.setSampleFormat(QAudioFormat.Int16)
        self.rate = fmt.sampleRate()
        self.channels = fmt.channelCount()
        self.src = QAudioSource(dev, fmt, self)
        self.io = self.src.start()
        if self.io is None:
            raise RuntimeError("couldn't open the audio input")
        self.io.readyRead.connect(self._read)

    def stop(self):
        if self.cap:
            self.cap.stop()
        if self.src:
            self.src.stop()
            self.src.deleteLater()
        self.src = self.io = self.cap = None
        with self.lock:
            self.buf = array.array("h")

    def _read(self):
        data = bytes(self.io.readAll().data())
        a = array.array("h")
        a.frombytes(data[:len(data) // 2 * 2])
        if getattr(self, "channels", 1) > 1:
            a = a[::self.channels]
        self._push(a)

    def _push(self, a):  # GUI thread (Qt) or the capture thread (native)
        with self.lock:
            self.buf.extend(a)
            if len(self.buf) > self.rate:
                del self.buf[:len(self.buf) - self.rate]
            self.last_push = time.monotonic()

    def frame(self):
        with self.lock:
            if time.monotonic() - self.last_push > 0.2:  # loopback sends nothing while nothing plays
                self.buf = array.array("h")
            n = min(len(self.buf), max(256, self.rate // 30))
            tail = self.buf[-n:]
        if n < 128:
            self.level.emit(0.0)
            return [0.0] * 10, [0.0] * 10
        rate = self.rate
        step = max(1, rate // 16000)  # average down to ~16 kHz: keeps the Goertzel cost low
        if step > 1:
            tail = [sum(tail[i:i + step]) / step for i in range(0, len(tail) - step + 1, step)]
            rate //= step
        win = [x / 32768.0 for x in tail]
        rms = math.sqrt(sum(x * x for x in win) / len(win)) * self.gain
        bands = []
        for size, freqs in self.BANDS:
            size = min(len(win), size * rate // 16000)
            hann = self._hann.get(size)
            if hann is None:  # 2x Hann: unit gain
                hann = self._hann[size] = [1 - math.cos(2 * math.pi * i / (size - 1)) for i in range(size)]
            freqs = [f for f in freqs if f < rate / 2]
            p = 0.0
            chunks = range(len(win) - size, -1, -size)  # newest first, at least one
            for end in chunks:
                w = [x * h for x, h in zip(win[end:end + size], hann)]
                p += sum(_goertzel(w, rate, f) ** 2 for f in freqs)
            bands.append(math.sqrt(p / (len(chunks) * max(1, len(freqs)))) * self.gain * 8)
        # fast attack, slow release, auto-scaling peaks
        self.rms_env = rms if rms > self.rms_env else self.rms_env * 0.85 + rms * 0.15
        self.rms_peak = max(self.rms_env, self.rms_peak * 0.995, 0.02)
        for k, b in enumerate(bands):
            self.env[k] = b if b > self.env[k] else self.env[k] * 0.8 + b * 0.2
            self.peak[k] = max(self.env[k], self.peak[k] * 0.995, 0.004)
        top = max(self.peak)  # a band far below the loudest one stays dark: no blowing up leakage to full scale
        self.peak = [max(p, top * 0.08) for p in self.peak]
        loud = self.rms_env / self.rms_peak
        self.level.emit(loud)
        left, right = [0.0] * 10, [0.0] * 10
        if self.style == "meter":
            fill = loud * 4.0
            for r, tier in enumerate(reversed(TIERS)):
                v = max(0.0, min(1.0, fill - r))
                for i in tier:
                    left[i] = right[i] = v
        elif self.style == "pulse":
            self.beat = max(self.beat * 0.82, 1.0 if self.env[0] / self.peak[0] > 0.8 else 0.0)
            for i in range(10):
                left[i] = right[i] = 0.08 + 0.92 * max(self.beat, loud * 0.5)
        else:  # bands
            for r, tier in enumerate(reversed(TIERS)):  # bottom tier = bass
                v = self.env[r] / self.peak[r]
                v = max(0.0, min(1.0, (v - 0.15) / 0.85))
                for i in tier:
                    left[i] = v
                    right[i] = max(0.0, v - 0.25) / 0.75
        return left, right


class CpuSource:
    """CPU load fills the tree from the bottom; the right electrodes trail the left ones."""

    def __init__(self):
        self.meter = CpuMeter()
        self.value = 0.0
        self.last = 0.0
        self.load = 0.0

    def frame(self):
        now = time.monotonic()
        if now - self.last > 0.5:
            self.last = now
            self.load = self.meter.load()
        self.value += (self.load - self.value) * 0.15
        fill = self.value * 4.0
        left, right = [0.04] * 10, [0.04] * 10
        for r, tier in enumerate(reversed(TIERS)):
            v = max(0.04, min(1.0, fill - r))
            for i in sorted(tier, key=lambda i: LAMP_X[i]):
                left[i] = v
                right[i] = max(0.04, min(1.0, fill - r - 0.35))
        return left, right


class LiveDriver(QObject):
    """Ticks the active source at ~30 fps and hands frames to the device + the preview."""
    frame = Signal(list, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def run(self, source):
        self.source = source
        if source:
            self.timer.start(33)
        else:
            self.timer.stop()

    def _tick(self):
        if self.source:
            left, right = self.source.frame()
            self.frame.emit(list(left), list(right))
