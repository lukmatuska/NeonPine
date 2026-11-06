"""Minimal HID feature-report access without extra packages.

Linux:   /dev/hidraw* with the HIDIOC[GS]FEATURE ioctls (needs the udev rule in firmware/tools/).
Windows: hid.dll / setupapi.dll through ctypes (HID devices need no driver).
Other:   the `hid` module (pip install hidapi), if it is installed.

Every report buffer starts with the report ID, like hidapi.
"""
import os
import sys
from dataclasses import dataclass


class HidError(OSError):
    pass


@dataclass
class DeviceInfo:
    path: str
    vid: int
    pid: int
    serial: str = ""
    product: str = ""


# ---- Linux -------------------------------------------------------------------------------------

if sys.platform.startswith("linux"):
    import fcntl
    import glob

    def _ioc(nr, size):
        return (3 << 30) | (size << 16) | (ord("H") << 8) | nr  # _IOC(_IOC_READ|_IOC_WRITE, 'H', nr, size)

    def enumerate_devices(vid, pid):
        found = []
        for d in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
            try:
                with open(os.path.join(d, "device/uevent")) as f:
                    ev = dict(line.strip().split("=", 1) for line in f if "=" in line)
            except OSError:
                continue
            hid_id = ev.get("HID_ID", "").split(":")
            if len(hid_id) != 3:
                continue
            if int(hid_id[1], 16) == vid and int(hid_id[2], 16) == pid:
                found.append(DeviceInfo("/dev/" + os.path.basename(d), vid, pid, ev.get("HID_UNIQ", ""), ev.get("HID_NAME", "")))
        return found

    class HidDevice:
        def __init__(self, info):
            self.info = info
            try:
                self.fd = os.open(info.path, os.O_RDWR)
            except PermissionError as e:
                raise PermissionError(e.errno, "no access to %s - install firmware/tools/99-neonpine.rules (udev) and replug" % info.path)
            except OSError as e:
                raise HidError(e.errno, "can't open %s: %s" % (info.path, e.strerror))

        def close(self):
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None

        def set_feature(self, data):
            buf = bytearray(data)
            try:
                fcntl.ioctl(self.fd, _ioc(0x06, len(buf)), buf)
            except OSError as e:
                raise HidError(e.errno, "set feature 0x%02x: %s" % (buf[0], e.strerror))

        def get_feature(self, report_id, size):
            buf = bytearray(size)
            buf[0] = report_id
            try:
                n = fcntl.ioctl(self.fd, _ioc(0x07, size), buf)
            except OSError as e:
                raise HidError(e.errno, "get feature 0x%02x: %s" % (report_id, e.strerror))
            return bytes(buf[:n]) if 0 < n <= size else bytes(buf)

# ---- Windows -----------------------------------------------------------------------------------

