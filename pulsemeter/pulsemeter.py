import tkinter as tk
from tkinter import ttk
import time
import os
import platform
import shutil
import subprocess
import threading
import socket
import struct
import psutil
import numpy as np
import soundcard as sc
import sys
import traceback
import pystray
from PIL import Image
from pathlib import Path
from settings import Setting

from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

ROOT = Path(os.path.abspath(__file__)).parent
print(f"ROOT: {ROOT}")

# ---------- Bundled font loader ----------
# Drop any TTF/OTF files into  pulsemeter/fonts/  and they will be registered
# at startup without touching the user's system font directories.
#
# Current bundle: Lato-Regular.ttf  Lato-Bold.ttf  Lato-Light.ttf
#   (Lato is a clean, modern geometric sans-serif — consistent on all platforms)
_BUNDLED_FAMILY = 'Segoe UI'
_FALLBACK_FAMILY = 'Segoe UI' if platform.system() == 'Windows' else 'DejaVu Sans'


def _load_bundled_fonts() -> str:
    """
    Register fonts from  pulsemeter/fonts/  so Tk can use them by family name.

    Windows : AddFontResourceEx FR_PRIVATE — process-only, nothing written to disk.
    Linux   : Sync fonts to ~/.local/share/fonts/PulseMeter/, run fc-cache, then
              call FcInitReinitialize() so the current process sees the updated
              system font set immediately — before tk.Tk() is created.
    macOS   : CTFontManagerRegisterFontsForURL scope=Process — nothing written.
    """
    font_dir = ROOT / 'fonts'
    if not font_dir.is_dir():
        return _FALLBACK_FAMILY

    files = list(font_dir.glob('*.ttf')) + list(font_dir.glob('*.TTF')) + list(font_dir.glob('*.otf'))
    if not files:
        return _FALLBACK_FAMILY

    system = platform.system()
    try:
        if system == 'Windows':
            import ctypes
            for f in files:
                # FR_PRIVATE (0x10): loaded for this process only
                ctypes.windll.gdi32.AddFontResourceExW(str(f), 0x10, 0)

        elif system == 'Linux':
            import ctypes
            # Sync font files into the XDG user font dir (fontconfig scans this automatically)
            xdg_data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
            dst_dir = xdg_data / 'fonts' / 'PulseMeter'
            dst_dir.mkdir(parents=True, exist_ok=True)
            changed = False
            for f in files:
                dst = dst_dir / f.name
                if not dst.exists() or dst.stat().st_mtime < f.stat().st_mtime:
                    shutil.copy2(f, dst)
                    changed = True
            if changed:
                # Rebuild the per-directory fontconfig cache
                subprocess.run(['fc-cache', '-f', str(dst_dir)],
                               capture_output=True, timeout=15)
            # Reinitialise fontconfig in this process so it reads the updated cache.
            # Must happen before tk.Tk() so Xft/Tk sees the fonts at window creation.
            fc = ctypes.cdll.LoadLibrary('libfontconfig.so.1')
            fc.FcInitReinitialize.restype = ctypes.c_int
            fc.FcInitReinitialize()

        elif system == 'Darwin':
            import ctypes, ctypes.util
            ct = ctypes.cdll.LoadLibrary(ctypes.util.find_library('CoreText'))
            cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library('CoreFoundation'))
            for f in files:
                path = str(f).encode('utf-8')
                url = cf.CFURLCreateFromFileSystemRepresentation(
                    None, path, len(path), False)
                ct.CTFontManagerRegisterFontsForURL(url, 1, None)
                cf.CFRelease(url)

    except Exception as e:
        print(f'[font] Failed to load bundled fonts: {e}')
        return _FALLBACK_FAMILY

    print(f'[font] Loaded {len(files)} font(s) from {font_dir}')
    return _BUNDLED_FAMILY


_FF = _load_bundled_fonts()
print(f'[font] Using font family: {_FF}')


# -------------------- Device discovery (mDNS) --------------------

class DeviceDiscovery:
    """
    Browses for PulseMeter devices advertising _pulsemeter._tcp.local. via mDNS.

    Usage:
        discovery = DeviceDiscovery()
        discovery.on_change = lambda: print(discovery.get_devices())
        discovery.start()
        ...
        discovery.stop()
    """

    SERVICE_TYPE = "_pulsemeter._tcp.local."

    def __init__(self):
        self._zc = None
        self._browser = None
        self._devices = {}       # instance_name -> ip_str
        self._lock = threading.Lock()
        self.on_change = None    # called (no args) on the worker thread when list changes

    def start(self):
        """Start background mDNS browsing. Safe to call multiple times."""
        self.stop()
        self._devices.clear()
        try:
            self._zc = Zeroconf()
            self._browser = ServiceBrowser(self._zc, self.SERVICE_TYPE, handlers=[self._on_service])
            print("[mDNS] Discovery started")
        except Exception as e:
            print(f"[mDNS] Failed to start discovery: {e}")

    def stop(self):
        """Stop browsing and release resources."""
        try:
            if self._browser:
                self._browser.cancel()
            if self._zc:
                self._zc.close()
        except Exception:
            pass
        self._browser = None
        self._zc = None

    def get_devices(self):
        """Return list of (instance_name, ip) tuples for all discovered devices."""
        with self._lock:
            return list(self._devices.items())

    def _on_service(self, zeroconf, service_type, name, state_change):
        # Extract just the instance portion (everything before the first '.')
        instance = name.split('.')[0]

        if state_change in (ServiceStateChange.Added, ServiceStateChange.Updated):
            info = zeroconf.get_service_info(service_type, name)
            if info:
                addrs = info.parsed_addresses()
                if addrs:
                    ip = addrs[0]
                    with self._lock:
                        self._devices[instance] = ip
                    print(f"[mDNS] Found device: {instance} @ {ip}")
                    if self.on_change:
                        self.on_change()
        elif state_change is ServiceStateChange.Removed:
            with self._lock:
                self._devices.pop(instance, None)
            print(f"[mDNS] Device gone: {instance}")
            if self.on_change:
                self.on_change()


# -------------------- Protocol framing --------------------

