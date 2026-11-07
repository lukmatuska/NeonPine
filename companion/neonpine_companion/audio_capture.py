"""Audio capture for the music visualizer, including what the computer is playing.

Qt Multimedia only lists real inputs (its PulseAudio backend drops monitor sources, and it can't do WASAPI loopback),
so besides Qt this has two small native backends with no extra packages:
  * Linux: PulseAudio / PipeWire (pipewire-pulse) through libpulse + libpulse-simple: every source, monitors included
  * Windows: WASAPI loopback capture of each output device, through ctypes COM
A device is a (label, spec) pair; spec is ("qt", QAudioDevice), ("pulse", source name) or ("wasapi", endpoint id | None).
Captures call push(array('h')) with mono int16 samples from their own thread.
"""
import array
import ctypes
import sys
import threading
import time
import uuid
from ctypes import POINTER, Structure, byref, c_char_p, c_int, c_uint8, c_uint16, c_uint32, c_void_p

try:
    from PySide6.QtMultimedia import QMediaDevices
    HAVE_QT_AUDIO = True
except ImportError:
    HAVE_QT_AUDIO = False

RATE = 16000


def list_devices():
    """Inputs for the music visualizer, the computer's own output (monitor / loopback) first."""
    devs = []
    if sys.platform.startswith("linux"):
        try:
            devs = _pulse_devices()
        except OSError:
            devs = []  # no libpulse or no sound server: plain ALSA through Qt
        if devs:
            return devs
    elif sys.platform == "win32":
        try:
            devs = _wasapi_devices()
        except OSError:
            devs = []
    if HAVE_QT_AUDIO:
        devs += [(d.description(), ("qt", d)) for d in QMediaDevices.audioInputs()]
    return devs


def open_capture(spec, push):
    """Starts a native capture for a ("pulse" | "wasapi", ...) spec; returns an object with .rate and .stop()."""
    kind, arg = spec
    cap = {"pulse": PulseCapture, "wasapi": WasapiLoopback}[kind](arg, push)
    cap.start()
    return cap


class _Capture:
    rate = RATE

    def __init__(self, arg, push):
        self.arg = arg
        self.push = push
        self.running = False
        self.error = None
        self.thread = None
        self._ready = threading.Event()

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._guarded, daemon=True, name=type(self).__name__)
        self.thread.start()
        self._ready.wait(3.0)
        if self.error:
            self.thread.join(0.5)
            raise RuntimeError("couldn't open the audio device: %s" % self.error)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(0.5)  # a read in progress returns within a fragment (~20 ms)
        self.thread = None

    def _guarded(self):
        try:
            self._run()
        except Exception as e:  # noqa: BLE001 - reported to start(), or ends the capture quietly
            self.error = str(e) or type(e).__name__
        finally:
            self._ready.set()


# ---------------------------------------------------------------------------------------------------------------------
# PulseAudio / PipeWire

class _PaSourceInfo(Structure):  # just the leading fields of pa_source_info
    _fields_ = [("name", c_char_p), ("index", c_uint32), ("description", c_char_p)]


class _PaSampleSpec(Structure):
    _fields_ = [("format", c_int), ("rate", c_uint32), ("channels", c_uint8)]


class _PaBufferAttr(Structure):
    _fields_ = [("maxlength", c_uint32), ("tlength", c_uint32), ("prebuf", c_uint32), ("minreq", c_uint32),
                ("fragsize", c_uint32)]


_PA_SOURCE_CB = ctypes.CFUNCTYPE(None, c_void_p, POINTER(_PaSourceInfo), c_int, c_void_p)
_pa = _pa_simple = None


def _libpulse():
    global _pa
    if _pa is None:
        lib = ctypes.CDLL("libpulse.so.0")
        for name, res, args in (
                ("pa_mainloop_new", c_void_p, []),
                ("pa_mainloop_get_api", c_void_p, [c_void_p]),
                ("pa_mainloop_iterate", c_int, [c_void_p, c_int, POINTER(c_int)]),
                ("pa_mainloop_free", None, [c_void_p]),
                ("pa_context_new", c_void_p, [c_void_p, c_char_p]),
                ("pa_context_connect", c_int, [c_void_p, c_char_p, c_int, c_void_p]),
                ("pa_context_get_state", c_int, [c_void_p]),
                ("pa_context_disconnect", None, [c_void_p]),
                ("pa_context_unref", None, [c_void_p]),
                ("pa_context_get_source_info_list", c_void_p, [c_void_p, _PA_SOURCE_CB, c_void_p]),
                ("pa_operation_get_state", c_int, [c_void_p]),
                ("pa_operation_unref", None, [c_void_p])):
            f = getattr(lib, name)
            f.restype, f.argtypes = res, args
        _pa = lib
    return _pa