elif sys.platform == "win32":
    import ctypes
    from ctypes import wintypes as wt

    _hid = ctypes.WinDLL("hid.dll", use_last_error=True)
    _setupapi = ctypes.WinDLL("setupapi.dll", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

    class _GUID(ctypes.Structure):
        _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class _SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("InterfaceClassGuid", _GUID), ("Flags", wt.DWORD), ("Reserved", ctypes.c_size_t)]

    class _HIDD_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Size", wt.ULONG), ("VendorID", wt.USHORT), ("ProductID", wt.USHORT), ("VersionNumber", wt.USHORT)]

    class _HIDP_CAPS(ctypes.Structure):
        _fields_ = [("Usage", wt.USHORT), ("UsagePage", wt.USHORT), ("InputReportByteLength", wt.USHORT),
                    ("OutputReportByteLength", wt.USHORT), ("FeatureReportByteLength", wt.USHORT),
                    ("Reserved", wt.USHORT * 17), ("NumberLinkCollectionNodes", wt.USHORT),
                    ("NumberInputButtonCaps", wt.USHORT), ("NumberInputValueCaps", wt.USHORT),
                    ("NumberInputDataIndices", wt.USHORT), ("NumberOutputButtonCaps", wt.USHORT),
                    ("NumberOutputValueCaps", wt.USHORT), ("NumberOutputDataIndices", wt.USHORT),
                    ("NumberFeatureButtonCaps", wt.USHORT), ("NumberFeatureValueCaps", wt.USHORT),
                    ("NumberFeatureDataIndices", wt.USHORT)]

    _INVALID_HANDLE = ctypes.c_void_p(-1).value
    _GENERIC_READ, _GENERIC_WRITE = 0x80000000, 0x40000000
    _FILE_SHARE_RW, _OPEN_EXISTING = 0x3, 3
    _DIGCF_PRESENT, _DIGCF_DEVICEINTERFACE = 0x2, 0x10

    _hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(_GUID)]
    _hid.HidD_GetAttributes.argtypes = [wt.HANDLE, ctypes.POINTER(_HIDD_ATTRIBUTES)]
    _hid.HidD_GetAttributes.restype = wt.BOOLEAN
    _hid.HidD_GetSerialNumberString.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
    _hid.HidD_GetSerialNumberString.restype = wt.BOOLEAN
    _hid.HidD_GetProductString.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
    _hid.HidD_GetProductString.restype = wt.BOOLEAN
    _hid.HidD_SetFeature.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
    _hid.HidD_SetFeature.restype = wt.BOOLEAN
    _hid.HidD_GetFeature.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
    _hid.HidD_GetFeature.restype = wt.BOOLEAN
    _hid.HidD_GetPreparsedData.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    _hid.HidD_GetPreparsedData.restype = wt.BOOLEAN
    _hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    _hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(_HIDP_CAPS)]
    _hid.HidP_GetCaps.restype = ctypes.c_long
    _setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(_GUID), wt.LPCWSTR, wt.HWND, wt.DWORD]
    _setupapi.SetupDiGetClassDevsW.restype = wt.HANDLE
    _setupapi.SetupDiEnumDeviceInterfaces.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(_GUID), wt.DWORD,
                                                      ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA)]
    _setupapi.SetupDiEnumDeviceInterfaces.restype = wt.BOOL
    _setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [wt.HANDLE, ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
                                                           ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
    _setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wt.BOOL
    _setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wt.HANDLE]
    _kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
    _kernel32.CreateFileW.restype = wt.HANDLE
    _kernel32.CloseHandle.argtypes = [wt.HANDLE]

    def _open_path(path, access):
        h = _kernel32.CreateFileW(path, access, _FILE_SHARE_RW, None, _OPEN_EXISTING, 0, None)
        return None if h in (None, _INVALID_HANDLE) else h

    def _hid_string(fn, h):
        buf = ctypes.create_unicode_buffer(128)
        return buf.value if fn(h, buf, ctypes.sizeof(buf)) else ""

    def enumerate_devices(vid, pid):
        guid = _GUID()
        _hid.HidD_GetHidGuid(ctypes.byref(guid))
        info = _setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, _DIGCF_PRESENT | _DIGCF_DEVICEINTERFACE)
        if info in (None, _INVALID_HANDLE):
            return []
        found = []
        try:
            index = 0
            while True:
                ifd = _SP_DEVICE_INTERFACE_DATA()
                ifd.cbSize = ctypes.sizeof(ifd)
                if not _setupapi.SetupDiEnumDeviceInterfaces(info, None, ctypes.byref(guid), index, ctypes.byref(ifd)):
                    break
                index += 1
                need = wt.DWORD()
                _setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(ifd), None, 0, ctypes.byref(need), None)
                buf = ctypes.create_string_buffer(need.value + 4)
                ctypes.cast(buf, ctypes.POINTER(wt.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
                if not _setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(ifd), buf, need, None, None):
                    continue
                path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
                h = _open_path(path, 0)  # attributes only need a handle without access rights
                if not h:
                    continue
                try:
                    attrs = _HIDD_ATTRIBUTES()
                    attrs.Size = ctypes.sizeof(attrs)
                    if _hid.HidD_GetAttributes(h, ctypes.byref(attrs)) and attrs.VendorID == vid and attrs.ProductID == pid:
                        found.append(DeviceInfo(path, vid, pid, _hid_string(_hid.HidD_GetSerialNumberString, h),
                                                _hid_string(_hid.HidD_GetProductString, h)))
                finally:
                    _kernel32.CloseHandle(h)
        finally:
            _setupapi.SetupDiDestroyDeviceInfoList(info)
        return found

    class HidDevice:
        def __init__(self, info):
            self.info = info
            self.h = _open_path(info.path, _GENERIC_READ | _GENERIC_WRITE) or _open_path(info.path, 0)
            if not self.h:
                raise HidError(ctypes.get_last_error(), "can't open the NeonPine HID device")
            # Windows wants feature buffers of at least the longest feature report.
            self.feature_len = 0
            pp = ctypes.c_void_p()
            if _hid.HidD_GetPreparsedData(self.h, ctypes.byref(pp)):
                caps = _HIDP_CAPS()
                if _hid.HidP_GetCaps(pp, ctypes.byref(caps)) == 0x110000:  # HIDP_STATUS_SUCCESS
                    self.feature_len = caps.FeatureReportByteLength
                _hid.HidD_FreePreparsedData(pp)

        def close(self):
            if self.h:
                _kernel32.CloseHandle(self.h)
                self.h = None

        def set_feature(self, data):
            n = max(len(data), self.feature_len)
            buf = (ctypes.c_ubyte * n).from_buffer_copy(bytes(data).ljust(n, b"\0"))
            if not _hid.HidD_SetFeature(self.h, buf, n):
                raise HidError(ctypes.get_last_error(), "set feature 0x%02x failed" % data[0])

        def get_feature(self, report_id, size):
            n = max(size, self.feature_len)
            buf = (ctypes.c_ubyte * n)()
            buf[0] = report_id
            if not _hid.HidD_GetFeature(self.h, buf, n):
                raise HidError(ctypes.get_last_error(), "get feature 0x%02x failed" % report_id)
            return bytes(buf)[:size]

# ---- anything else: hidapi ---------------------------------------------------------------------

else:
    try:
        import hid as _hidapi
    except ImportError:
        _hidapi = None

    def enumerate_devices(vid, pid):
        if not _hidapi:
            return []
        return [DeviceInfo(d["path"].decode() if isinstance(d["path"], bytes) else d["path"], vid, pid,
                           d.get("serial_number") or "", d.get("product_string") or "")
                for d in _hidapi.enumerate(vid, pid)]

    class HidDevice:
        def __init__(self, info):
            self.info = info
            self.dev = _hidapi.device()
            self.dev.open_path(info.path.encode())

        def close(self):
            self.dev.close()

        def set_feature(self, data):
            if self.dev.send_feature_report(bytes(data)) < 0:
                raise HidError(5, "set feature failed")

        def get_feature(self, report_id, size):
            r = self.dev.get_feature_report(report_id, size)
            if not r:
                raise HidError(5, "get feature failed")
            return bytes(r).ljust(size, b"\0")