class Protocol:
    """
    Binary framing layer for PulseMeter TCP communication.

    Frame layout (big-endian):
      magic[2]  type[1]  seq[1]  len[2]  payload[len]  crc8[1]

    seq=0 means fire-and-forget (no response expected).
    Non-zero seq is echoed in the response for request/response matching.
    """

    MAGIC0 = 0x23
    MAGIC1 = 0x35
    HEADER_SIZE = 6  # magic(2) + type(1) + seq(1) + len(2)

    # Message types
    MSG_STREAM    = 0x01  # Host → Device: push meter values
    MSG_READ_REQ  = 0x02  # Host → Device: read parameter
    MSG_READ_RSP  = 0x03  # Device → Host: read response
    MSG_WRITE_REQ = 0x04  # Host → Device: write parameter
    MSG_WRITE_RSP = 0x05  # Device → Host: write ack

    # Status codes
    STATUS_OK      = 0x00
    STATUS_ERR     = 0x01
    STATUS_UNKNOWN = 0x02

    # Parameter IDs (must match firmware protocol.h)
    PARAM_METER1_MAX_DUTY = 0x0001
    PARAM_METER2_MAX_DUTY = 0x0002
    PARAM_MODE            = 0x0003
    PARAM_METER1_VALUE    = 0x0010  # read-only
    PARAM_METER2_VALUE    = 0x0011  # read-only

    @staticmethod
    def crc8(type_: int, seq: int, payload: bytes) -> int:
        length = len(payload)
        crc = type_ ^ seq ^ (length >> 8) ^ (length & 0xFF)
        for b in payload:
            crc ^= b
        return crc & 0xFF

    @staticmethod
    def build_frame(type_: int, seq: int, payload: bytes) -> bytes:
        length = len(payload)
        header = struct.pack("!BBBBH", Protocol.MAGIC0, Protocol.MAGIC1,
                             type_, seq, length)
        crc = Protocol.crc8(type_, seq, payload)
        return header + payload + bytes([crc])

    @staticmethod
    def build_stream(d1: int, d2: int) -> bytes:
        """Stream frame: push two meter values, fire-and-forget."""
        payload = struct.pack("BB", int(d1), int(d2))
        return Protocol.build_frame(Protocol.MSG_STREAM, 0, payload)

    @staticmethod
    def build_read_req(seq: int, param_id: int) -> bytes:
        payload = struct.pack("!H", param_id)
        return Protocol.build_frame(Protocol.MSG_READ_REQ, seq, payload)

    @staticmethod
    def build_write_req(seq: int, param_id: int, value: int) -> bytes:
        payload = struct.pack("!HI", param_id, value)
        return Protocol.build_frame(Protocol.MSG_WRITE_REQ, seq, payload)

    @staticmethod
    def parse_read_rsp(payload: bytes) -> tuple:
        """Returns (param_id: int, status: int, value: int)."""
        if len(payload) < 7:
            raise ValueError(f"READ_RSP payload too short: {len(payload)}")
        param_id, status, value = struct.unpack("!HBI", payload[:7])
        return param_id, status, value

    @staticmethod
    def parse_write_rsp(payload: bytes) -> tuple:
        """Returns (param_id: int, status: int)."""
        if len(payload) < 3:
            raise ValueError(f"WRITE_RSP payload too short: {len(payload)}")
        param_id, status = struct.unpack("!HB", payload[:3])
        return param_id, status


# -------------------- 数据发送类 --------------------

class DataSender:
    """
    TCP client with bidirectional framed protocol support.

    - send_data(d1, d2)               — fire-and-forget stream frame
    - read_param(param_id)            — synchronous parameter read (blocks ≤ timeout)
    - write_param(param_id, value)    — synchronous parameter write (blocks ≤ timeout)

    Incoming response frames are dispatched by a background thread so that
    streaming and async RPC can coexist on the same socket.
    """

    def __init__(self):
        self.sock = None
        self.host = None
        self.port = None
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._pending: dict = {}          # seq → {'event': Event, 'result': ...}
        self._pending_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._recv_thread = None
        self._stop_recv = threading.Event()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self, host: str, port: int) -> bool:
        self.host = host
        self.port = port
        try:
            print(f"[TCP] Connecting to {host}:{port}")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock.settimeout(2)
            self.sock.connect((host, port))
            self.sock.settimeout(None)  # blocking mode for recv thread
            self._stop_recv.clear()
            self._recv_thread = threading.Thread(
                target=self._recv_loop, daemon=True, name="DataSender-recv")
            self._recv_thread.start()
            return True
        except Exception as e:
            print(f"[TCP] Connection failed: {e}")
            self.sock = None
            return False

    def close(self):
        self._stop_recv.set()
        if self.sock:
            try:
                # shutdown(SHUT_RDWR) does two things atomically:
                #   SHUT_WR — sends FIN immediately, remote recv() returns 0
                #   SHUT_RD — unblocks the recv thread's blocking recv() call
                # plain close() alone does neither reliably while another
                # thread is blocked in recv().
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_data(self, data1: int, data2: int) -> bool:
        """Push streaming meter values. Non-blocking, no response."""
        return self._send_raw(Protocol.build_stream(data1, data2))

    def read_param(self, param_id: int, timeout: float = 2.0):
        """
        Read a device parameter synchronously.
        Returns the integer value, or None on timeout / error.
        """
        seq = self._next_seq()
        entry = {'event': threading.Event(), 'result': None}
        with self._pending_lock:
            self._pending[seq] = entry

        if not self._send_raw(Protocol.build_read_req(seq, param_id)):
            with self._pending_lock:
                self._pending.pop(seq, None)
            return None

        if not entry['event'].wait(timeout):
            print(f"[TCP] read_param 0x{param_id:04X} timed out")
            with self._pending_lock:
                self._pending.pop(seq, None)
            return None

        try:
            _, payload = entry['result']
            _, status, value = Protocol.parse_read_rsp(payload)
            if status != Protocol.STATUS_OK:
                print(f"[TCP] read_param 0x{param_id:04X} status={status}")
                return None
            return value
        except Exception as e:
            print(f"[TCP] read_param parse error: {e}")
            return None

    def write_param(self, param_id: int, value: int, timeout: float = 2.0) -> bool:
        """
        Write a device parameter synchronously.
        Returns True on success, False on timeout / error.
        """
        seq = self._next_seq()
        entry = {'event': threading.Event(), 'result': None}
        with self._pending_lock:
            self._pending[seq] = entry

        if not self._send_raw(Protocol.build_write_req(seq, param_id, value)):
            with self._pending_lock:
                self._pending.pop(seq, None)
            return False

        if not entry['event'].wait(timeout):
            print(f"[TCP] write_param 0x{param_id:04X} timed out")
            with self._pending_lock:
                self._pending.pop(seq, None)
            return False

        try:
            _, payload = entry['result']
            _, status = Protocol.parse_write_rsp(payload)
            return status == Protocol.STATUS_OK
        except Exception as e:
            print(f"[TCP] write_param parse error: {e}")
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_seq(self) -> int:
        """Allocate next non-zero sequence number, cycling 1-255."""
        with self._seq_lock:
            self._seq = (self._seq % 255) + 1
            return self._seq

    def _send_raw(self, data: bytes) -> bool:
        if not self.sock:
            return False
        try:
            with self._send_lock:
                self.sock.sendall(data)
            return True
        except Exception as e:
            print(f"[TCP] Send failed: {e}")
            return False

    def _recv_exact(self, n: int):
        """Read exactly n bytes from the socket, or return None on error."""
        data = b''
        while len(data) < n:
            try:
                chunk = self.sock.recv(n - len(data))
                if not chunk:
                    return None
                data += chunk
            except Exception:
                return None
        return data

    def _recv_loop(self):
        """Background thread: parse inbound frames, dispatch responses."""
        while not self._stop_recv.is_set() and self.sock:
            header = self._recv_exact(Protocol.HEADER_SIZE)
            if header is None:
                print("[TCP] Recv: connection closed")
                break

            magic0, magic1, type_, seq, length = struct.unpack("!BBBBH", header)
            if magic0 != Protocol.MAGIC0 or magic1 != Protocol.MAGIC1:
                print(f"[TCP] Recv: bad magic 0x{magic0:02X} 0x{magic1:02X}")
                break

            payload = self._recv_exact(length) if length > 0 else b''
            if payload is None:
                print("[TCP] Recv: lost payload")
                break

            crc_byte = self._recv_exact(1)
            if crc_byte is None:
                break

            crc_rx   = crc_byte[0]
            crc_calc = Protocol.crc8(type_, seq, payload)
            if crc_rx != crc_calc:
                print(f"[TCP] Recv: CRC mismatch rx=0x{crc_rx:02X} calc=0x{crc_calc:02X}")
                continue  # skip bad frame; stay in sync thanks to fixed header

            if type_ in (Protocol.MSG_READ_RSP, Protocol.MSG_WRITE_RSP):
                with self._pending_lock:
                    entry = self._pending.pop(seq, None)
                if entry:
                    entry['result'] = (type_, payload)
                    entry['event'].set()
                else:
                    print(f"[TCP] Recv: no pending request for seq={seq}")