def _pulse_devices():
    pa = _libpulse()
    ml = pa.pa_mainloop_new()
    ctx = pa.pa_context_new(pa.pa_mainloop_get_api(ml), b"NeonPine Companion")
    sources = []

    @_PA_SOURCE_CB
    def on_source(_c, info, eol, _u):
        if not eol and info:
            i = info.contents
            sources.append((i.name.decode(errors="replace"), (i.description or i.name).decode(errors="replace")))

    def spin(done, timeout=2.0):
        end = time.monotonic() + timeout
        while not done() and time.monotonic() < end:
            if pa.pa_mainloop_iterate(ml, 0, None) == 0:
                time.sleep(0.003)
        return done()

    try:
        if pa.pa_context_connect(ctx, None, 1, None) < 0:  # 1 = PA_CONTEXT_NOAUTOSPAWN
            return []
        if not spin(lambda: pa.pa_context_get_state(ctx) in (4, 5, 6)) or pa.pa_context_get_state(ctx) != 4:
            return []  # 4 READY, 5 FAILED, 6 TERMINATED
        op = pa.pa_context_get_source_info_list(ctx, on_source, None)
        if op:
            spin(lambda: pa.pa_operation_get_state(op) != 0)  # 0 RUNNING
            pa.pa_operation_unref(op)
        pa.pa_context_disconnect(ctx)
    finally:
        pa.pa_context_unref(ctx)
        pa.pa_mainloop_free(ml)
    if not sources:
        return []
    monitors = [(desc, ("pulse", name)) for name, desc in sources if name.endswith(".monitor")]
    inputs = [(desc, ("pulse", name)) for name, desc in sources if not name.endswith(".monitor")]
    return [("What's playing on this computer (default output)", ("pulse", "@DEFAULT_MONITOR@"))] + monitors + inputs


class PulseCapture(_Capture):
    def _run(self):
        global _pa_simple
        if _pa_simple is None:
            lib = ctypes.CDLL("libpulse-simple.so.0")
            lib.pa_simple_new.restype = c_void_p
            lib.pa_simple_new.argtypes = [c_char_p, c_char_p, c_int, c_char_p, c_char_p, POINTER(_PaSampleSpec),
                                          c_void_p, POINTER(_PaBufferAttr), POINTER(c_int)]
            lib.pa_simple_read.restype = c_int
            lib.pa_simple_read.argtypes = [c_void_p, c_void_p, ctypes.c_size_t, POINTER(c_int)]
            lib.pa_simple_free.restype = None
            lib.pa_simple_free.argtypes = [c_void_p]
            _pa_simple = lib
        lib = _pa_simple
        frag = RATE // 50 * 2  # 20 ms of mono s16
        spec = _PaSampleSpec(3, RATE, 1)  # PA_SAMPLE_S16LE; the server converts and resamples
        attr = _PaBufferAttr(0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, frag)
        err = c_int(0)
        s = lib.pa_simple_new(None, b"NeonPine Companion", 2, self.arg.encode(), b"Tree music visualizer",
                              byref(spec), None, byref(attr), byref(err))  # 2 = PA_STREAM_RECORD
        if not s:
            raise OSError("PulseAudio error %d" % err.value)
        self._ready.set()
        buf = ctypes.create_string_buffer(frag)
        try:
            while self.running:
                if lib.pa_simple_read(s, buf, frag, byref(err)) < 0:
                    raise OSError("PulseAudio read error %d" % err.value)
                a = array.array("h")
                a.frombytes(buf.raw)
                if sys.byteorder == "big":
                    a.byteswap()
                self.push(a)
        finally:
            lib.pa_simple_free(s)


# ---------------------------------------------------------------------------------------------------------------------
# Windows: WASAPI loopback

class _GUID(Structure):
    _fields_ = [("Data1", c_uint32), ("Data2", c_uint16), ("Data3", c_uint16), ("Data4", ctypes.c_ubyte * 8)]


