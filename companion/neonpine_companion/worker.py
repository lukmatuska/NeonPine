"""USB lives in its own thread: connecting, status polling, jobs from the UI, live frames, flashing."""
import errno
import threading
import time
import traceback

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot

from . import custom, device, flasher


class TreeInfo:
    """What the UI knows about the connected tree."""

    def __init__(self, path, status, config, customs, blob_ok):
        self.path = path
        self.status = status
        self.config = config
        self.customs = customs
        self.blob_ok = blob_ok


class DeviceWorker(QObject):
    connected = Signal(object)          # TreeInfo
    disconnected = Signal(str)
    statusUpdated = Signal(object)      # device.Status
    treesFound = Signal(list)           # [DeviceInfo] when more than one is plugged in
    jobDone = Signal(object, object, object)
    flashProgress = Signal(str, float)
    flashDone = Signal(bool, str)

    POLL_MS = 250

    def __init__(self):
        super().__init__()
        self.tree = None
        self.preferred = None           # hidraw path / device path to prefer
        self._live = None
        self._live_lock = threading.Lock()
        self.flashing = False
        self.cancel_flash = False
        self.live_fps = 25
        self._last_live = 0.0
        self._last_scan = 0.0
        self._poll_div = 0

    @Slot()
    def start(self):
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(self.POLL_MS)
        self.live_timer = QTimer(self)
        self.live_timer.setTimerType(Qt.PreciseTimer)
        self.live_timer.timeout.connect(self._send_live)
        self.live_timer.start(10)

    @Slot()
    def stop(self):
        self.poll_timer.stop()
        self.live_timer.stop()
        self._drop("closing")

    # -- connection

    def _drop(self, reason):
        if self.tree:
            try:
                self.tree.close()
            except OSError:
                pass
            self.tree = None
            self.disconnected.emit(reason)

    def _connect(self, info):
        try:
            t = device.Tree(info)
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EPERM):
                self.disconnected.emit(str(e))
            return
        try:
            cfg = t.read_config() if t.status.has_store else None
            blob = t.read_blob() if t.status.has_store else b""
            customs = custom.unpack_blob(blob) if blob else []
            self.tree = t
            self.connected.emit(TreeInfo(info.path, t.status, cfg, customs, bool(blob)))
        except (OSError, device.DeviceError) as e:
            try:
                t.close()
            except OSError:
                pass
            self.disconnected.emit("couldn't read the tree: %s" % e)

    def _poll(self):
        if self.flashing:
            return
        if not self.tree:
            now = time.monotonic()
            if now - self._last_scan < 0.9:
                return
            self._last_scan = now
            trees = device.find_trees()
            if len(trees) > 1:
                self.treesFound.emit(trees)
            if trees:
                pick = next((t for t in trees if t.path == self.preferred), trees[0])
                self._connect(pick)
            return
        self._poll_div += 1
        if self._live is not None and self._poll_div % 3:
            return  # stream first: fewer status reads while live frames go out
        try:
            self.statusUpdated.emit(self.tree.read_status())
        except OSError as e:
            self._drop("unplugged" if e.errno in (errno.ENODEV, errno.ENOENT, errno.EIO) else str(e))

    @Slot(str)
    def select(self, path):
        self.preferred = path
        if self.tree and self.tree.info.path != path:
            self._drop("switching trees")

    # -- jobs: fn(tree) runs here, the result goes back to the UI

    @Slot(object, object)
    def run_job(self, fn, callbacks):
        if self.flashing:
            self.jobDone.emit(callbacks, None, RuntimeError("busy flashing"))
            return
        if not self.tree:
            self.jobDone.emit(callbacks, None, RuntimeError("no tree connected"))
            return
        try:
            r = fn(self.tree)
            self.jobDone.emit(callbacks, r, None)
        except Exception as e:  # noqa: BLE001 - reported to the UI
            if isinstance(e, OSError) and e.errno in (errno.ENODEV, errno.ENOENT):
                self._drop("unplugged")
            if not isinstance(e, (OSError, device.DeviceError, ValueError)):
                traceback.print_exc()
            self.jobDone.emit(callbacks, None, e)

    # -- live frames: the UI sets the latest frame, this sends it at live_fps

    def set_live(self, frame):
        with self._live_lock:
            self._live = frame

    def _send_live(self):
        if self.flashing or not self.tree:
            return
        with self._live_lock:
            frame = self._live
        if frame is None:
            return
        now = time.monotonic()
        if now - self._last_live < 1.0 / self.live_fps:
            return
        self._last_live = now
        try:
            self.tree.live_frame(*frame)
        except OSError as e:
            if e.errno in (errno.ENODEV, errno.ENOENT):
                self._drop("unplugged")

    # -- flashing

    @Slot(bytes, bool)
    def flash(self, image, allow_store_overwrite):
        self.flashing = True
        self.cancel_flash = False
        if self.tree:
            try:
                self.tree.close()
            except OSError:
                pass
            self.tree = None
            self.disconnected.emit("updating firmware")
        try:
            ok = flasher.flash_firmware(image, log=lambda s: None,
                                        progress=lambda text, frac: self.flashProgress.emit(text, frac),
                                        wait_s=12.0, cancel=lambda: self.cancel_flash,
                                        allow_store_overwrite=allow_store_overwrite)
            self.flashDone.emit(ok, "Firmware updated." if ok else "Written - replug the tree.")
        except Exception as e:  # noqa: BLE001
            self.flashDone.emit(False, str(e))
        finally:
            self.flashing = False
            self._last_scan = 0


class DeviceClient(QObject):
    """UI-side handle: call(fn, on_done, on_error) runs fn(tree) in the worker thread."""
    _request = Signal(object, object)
    _flash = Signal(bytes, bool)
    _select = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread = QThread()
        self.thread.setObjectName("neonpine-usb")
        self.worker = DeviceWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.start)
        self._request.connect(self.worker.run_job, Qt.QueuedConnection)
        self._flash.connect(self.worker.flash, Qt.QueuedConnection)
        self._select.connect(self.worker.select, Qt.QueuedConnection)
        self.worker.jobDone.connect(self._done, Qt.QueuedConnection)

    def start(self):
        self.thread.start()

    def shutdown(self):
        QTimer.singleShot(0, self.worker.stop)
        self.worker.set_live(None)
        self.thread.quit()
        self.thread.wait(1500)

    def call(self, fn, on_done=None, on_error=None):
        self._request.emit(fn, (on_done, on_error))

    def flash(self, image, allow_store_overwrite=False):
        self._flash.emit(bytes(image), allow_store_overwrite)

    def select(self, path):
        self._select.emit(path)

    def set_live(self, frame):
        self.worker.set_live(frame)

    @Slot(object, object, object)
    def _done(self, callbacks, result, error):
        on_done, on_error = callbacks
        if error is not None:
            if on_error:
                on_error(error)
            else:
                print("NeonPine: %s" % error)
        elif on_done:
            on_done(result)