# Metric display labels — BMP-only Unicode symbols render on all platforms and fonts.
# Raw keys are used everywhere internally; labels appear only in the UI comboboxes.
METRIC_LABELS = {
    'cpu':           '⚡ CPU',
    'memory':        '🧠 Memory',
    'disk_io_read':  '📤 Disk Read',
    'disk_io_write': '📥 Disk Write',
    'net_up':        '🔼 Net Up',
    'net_down':      '🔽 Net Down',
    'audio':         '🎵 Audio',
}
METRIC_KEYS = {v: k for k, v in METRIC_LABELS.items()}


class DataCollector:
    def __init__(self):
        self.interval = None
        self.metrics: list[str] = []
        self.callback = None
        self._stop_event = threading.Event()
        self._thread = None
        self._prev_net = psutil.net_io_counters()
        self._prev_disk = psutil.disk_io_counters()
        self._mic = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
        # Audio is sampled in a dedicated thread to avoid blocking the main loop.
        # The recorder is kept open permanently to eliminate per-iteration open overhead.
        self._audio_level: float = 0.0
        self._audio_stop = threading.Event()
        self._audio_thread: threading.Thread | None = None
        # Cache of the last non-audio data frame.  Written by _run() at 0.5 s;
        # read by _audio_loop() so it can assemble a complete dict at 50 ms rate.
        # Dict reference replacement is atomic under the GIL, so no extra lock needed.
        self._non_audio_cache: dict = {}

    def get_available_metrics(self):
        # Returns display labels (with icons); use METRIC_KEYS to convert back to raw keys.
        return list(METRIC_LABELS.values())

    def start(self, interval=1.0, metrics=None, callback=None):
        self.interval = interval
        self.metrics = metrics
        self.callback = callback
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        # Start a dedicated audio thread when audio is selected.
        # It keeps the recorder open permanently so the main loop is never blocked.
        if "audio" in (metrics or []):
            if self._audio_thread is None or not self._audio_thread.is_alive():
                self._audio_stop.clear()
                self._audio_thread = threading.Thread(
                    target=self._audio_loop, daemon=True, name="DataCollector-audio")
                self._audio_thread.start()

    def stop(self):
        self._stop_event.set()
        self._audio_stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 1.0 if self.interval else 3.0)
        if self._audio_thread and self._audio_thread.is_alive():
            self._audio_thread.join(timeout=3.0)

    # Fixed audio analysis window independent of the main collection interval.
    # 50 ms gives ~20 Hz beat-detection updates while keeping FFT bins fine
    # enough to resolve 60–300 Hz bass content.
    _AUDIO_CHUNK_S = 0.05

    def _audio_loop(self):
        """
        Dedicated audio sampling thread.
        Keeps a single recorder context open and continuously updates
        self._audio_level so the main collection loop can read it without blocking.

        Uses a fixed chunk size (_AUDIO_CHUNK_S) that is independent of the
        main collection interval, so selecting audio on one meter does not
        force non-audio metrics to run at a faster (wasteful) rate.
        """
        samplerate = 8000
        # Fixed window regardless of the main loop interval
        chunk_frames = max(1, int(self._AUDIO_CHUNK_S * samplerate))

        # Bass band: kick drum + bass guitar (60–300 Hz).
        # Zeroing everything outside this range in the FFT removes cymbals,
        # vocals and high-frequency noise that obscure the rhythmic beat signal.
        FREQ_LOW  = 60    # Hz — below this is rumble/DC
        FREQ_HIGH = 300   # Hz — above this is mids/highs

        try:
            with self._mic.recorder(samplerate=samplerate, channels=1) as rec:
                while not self._audio_stop.is_set():
                    buf = rec.record(numframes=chunk_frames).flatten()
                    if buf.size == 0:
                        continue

                    # FFT band-pass: keep only FREQ_LOW ~ FREQ_HIGH
                    spectrum = np.fft.rfft(buf)
                    freqs    = np.fft.rfftfreq(len(buf), d=1.0 / samplerate)
                    spectrum[(freqs < FREQ_LOW) | (freqs > FREQ_HIGH)] = 0
                    bass     = np.fft.irfft(spectrum, len(buf))

                    rms = np.sqrt(np.mean(np.square(bass)))
                    if rms > 1e-6:
                        # dB scale: [-60 dB, 0 dB] → [0, 100]
                        db = 20 * np.log10(rms)
                        self._audio_level = round(max(0.0, min(100.0, (db + 60) / 60 * 100)), 2)
                    else:
                        self._audio_level = 0.0

                    # Drive the callback at audio rate.  Take a GIL-safe snapshot
                    # of the non-audio cache and inject the fresh audio level so
                    # the sender and UI both update at _AUDIO_CHUNK_S (50 ms).
                    if self.callback:
                        data = dict(self._non_audio_cache)
                        data['audio'] = self._audio_level
                        self.callback(data)
        except Exception:
            traceback.print_exc()

    def _run(self):
        # Pre-warm cpu_percent so the first real sample isn't always 0.0
        psutil.cpu_percent(interval=None)

        # Use an absolute deadline instead of a relative sleep.
        # With relative sleep: if the OS oversleeps by N ms one iteration,
        # the next iteration has no sleep at all, creating a long/short
        # alternating pattern. With an absolute deadline the schedule
        # self-corrects: a late wakeup just shortens the *next* sleep, and
        # the average rate stays on target.
        next_deadline = time.perf_counter() + self.interval

        while not self._stop_event.is_set():
            tick_start = time.perf_counter()
            data = {}

            # Snapshot metrics and interval once per iteration so that a
            # concurrent update_metrics() call cannot cause inconsistency
            # between the multiple "in metrics" checks below.
            metrics  = self.metrics
            interval = self.interval

            # 常规指标
            if "cpu" in metrics:
                data["cpu"] = psutil.cpu_percent(interval=None)
            if "memory" in metrics:
                mem = psutil.virtual_memory()
                data["memory"] = mem.percent
            if "disk_io_read" in metrics or "disk_io_write" in metrics:
                disk = psutil.disk_io_counters()
                # Use actual elapsed time for accurate speed calculation
                actual_dt = time.perf_counter() - tick_start or interval
                read_speed = (disk.read_bytes - self._prev_disk.read_bytes) / actual_dt
                write_speed = (disk.write_bytes - self._prev_disk.write_bytes) / actual_dt
                key = "disk_io_read" if "disk_io_read" in metrics else "disk_io_write"
                data[key] = {"MB/s": round((read_speed if key == "disk_io_read" else write_speed) / (1024 * 1024), 2)}
                self._prev_disk = disk
            if "net_up" in metrics or "net_down" in metrics:
                net = psutil.net_io_counters()
                actual_dt = time.perf_counter() - tick_start or interval
                up_speed = (net.bytes_sent - self._prev_net.bytes_sent) / actual_dt
                down_speed = (net.bytes_recv - self._prev_net.bytes_recv) / actual_dt
                key = "net_up" if "net_up" in metrics else "net_down"
                data[key] = {"MB/s": round((up_speed if key == "net_up" else down_speed) / (1024 * 1024), 2)}
                self._prev_net = net
            if "audio" in metrics:
                # When audio is active the _audio_loop drives the callback at
                # _AUDIO_CHUNK_S rate.  Here we only refresh the non-audio cache
                # so the audio loop can pair the latest collected values with
                # each fresh audio sample.  Do NOT fire the callback from here —
                # that would produce a second, slower stream of audio frames.
                self._non_audio_cache = data  # atomic dict replace under GIL
            else:
                # No audio: fire callback at the normal 0.5 s collection rate.
                if self.callback:
                    self.callback(data)

            # Sleep until the next absolute deadline, then advance it.
            # If we're already past the deadline, skip the sleep but still
            # advance so we don't try to catch up with a burst of sends.
            remaining = next_deadline - time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)
            next_deadline += interval