def _guid(s):
    return _GUID.from_buffer_copy(uuid.UUID(s).bytes_le)


class _PropKey(Structure):
    _fields_ = [("fmtid", _GUID), ("pid", c_uint32)]


class _PropVariant(Structure):  # 16 bytes on 32-bit, 24 on 64-bit, like PROPVARIANT
    _fields_ = [("vt", c_uint16), ("r1", c_uint16), ("r2", c_uint16), ("r3", c_uint16), ("val", c_void_p),
                ("pad", c_void_p)]


class _WaveFormatEx(Structure):
    _pack_ = 1
    _fields_ = [("wFormatTag", c_uint16), ("nChannels", c_uint16), ("nSamplesPerSec", c_uint32),
                ("nAvgBytesPerSec", c_uint32), ("nBlockAlign", c_uint16), ("wBitsPerSample", c_uint16),
                ("cbSize", c_uint16)]


CLSID_MMDeviceEnumerator = "BCDE0395-E52F-467C-8E3D-C4579291692E"
IID_IMMDeviceEnumerator = "A95664D2-9614-4F35-A746-DE8DB63617E6"
IID_IAudioClient = "1CB9AD4C-DBFA-4C32-B178-C2F568A703B2"
IID_IAudioCaptureClient = "C8ADBD64-E71E-48A0-A4DE-185C395CD317"
PKEY_Device_FriendlyName = ("A45C254E-DF1C-4EFD-8020-67D146A850E0", 14)
E_RENDER, E_CONSOLE, DEVICE_STATE_ACTIVE, CLSCTX_ALL, VT_LPWSTR = 0, 0, 1, 23, 31
AUDCLNT_STREAMFLAGS_LOOPBACK, AUDCLNT_BUFFERFLAGS_SILENT = 0x00020000, 0x2


def _com(obj, index, *argtypes):
    """Method `index` of the vtable of COM object `obj` (a c_void_p); a failing HRESULT raises OSError."""
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)(vtbl[index])
    return lambda *a: fn(obj, *a)


def _release(obj):
    if obj and obj.value:
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
        ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(vtbl[2])(obj)


class _ComApartment:
    def __enter__(self):
        try:
            ctypes.oledll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
            self.ok = True
        except OSError:  # already initialized differently on this thread: COM is usable anyway
            self.ok = False
        return self

    def __exit__(self, *exc):
        if self.ok:
            ctypes.windll.ole32.CoUninitialize()


def _enumerator():
    obj = c_void_p()
    ctypes.oledll.ole32.CoCreateInstance(byref(_guid(CLSID_MMDeviceEnumerator)), None, CLSCTX_ALL,
                                         byref(_guid(IID_IMMDeviceEnumerator)), byref(obj))
    return obj


def _device_info(dev):
    """(id, friendly name) of an IMMDevice."""
    p = c_void_p()
    _com(dev, 5, POINTER(c_void_p))(byref(p))  # IMMDevice::GetId
    dev_id = ctypes.wstring_at(p.value)
    ctypes.windll.ole32.CoTaskMemFree(p)
    name = dev_id
    store = c_void_p()
    try:
        _com(dev, 4, c_uint32, POINTER(c_void_p))(0, byref(store))  # IMMDevice::OpenPropertyStore(STGM_READ)
        key = _PropKey(_guid(PKEY_Device_FriendlyName[0]), PKEY_Device_FriendlyName[1])
        pv = _PropVariant()
        _com(store, 5, POINTER(_PropKey), POINTER(_PropVariant))(byref(key), byref(pv))  # IPropertyStore::GetValue
        if pv.vt == VT_LPWSTR and pv.val:
            name = ctypes.wstring_at(pv.val)
        ctypes.oledll.ole32.PropVariantClear(byref(pv))
    except OSError:
        pass
    finally:
        _release(store)
    return dev_id, name