# -------------------- 仪表管理类 --------------------
class MeterManager:
    def __init__(self):
        self.sender = DataSender()
        self.setting = Setting()
        self.collector = DataCollector()
        self.extra_display_callback = None
        self.is_running = False
        self._calibrating = False   # when True, override output with 100/100

    @staticmethod
    def _to_pct(v) -> int:
        """Convert a raw metric value to a 0–100 integer suitable for the TCP frame.
        Numeric values are clamped; MB/s dicts are scaled (5 MB/s → 100)."""
        if isinstance(v, dict):
            return int(min(v.get('MB/s', 0.0) * 20.0, 100.0))
        try:
            return max(0, min(100, int(float(v))))
        except (TypeError, ValueError):
            return 0

    def data_cb(self, data):
        try:
            # Snapshot metric keys to stay consistent if restart_collector() fires
            # concurrently on another thread.
            metrics = self.collector.metrics
            if len(metrics) < 2:
                return
            # Use .get() so a mid-switch frame missing the new key is treated as 0.
            data1 = data.get(metrics[0], 0)
            data2 = data.get(metrics[1], 0)
            if self._calibrating:
                # Send full-scale values so the needle visually reaches max_duty
                self.sender.send_data(100, 100)
            else:
                pct1, pct2 = self._to_pct(data1), self._to_pct(data2)
                print(f"[CPU] Sending data: {pct1}, {pct2}")
                self.sender.send_data(pct1, pct2)
            if self.extra_display_callback:
                self.extra_display_callback(data1, data2)
        except Exception as e:
            print(f"[CPU] Loop error: {e}")
            traceback.print_exc()

    def start(self):
        metrics = [self.setting.systemsetting.meter1, self.setting.systemsetting.meter2]
        # All metrics use a 0.5 s collection interval.  Audio is sampled by its
        # own dedicated thread at _AUDIO_CHUNK_S (50 ms) and exposed via
        # _audio_level, so the main loop just does a non-blocking read.
        interval = 0.5
        print("[APP] Starting MeterManager", self.setting.systemsetting.__dict__, f"interval={interval}")
        self.collector.start(interval, metrics=metrics, callback=self.data_cb)
        self.sender.connect(self.setting.systemsetting.server_ip, 5000)
        self.is_running = True

    def start_calibration(self):
        """Override data output with 100/100 so needles sweep to full scale."""
        self._calibrating = True

    def stop_calibration(self):
        """Return to normal data-driven output."""
        self._calibrating = False

    def restart_collector(self, meter1: str, meter2: str):
        """
        Hot-swap the two metric channels without dropping the TCP connection.

        Stops the current collector (joins its thread), updates settings,
        then restarts with the new metrics.  The sender is intentionally
        left untouched.

        MUST be called from a non-UI thread — collector.stop() blocks until
        the worker thread exits (up to interval + 1 s).
        """
        self.collector.stop()
        self.setting.systemsetting.meter1 = meter1
        self.setting.systemsetting.meter2 = meter2
        metrics  = [meter1, meter2]
        interval = 0.5  # audio is handled by its own thread; main loop stays at 0.5 s
        print(f"[APP] Restarting collector: {meter1}, {meter2}  interval={interval}")
        self.collector.start(interval, metrics=metrics, callback=self.data_cb)

    def stop(self):
        self._calibrating = False
        print("[APP] Stopped MeterManager")
        self.collector.stop()
        self.sender.send_data(0, 0)
        self.sender.close()
        self.is_running = False

    def set_extra_display_callback(self, callback):
        self.extra_display_callback = callback


# -------------------- Theme --------------------

THEME = {
    'bg':        '#1e1e2e',   # main window background
    'surface':   '#181825',   # header / footer surface
    'card':      '#313244',   # metric card background
    'border':    '#45475a',   # border / separator
    'accent':    '#89b4fa',   # primary accent (blue)
    'accent2':   '#cba6f7',   # secondary accent (purple)
    'text':      '#cdd6f4',   # primary text
    'subtext':   '#a6adc8',   # muted / secondary text
    'green':     '#a6e3a1',   # connected / ok
    'red':       '#f38ba8',   # disconnected / error
    'yellow':    '#f9e2af',   # warning (high load)
    'input_bg':  '#45475a',   # input field background
    'btn_hover': '#585b70',   # generic button hover
}

FONT = {
    'title':   (_FF, 13, 'bold'),
    'value':   (_FF, 32, 'bold'),   # enlarged for prominence
    'unit':    (_FF, 9),            # unit label beneath value
    'card_h':  (_FF, 11, 'bold'),
    'normal':  (_FF, 10),
    'small':   (_FF, 9),
    'btn':     (_FF, 10, 'bold'),
    'section': (_FF, 7, 'bold'),    # section headers inside settings
    'combo':   (_FF, 11),           # metric selector dropdown
}

# -------------------- UI Helpers --------------------

class _HoverButton(tk.Button):
    """tk.Button that highlights on mouse-over."""

    def __init__(self, master, hover_bg=None, **kw):
        _hover = hover_bg or THEME['btn_hover']
        kw.setdefault('activebackground', _hover)
        kw.setdefault('activeforeground', kw.get('fg', THEME['text']))
        super().__init__(master, **kw)
        self._normal_bg = kw.get('bg', THEME['card'])
        self._hover_bg  = _hover
        self.bind('<Enter>', lambda _: self.config(bg=self._hover_bg))
        self.bind('<Leave>', lambda _: self.config(bg=self._normal_bg))


class _ProgressBar(tk.Canvas):
    """Horizontal progress bar — 5 px tall, colour-coded by level."""

    def __init__(self, master, **kw):
        kw.setdefault('height', 5)
        kw.setdefault('highlightthickness', 0)
        super().__init__(master, **kw)
        self._value = 0.0
        self.bind('<Configure>', lambda _: self._redraw())

    def set_value(self, value: float):
        self._value = max(0.0, min(100.0, float(value)))
        self._redraw()

    def _redraw(self):
        self.delete('all')
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1:
            return
        self.create_rectangle(0, 0, w, h, fill=THEME['border'], outline='')
        filled = int(w * self._value / 100)
        if filled > 0:
            v = self._value
            color = THEME['green'] if v < 70 else THEME['yellow'] if v < 90 else THEME['red']
            self.create_rectangle(0, 0, filled, h, fill=color, outline='')


# -------------------- Settings Window --------------------