def _wasapi_devices():
    result = []

    def work():  # in a thread of its own, away from Qt's single-threaded apartment
        with _ComApartment():
            en = coll = None
            try:
                en = _enumerator()
                coll = c_void_p()
                _com(en, 3, c_int, c_uint32, POINTER(c_void_p))(E_RENDER, DEVICE_STATE_ACTIVE, byref(coll))
                n = c_uint32()
                _com(coll, 3, POINTER(c_uint32))(byref(n))  # IMMDeviceCollection::GetCount
                for k in range(n.value):
                    dev = c_void_p()
                    _com(coll, 4, c_uint32, POINTER(c_void_p))(k, byref(dev))  # ::Item
                    try:
                        result.append(_device_info(dev))
                    finally:
                        _release(dev)
            except OSError:
                pass
            finally:
                _release(coll)
                _release(en)

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(3.0)
    devs = [("What's playing on this computer (default output)", ("wasapi", None))]
    devs += [("What's playing on %s" % name, ("wasapi", dev_id)) for dev_id, name in result]
    return devs


class WasapiLoopback(_Capture):
    def _run(self):
        with _ComApartment():
            en = dev = client = cap = None
            fmt = c_void_p()
            try:
                en = _enumerator()
                dev = c_void_p()
                if self.arg is None:
                    _com(en, 4, c_int, c_int, POINTER(c_void_p))(E_RENDER, E_CONSOLE, byref(dev))
                else:
                    _com(en, 5, ctypes.c_wchar_p, POINTER(c_void_p))(self.arg, byref(dev))
                client = c_void_p()
                _com(dev, 3, POINTER(_GUID), c_uint32, c_void_p, POINTER(c_void_p))(  # IMMDevice::Activate
                    byref(_guid(IID_IAudioClient)), CLSCTX_ALL, None, byref(client))
                _com(client, 8, POINTER(c_void_p))(byref(fmt))  # IAudioClient::GetMixFormat
                wf = _WaveFormatEx.from_address(fmt.value)
                kind = wf.wFormatTag
                if kind == 0xFFFE:  # WAVE_FORMAT_EXTENSIBLE: the subformat GUID's Data1 is the format tag
                    kind = c_uint32.from_address(fmt.value + 24).value
                ch, bits, block = wf.nChannels, wf.wBitsPerSample, wf.nBlockAlign
                if (kind, bits) not in ((3, 32), (1, 16), (1, 32)):
                    raise OSError("unsupported mix format (tag %d, %d bit)" % (kind, bits))
                step = max(1, wf.nSamplesPerSec // RATE)  # decimate to roughly 16 kHz by averaging
                self.rate = wf.nSamplesPerSec // step
                _com(client, 3, c_int, c_uint32, ctypes.c_longlong, ctypes.c_longlong, c_void_p, c_void_p)(
                    0, AUDCLNT_STREAMFLAGS_LOOPBACK, 2000000, 0, fmt, None)  # shared mode, 200 ms buffer
                cap = c_void_p()
                _com(client, 14, POINTER(_GUID), POINTER(c_void_p))(byref(_guid(IID_IAudioCaptureClient)), byref(cap))
                next_size = _com(cap, 5, POINTER(c_uint32))
                get_buffer = _com(cap, 3, POINTER(c_void_p), POINTER(c_uint32), POINTER(c_uint32), c_void_p, c_void_p)
                release_buffer = _com(cap, 4, c_uint32)
                _com(client, 10)()  # IAudioClient::Start
                self._ready.set()
                typecode, scale = {(3, 32): ("f", 32767.0), (1, 16): ("h", 1.0), (1, 32): ("i", 1 / 65536)}[(kind, bits)]
                group = ch * step
                carry = []
                n, data, frames, flags = c_uint32(), c_void_p(), c_uint32(), c_uint32()
                while self.running:
                    time.sleep(0.01)
                    while self.running:
                        next_size(byref(n))
                        if not n.value:
                            break
                        get_buffer(byref(data), byref(frames), byref(flags), None, None)
                        size = frames.value * block
                        if flags.value & AUDCLNT_BUFFERFLAGS_SILENT or not data.value:
                            raw = bytes(size)
                        else:
                            raw = ctypes.string_at(data.value, size)
                        release_buffer(frames.value)
                        a = array.array(typecode)
                        a.frombytes(raw)
                        v = carry + a.tolist() if carry else a.tolist()
                        cut = len(v) // group * group
                        carry = v[cut:]
                        k = scale / group
                        self.push(array.array("h", (max(-32768, min(32767, int(sum(v[i:i + group]) * k)))
                                                    for i in range(0, cut, group))))
                _com(client, 11)()  # IAudioClient::Stop
            finally:
                _release(cap)
                _release(client)
                if fmt.value:
                    ctypes.windll.ole32.CoTaskMemFree(fmt)
                _release(dev)
                _release(en)