class SettingsWindow:
    """
    Modal settings popup with two sections:
      CONNECTION  — IP combo, mDNS scan, connect/disconnect
      CALIBRATION — per-meter max_duty read/write

    Holds a reference to PulseMeterApp for bidirectional state sync.
    """

    def __init__(self, parent: tk.Tk, app: 'PulseMeterApp'):
        self._app      = app
        self._manager  = app.manager
        self._max_duty = app._max_duty

        win = tk.Toplevel(parent)
        win.title("Settings")
        win.geometry("360x300")
        win.resizable(False, False)
        win.configure(bg=THEME['bg'])
        win.transient(parent)
        win.grab_set()
        win.protocol("WM_DELETE_WINDOW", self._on_close)
        self.win = win

        # --- Header ---
        hdr = tk.Frame(win, bg=THEME['surface'], height=44)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Settings", bg=THEME['surface'],
                 fg=THEME['text'], font=FONT['title']).pack(side='left', padx=16, pady=10)

        # --- Body ---
        body = tk.Frame(win, bg=THEME['bg'], padx=20, pady=12)
        body.pack(fill='both', expand=True)

        # -- Section: CONNECTION --
        tk.Label(body, text="CONNECTION", bg=THEME['bg'],
                 fg=THEME['accent'], font=FONT['section']).grid(
                     row=0, column=0, columnspan=4, sticky='w', pady=(0, 4))

        tk.Label(body, text="IP", bg=THEME['bg'],
                 fg=THEME['subtext'], font=FONT['small']).grid(
                     row=1, column=0, sticky='w', pady=6)

        self._ip_combo = ttk.Combobox(body, width=16, style='Dark.TCombobox')
        self._ip_combo.set(self._manager.setting.systemsetting.server_ip)
        self._ip_combo['values'] = app._discovered_ips
        self._ip_combo.grid(row=1, column=1, sticky='ew', padx=(8, 4), pady=6)

        _HoverButton(body, text="↻", bg=THEME['bg'], hover_bg=THEME['border'],
                     fg=THEME['subtext'], font=(_FF, 13),
                     relief='flat', cursor='hand2',
                     command=self._rescan).grid(row=1, column=2, padx=(0, 6))

        self._conn_btn = _HoverButton(
            body, text="", bg=THEME['accent'], hover_bg='#a6c8ff',
            fg=THEME['bg'], font=FONT['btn'],
            relief='flat', cursor='hand2', width=7, padx=4,
            command=self._toggle_connect)
        self._conn_btn.grid(row=1, column=3, pady=6)
        self.refresh_connect_btn()

        # -- Separator --
        tk.Frame(body, bg=THEME['border'], height=1).grid(
            row=2, column=0, columnspan=4, sticky='ew', pady=(4, 10))

        # -- Section: CALIBRATION --
        tk.Label(body, text="CALIBRATION", bg=THEME['bg'],
                 fg=THEME['accent2'], font=FONT['section']).grid(
                     row=3, column=0, columnspan=3, sticky='w', pady=(0, 4))

        self._calib_btn = _HoverButton(
            body, text="▶ Cal", bg=THEME['card'], hover_bg=THEME['border'],
            fg=THEME['accent2'], font=FONT['small'],
            relief='flat', cursor='hand2', width=7, padx=2,
            command=self._toggle_calibrate)
        self._calib_btn.grid(row=3, column=3, pady=(0, 4))
        self._refresh_calib_btn()

        for idx, (default, name) in enumerate([
            (self._max_duty[0], "Meter 1  max duty"),
            (self._max_duty[1], "Meter 2  max duty"),
        ]):
            tk.Label(body, text=name, bg=THEME['bg'],
                     fg=THEME['subtext'], font=FONT['small']).grid(
                         row=4 + idx, column=0, sticky='w', pady=6)

            spin = ttk.Spinbox(body, from_=1, to=4095, increment=1,
                               width=7, style='Dark.TSpinbox')
            spin.set(default)
            spin.grid(row=4 + idx, column=1, padx=(8, 4), pady=6)

            btn_r = _HoverButton(body, text="R", width=2,
                                 bg=THEME['card'], fg=THEME['accent'],
                                 font=FONT['small'], relief='flat', cursor='hand2',
                                 command=lambda i=idx+1, s=spin: self._read_duty(i, s))
            btn_r.grid(row=4 + idx, column=2, padx=2)

            btn_w = _HoverButton(body, text="W", width=2,
                                 bg=THEME['card'], fg=THEME['accent2'],
                                 font=FONT['small'], relief='flat', cursor='hand2',
                                 command=lambda i=idx+1, s=spin: self._write_duty(i, s))
            btn_w.grid(row=4 + idx, column=3, padx=2)

            if idx == 0:
                self._spin1, self._btn1_r, self._btn1_w = spin, btn_r, btn_w
            else:
                self._spin2, self._btn2_r, self._btn2_w = spin, btn_r, btn_w

        body.grid_columnconfigure(1, weight=1)

        # --- Footer ---
        footer = tk.Frame(win, bg=THEME['surface'], height=48)
        footer.pack(fill='x', side='bottom')
        footer.pack_propagate(False)
        _HoverButton(footer, text="Close", bg=THEME['card'], hover_bg=THEME['border'],
                     fg=THEME['text'], font=FONT['btn'], relief='flat', cursor='hand2',
                     padx=20, command=self._on_close).pack(side='right', padx=16, pady=10)

    # ------------------------------------------------------------------
    # Public refresh methods called by PulseMeterApp
    # ------------------------------------------------------------------

    def refresh_connect_btn(self):
        """Sync the connect/disconnect button text and colour to manager state."""
        if self._manager.is_running:
            self._conn_btn._normal_bg = THEME['red']
            self._conn_btn._hover_bg  = '#ffa0b0'
            self._conn_btn.config(text="■ Discon.", bg=THEME['red'], fg=THEME['bg'])
        else:
            self._conn_btn._normal_bg = THEME['accent']
            self._conn_btn._hover_bg  = '#a6c8ff'
            self._conn_btn.config(text="▶ Connect", bg=THEME['accent'], fg=THEME['bg'])
        # Calibrate button is only usable while connected
        # (_calib_btn may not exist yet during __init__ construction)
        if hasattr(self, '_calib_btn'):
            self._refresh_calib_btn()

    def refresh_ip_list(self, ips: list):
        """Update the IP combo when mDNS discovery changes."""
        self._ip_combo['values'] = ips

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _toggle_connect(self):
        """Write the selected IP to settings then delegate to app.toggle_start()."""
        self._app.manager.setting.systemsetting.server_ip = self._ip_combo.get()
        self._app.toggle_start()

    def _toggle_calibrate(self):
        """Start or stop calibration mode (sends 100/100 to drive needles to max)."""
        if not self._manager.is_running:
            return
        if self._manager._calibrating:
            self._manager.stop_calibration()
        else:
            self._manager.start_calibration()
        self._refresh_calib_btn()

    def _refresh_calib_btn(self):
        """Update calibrate button appearance based on connection + calibration state."""
        if not self._manager.is_running:
            self._calib_btn.config(state='disabled', fg=THEME['border'])
        elif self._manager._calibrating:
            self._calib_btn.config(state='normal',
                                   text="■ Stop", fg=THEME['yellow'])
            self._calib_btn._normal_bg = THEME['card']
        else:
            self._calib_btn.config(state='normal',
                                   text="▶ Cal", fg=THEME['accent2'])
            self._calib_btn._normal_bg = THEME['card']

    def _rescan(self):
        self._ip_combo['values'] = []
        self._app._rescan_devices()

    def _on_close(self):
        """Persist max_duty values back to shared list before closing."""
        # Leave calibration mode when the window is dismissed
        self._manager.stop_calibration()
        for i, spin in enumerate([self._spin1, self._spin2]):
            try:
                self._max_duty[i] = int(float(spin.get()))
            except ValueError:
                pass
        self._app._settings_win = None
        self.win.destroy()

    def _read_duty(self, meter_idx: int, spin: ttk.Spinbox):
        """Read max_duty from device and populate the spinbox."""
        if not self._manager.is_running:
            return
        param = Protocol.PARAM_METER1_MAX_DUTY if meter_idx == 1 else Protocol.PARAM_METER2_MAX_DUTY
        btn   = self._btn1_r if meter_idx == 1 else self._btn2_r
        btn.config(state='disabled')

        def do():
            value = self._manager.sender.read_param(param)
            def done():
                btn.config(state='normal')
                if value is not None:
                    spin.set(value)
                    print(f"[APP] meter{meter_idx} max_duty = {value}")
                else:
                    print(f"[APP] meter{meter_idx} max_duty read failed")
            self.win.after(0, done)

        threading.Thread(target=do, daemon=True).start()

    def _write_duty(self, meter_idx: int, spin: ttk.Spinbox):
        """Write max_duty to device."""
        if not self._manager.is_running:
            return
        param = Protocol.PARAM_METER1_MAX_DUTY if meter_idx == 1 else Protocol.PARAM_METER2_MAX_DUTY
        btn   = self._btn1_w if meter_idx == 1 else self._btn2_w
        try:
            value = int(float(spin.get()))
        except ValueError:
            return
        btn.config(state='disabled')

        def do():
            ok = self._manager.sender.write_param(param, value)
            def done():
                btn.config(state='normal')
                print(f"[APP] meter{meter_idx} max_duty write {'ok' if ok else 'FAILED'}")
            self.win.after(0, done)

        threading.Thread(target=do, daemon=True).start()


# -------------------- Main GUI --------------------

class PulseMeterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PulseMeter")
        self.root.geometry("460x310")
        self.root.resizable(False, False)
        self.root.configure(bg=THEME['bg'])
        self.manager = MeterManager()

        self._max_duty       = [448, 236]   # shared with SettingsWindow
        self._discovered_ips: list = []     # filled by mDNS, read by SettingsWindow
        self._settings_win   = None         # track open SettingsWindow instance

        self._configure_styles()
        self._build_ui()

        # mDNS device discovery
        self.discovery = DeviceDiscovery()
        self.discovery.on_change = self._on_devices_changed
        self.discovery.start()

    # ------------------------------------------------------------------
    # Style setup
    # ------------------------------------------------------------------

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use('default')

        self.root.option_add('*TCombobox*Listbox.background',       THEME['input_bg'])
        self.root.option_add('*TCombobox*Listbox.foreground',       THEME['text'])
        self.root.option_add('*TCombobox*Listbox.selectBackground', THEME['accent'])
        self.root.option_add('*TCombobox*Listbox.selectForeground', THEME['bg'])

        style.configure('Dark.TCombobox',
            fieldbackground=THEME['input_bg'],
            background=THEME['card'],
            foreground=THEME['text'],
            arrowcolor=THEME['text'],
            bordercolor=THEME['border'],
            selectbackground=THEME['input_bg'],
            selectforeground=THEME['text'],
            padding=6,
        )
        style.map('Dark.TCombobox',
            fieldbackground=[('readonly', THEME['input_bg'])],
            selectbackground=[('readonly', THEME['input_bg'])],
            selectforeground=[('readonly', THEME['text'])],
        )
        style.configure('Dark.TEntry',
            fieldbackground=THEME['input_bg'],
            foreground=THEME['text'],
            insertcolor=THEME['text'],
            bordercolor=THEME['border'],
            padding=6,
        )
        style.configure('Dark.TSpinbox',
            fieldbackground=THEME['input_bg'],
            foreground=THEME['text'],
            insertcolor=THEME['text'],
            arrowcolor=THEME['text'],
            bordercolor=THEME['border'],
            padding=4,
        )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_ui(self):
        # === Header bar ===
        hdr = tk.Frame(self.root, bg=THEME['surface'], height=52)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)

        # Status dot — left of the title
        self._dot_cv = tk.Canvas(hdr, width=12, height=12,
                                 bg=THEME['surface'], highlightthickness=0)
        self._dot_cv.pack(side='left', padx=(16, 8), pady=20)
        self._dot = self._dot_cv.create_oval(1, 1, 11, 11, fill=THEME['red'], outline='')

        tk.Label(hdr, text="PULSEMETER", bg=THEME['surface'],
                 fg=THEME['text'], font=FONT['title']).pack(side='left', pady=14)

        # Gear button — accent colour when disconnected to guide the user
        self._gear_btn = _HoverButton(
            hdr, text="⚙", bg=THEME['surface'], hover_bg=THEME['border'],
            fg=THEME['accent'], font=(_FF, 14),
            relief='flat', cursor='hand2', padx=4,
            command=self._open_settings)
        self._gear_btn.pack(side='right', padx=(2, 12), pady=8)

        # Accent line below the header
        acc = tk.Canvas(self.root, height=2, bg=THEME['bg'], highlightthickness=0)
        acc.pack(fill='x')
        acc.bind('<Configure>', lambda e: (
            acc.delete('all'),
            acc.create_rectangle(0, 0, e.width, 2, fill=THEME['accent'], outline='')
        ))

        # === Metric cards ===
        cards = tk.Frame(self.root, bg=THEME['bg'])
        cards.pack(fill='both', expand=True, padx=16, pady=(12, 6))
        cards.grid_columnconfigure(0, weight=1)
        cards.grid_columnconfigure(1, weight=1)

        self.combo1, self._val1, self._unit1, self._prog1 = self._build_card(
            cards, col=0, title="METER 1", accent=THEME['accent'],
            default=self.manager.setting.systemsetting.meter1)
        self.combo2, self._val2, self._unit2, self._prog2 = self._build_card(
            cards, col=1, title="METER 2", accent=THEME['accent2'],
            default=self.manager.setting.systemsetting.meter2)

        # Dynamic metric switching — fires on the main thread (Tkinter event loop),
        # so it is safe to read combo state and schedule background work here.
        self.combo1.bind('<<ComboboxSelected>>', self._on_metric_changed)
        self.combo2.bind('<<ComboboxSelected>>', self._on_metric_changed)

        # === Hint label (only visible when disconnected) ===
        self._hint = tk.Label(
            self.root,
            text="○  Not connected — open ⚙ to connect",
            bg=THEME['bg'], fg=THEME['border'], font=FONT['small'])
        self._hint.pack(pady=(0, 8))

    def _build_card(self, parent: tk.Frame, col: int, title: str,
                    accent: str, default: str):
        """Build and grid a metric card. Returns (combo, val_label, unit_label, progress)."""
        padx = (0, 8) if col == 0 else (8, 0)

        # 4 px coloured left border via a thin accent-coloured wrapper frame
        wrapper = tk.Frame(parent, bg=accent)
        wrapper.grid(row=0, column=col, sticky='nsew', padx=padx)

        card = tk.Frame(wrapper, bg=THEME['card'])
        card.pack(fill='both', expand=True, padx=(4, 0))

        inner = tk.Frame(card, bg=THEME['card'], padx=12, pady=10)
        inner.pack(fill='both', expand=True)

        tk.Label(inner, text=title, bg=THEME['card'],
                 fg=THEME['subtext'], font=FONT['card_h']).pack(anchor='w')

        combo = ttk.Combobox(inner, values=self.manager.collector.get_available_metrics(),
                             width=15, state='readonly', style='Dark.TCombobox',
                             font=FONT['combo'])
        # default is a raw key from settings; convert to display label for the combobox
        combo.set(METRIC_LABELS.get(default, default))
        combo.pack(fill='x', pady=(6, 0))

        val_lbl = tk.Label(inner, text="—", bg=THEME['card'],
                           fg=accent, font=FONT['value'])
        val_lbl.pack(pady=(8, 0))

        unit_lbl = tk.Label(inner, text="", bg=THEME['card'],
                            fg=THEME['subtext'], font=FONT['unit'])
        unit_lbl.pack()

        prog = _ProgressBar(inner, bg=THEME['card'])
        prog.pack(fill='x', pady=(6, 0))

        return combo, val_lbl, unit_lbl, prog

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _open_settings(self):
        """Open settings window; bring existing one to front if already open."""
        if self._settings_win is not None:
            try:
                self._settings_win.win.focus_force()
                return
            except tk.TclError:
                self._settings_win = None
        self._settings_win = SettingsWindow(self.root, self)

    def _on_devices_changed(self):
        """Called from the mDNS worker thread — marshal update to main thread."""
        devices = self.discovery.get_devices()
        ips     = [ip for _, ip in devices]

        def update():
            self._discovered_ips = ips
            # Refresh IP combo inside settings window if it is open
            if self._settings_win is not None:
                try:
                    self._settings_win.refresh_ip_list(ips)
                except tk.TclError:
                    self._settings_win = None
            # Auto-connect when exactly one device is on the network
            if len(ips) == 1 and not self.manager.is_running:
                print(f"[mDNS] Single device @ {ips[0]} — auto-connecting")
                self.manager.setting.systemsetting.server_ip = ips[0]
                self.toggle_start()

        self.root.after(0, update)

    def _rescan_devices(self):
        """Restart mDNS discovery and clear stale device list."""
        self._discovered_ips = []
        self.discovery.start()

    @staticmethod
    def _fmt(v) -> tuple:
        """Return (display_str, unit_str, progress_pct 0–100) for a raw metric value."""
        if isinstance(v, dict):
            mb = v.get('MB/s', 0.0)
            return f"{mb:.1f}", "MB/s", min(mb * 20.0, 100.0)
        try:
            f = float(v)
            return f"{f:.1f}", "%", f
        except (TypeError, ValueError):
            return "—", "", 0.0

    def update_meter_label(self, meter1, meter2):
        """Collector thread callback — must marshal to the main thread."""
        def _update():
            for val, lbl, unit_lbl, prog in [
                (meter1, self._val1, self._unit1, self._prog1),
                (meter2, self._val2, self._unit2, self._prog2),
            ]:
                text, unit, pct = self._fmt(val)
                lbl.config(text=text)
                unit_lbl.config(text=unit)
                prog.set_value(pct)

        self.root.after(0, _update)

    def _set_connected(self, connected: bool):
        self._dot_cv.itemconfig(self._dot, fill=THEME['green'] if connected else THEME['red'])
        # Gear button: muted when connected (no action needed), accent when not (guide user)
        self._gear_btn._normal_bg = THEME['surface']
        self._gear_btn._hover_bg  = THEME['border']
        self._gear_btn.config(fg=THEME['subtext'] if connected else THEME['accent'],
                              bg=THEME['surface'])
        self._hint.config(text="" if connected else "○  Not connected — open ⚙ to connect")

        if not connected:
            for lbl, unit_lbl, prog in [
                (self._val1, self._unit1, self._prog1),
                (self._val2, self._unit2, self._prog2),
            ]:
                lbl.config(text="—")
                unit_lbl.config(text="")
                prog.set_value(0)

        # Sync the connect button inside settings window if it is open
        if self._settings_win is not None:
            try:
                self._settings_win.refresh_connect_btn()
            except tk.TclError:
                self._settings_win = None

    def _on_metric_changed(self, event=None):
        """
        Called on the main thread when either metric combo is changed.

        If the manager is not yet running, the new selection will simply be
        picked up when the user connects — no action needed.

        If already running, the collector must be restarted with the new
        metrics.  collector.stop() blocks until the worker thread exits, so
        the restart is offloaded to a daemon thread.  Both combos are
        temporarily disabled to prevent a second change from racing with
        the in-flight restart.
        """
        # Clear the text selection highlight that ttk.Combobox leaves after picking
        if event and hasattr(event, 'widget'):
            event.widget.selection_clear()

        if not self.manager.is_running:
            return

        m1 = METRIC_KEYS.get(self.combo1.get(), self.combo1.get())
        m2 = METRIC_KEYS.get(self.combo2.get(), self.combo2.get())

        # Disable both combos while the restart is in progress
        self.combo1.config(state='disabled')
        self.combo2.config(state='disabled')

        def do_restart():
            self.manager.restart_collector(m1, m2)
            # Re-enable combos on the main thread once restart completes
            self.root.after(0, lambda: (
                self.combo1.config(state='readonly'),
                self.combo2.config(state='readonly'),
            ))

        threading.Thread(target=do_restart, daemon=True,
                         name="MetricRestart").start()

    def toggle_start(self):
        if self.manager.is_running:
            self.manager.stop()
            self.manager.set_extra_display_callback(None)
            self._set_connected(False)
            print("[APP] stopped")
        else:
            # server_ip is already written by SettingsWindow._toggle_connect
            # or by _on_devices_changed (auto-connect); just sync the metric choice.
            # Combo shows display labels; convert back to raw keys for internal use.
            self.manager.setting.systemsetting.meter1 = METRIC_KEYS.get(self.combo1.get(), self.combo1.get())
            self.manager.setting.systemsetting.meter2 = METRIC_KEYS.get(self.combo2.get(), self.combo2.get())
            self.manager.setting.save(self.manager.setting.save_filename)
            self.manager.start()
            self.manager.set_extra_display_callback(self.update_meter_label)
            self._set_connected(True)
            print("[APP] started")


class TrayApp:
    def __init__(self, root, app):
        self.root: tk.Tk = root
        self.app: PulseMeterApp = app
        self.icon = pystray.Icon(
            "PulseMeter",
            Image.open(ROOT / "assets" / "icon.ico"),
            "PulseMeter",
            menu=pystray.Menu(
                pystray.MenuItem("Show", self.show_window, default=True),
                pystray.MenuItem("Exit", self.exit_app),
            ),
        )

    def run(self):
        threading.Thread(target=self.icon.run, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

    def hide_window(self):
        self.root.withdraw()

    def show_window(self, icon=None, item=None):
        self.root.deiconify()
        self.root.after(0, self.root.focus_force)

    def exit_app(self, icon, item):
        self.icon.stop()
        self.app.manager.stop()
        self.app.discovery.stop()
        self.root.destroy()


if __name__ == "__main__":
    if "--no-gui" in sys.argv:
        manager = MeterManager()
        manager.start()
        while True:
            time.sleep(1)
    else:
        root = tk.Tk()
        # Set the window title-bar / taskbar icon
        try:
            icon_path = ROOT / "assets" / "icon.ico"
            root.iconbitmap(str(icon_path))
        except Exception:
            pass

        app = PulseMeterApp(root)
        tray = TrayApp(root, app)
        tray.run()
        root.mainloop()
