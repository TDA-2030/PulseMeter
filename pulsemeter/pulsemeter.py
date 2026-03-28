import tkinter as tk
from tkinter import ttk
import time
import os
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
print(ROOT)


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


class DataCollector:
    def __init__(self):
        """
        :param interval: 数据采集间隔（秒）
        :param metrics: 要采集的指标列表，
                        可选 ['cpu', 'memory', 'disk_io', 'net', 'audio']
        :param callback: 数据采集完成回调函数，函数参数为采集的数据字典
        """
        self.interval = None
        self.metrics: list[str] = []
        self.callback = None
        self._stop_event = threading.Event()
        self._thread = None
        self._prev_net = psutil.net_io_counters()
        self._prev_disk = psutil.disk_io_counters()
        self._mic = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)

    def get_available_metrics(self):
        return ["cpu", "memory", "disk_io_read", "disk_io_write", "net_up", "net_down", "audio"]

    def start(self, interval=1.0, metrics=None, callback=None):
        self.interval = interval
        self.metrics = metrics
        self.callback = callback
        """启动采集线程"""
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        """停止采集线程"""
        self._stop_event.set()
        if self._thread:
            self._thread.join()

    def _get_audio_level(self, duration, samplerate=8000):
        """
        在整个 duration 内采样系统音频，计算 RMS 电平
        返回值范围 0~1
        """
        try:
            numframes = int(duration * samplerate)
            with self._mic.recorder(samplerate=samplerate, channels=1) as rec:
                data = rec.record(numframes=numframes)
                if data.size == 0:
                    return 0.0
                rms = np.sqrt(np.mean(np.square(data)))
                return round(100*min(rms, 1.0), 2)  # 限制最大值为1.0
        except Exception:
            traceback.print_exc()
            return None  # 没有音频设备时返回 None

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

            # 常规指标
            if "cpu" in self.metrics:
                data["cpu"] = psutil.cpu_percent(interval=None)
            if "memory" in self.metrics:
                mem = psutil.virtual_memory()
                data["memory"] = mem.percent
            if "disk_io_read" in self.metrics or "disk_io_write" in self.metrics:
                disk = psutil.disk_io_counters()
                # Use actual elapsed time for accurate speed calculation
                actual_dt = time.perf_counter() - tick_start or self.interval
                read_speed = (disk.read_bytes - self._prev_disk.read_bytes) / actual_dt
                write_speed = (disk.write_bytes - self._prev_disk.write_bytes) / actual_dt
                key = "disk_io_read" if "disk_io_read" in self.metrics else "disk_io_write"
                data[key] = {"MB/s": round((read_speed if key == "disk_io_read" else write_speed) / (1024 * 1024), 2)}
                self._prev_disk = disk
            if "net_up" in self.metrics or "net_down" in self.metrics:
                net = psutil.net_io_counters()
                actual_dt = time.perf_counter() - tick_start or self.interval
                up_speed = (net.bytes_sent - self._prev_net.bytes_sent) / actual_dt
                down_speed = (net.bytes_recv - self._prev_net.bytes_recv) / actual_dt
                key = "net_up" if "net_up" in self.metrics else "net_down"
                data[key] = {"MB/s": round((up_speed if key == "net_up" else down_speed) / (1024 * 1024), 2)}
                self._prev_net = net
            if "audio" in self.metrics:
                # Audio recording blocks for the full interval by design
                data["audio"] = self._get_audio_level(self.interval, samplerate=8000)

            # 回调输出
            if self.callback:
                self.callback(data)

            # Sleep until the next absolute deadline, then advance it.
            # If we're already past the deadline, skip the sleep but still
            # advance so we don't try to catch up with a burst of sends.
            remaining = next_deadline - time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)
            next_deadline += self.interval


# -------------------- 仪表管理类 --------------------
class MeterManager:
    def __init__(self):
        self.sender = DataSender()
        self.setting = Setting()
        self.collector = DataCollector()
        self.extra_display_callback = None
        self.is_running = False

    def data_cb(self, data):
        try:
            data1 = data[self.collector.metrics[0]]
            data2 = data[self.collector.metrics[1]]
            print(f"[CPU] Sending data: {data1}, {data2}")
            self.sender.send_data(int(data1), int(data2))
            if self.extra_display_callback:
                self.extra_display_callback(data1, data2)
        except Exception as e:
            print(f"[CPU] Loop error: {e}")
            traceback.print_exc()

    def start(self, **kwargs):
        print("[APP] Starting MeterManager", self.setting.systemsetting.__dict__)
        self.collector.start(self.setting.systemsetting.interval, metrics=[self.setting.systemsetting.meter1, self.setting.systemsetting.meter2], callback=self.data_cb)
        self.sender.connect(self.setting.systemsetting.server_ip, 5000)
        self.is_running = True

    def stop(self):
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
    'title':  ('Segoe UI', 13, 'bold'),
    'value':  ('Segoe UI', 28, 'bold'),
    'card_h': ('Segoe UI', 8),
    'normal': ('Segoe UI', 10),
    'small':  ('Segoe UI', 9),
    'btn':    ('Segoe UI', 10, 'bold'),
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
    """Thin horizontal progress bar drawn on a Canvas."""

    def __init__(self, master, **kw):
        kw.setdefault('height', 3)
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
        if w <= 1:
            return
        # Background track
        self.create_rectangle(0, 0, w, 3, fill=THEME['border'], outline='')
        filled = int(w * self._value / 100)
        if filled > 0:
            v = self._value
            color = THEME['green'] if v < 70 else THEME['yellow'] if v < 90 else THEME['red']
            self.create_rectangle(0, 0, filled, 3, fill=color, outline='')


# -------------------- Settings Window --------------------

class SettingsWindow:
    """
    Modal settings popup for advanced options:
    - Sample interval
    - Per-meter max_duty calibration (with read/write from device)

    max_duty values are persisted back via the shared `max_duty` list.
    """

    def __init__(self, parent: tk.Tk, manager: MeterManager,
                 interval_var: tk.StringVar, max_duty: list):
        self._manager  = manager
        self._max_duty = max_duty   # shared [duty1, duty2] list with PulseMeterApp

        win = tk.Toplevel(parent)
        win.title("Settings")
        win.geometry("360x270")
        win.resizable(False, False)
        win.configure(bg=THEME['bg'])
        win.transient(parent)
        win.grab_set()
        self.win = win

        # --- Header ---
        hdr = tk.Frame(win, bg=THEME['surface'], height=44)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Settings", bg=THEME['surface'],
                 fg=THEME['text'], font=FONT['title']).pack(side='left', padx=16, pady=10)

        # --- Body ---
        body = tk.Frame(win, bg=THEME['bg'], padx=20, pady=14)
        body.pack(fill='both', expand=True)

        def lbl(text, row):
            tk.Label(body, text=text, bg=THEME['bg'],
                     fg=THEME['subtext'], font=FONT['small']
                     ).grid(row=row, column=0, sticky='w', pady=6)

        # Interval row
        lbl("Sample interval (s)", 0)
        ttk.Entry(body, textvariable=interval_var, width=10,
                  style='Dark.TEntry').grid(row=0, column=1, columnspan=3,
                                            sticky='ew', padx=(12, 0), pady=6)

        # Separator
        tk.Frame(body, bg=THEME['border'], height=1).grid(
            row=1, column=0, columnspan=4, sticky='ew', pady=(4, 8))

        # Max-duty rows for each meter
        specs = [
            (max_duty[0], "Meter 1  max duty"),
            (max_duty[1], "Meter 2  max duty"),
        ]
        for idx, (default, name) in enumerate(specs, start=1):
            lbl(name, idx + 1)
            spin = ttk.Spinbox(body, from_=1, to=4095, increment=1,
                               width=7, style='Dark.TSpinbox')
            spin.set(default)
            spin.grid(row=idx + 1, column=1, padx=(12, 4), pady=6)

            btn_r = _HoverButton(body, text="R", width=2,
                                 bg=THEME['card'], fg=THEME['accent'],
                                 font=FONT['small'], relief='flat', cursor='hand2',
                                 command=lambda i=idx, s=spin: self._read_duty(i, s))
            btn_r.grid(row=idx + 1, column=2, padx=2)

            btn_w = _HoverButton(body, text="W", width=2,
                                 bg=THEME['card'], fg=THEME['accent2'],
                                 font=FONT['small'], relief='flat', cursor='hand2',
                                 command=lambda i=idx, s=spin: self._write_duty(i, s))
            btn_w.grid(row=idx + 1, column=3, padx=2)

            if idx == 1:
                self._spin1, self._btn1_r, self._btn1_w = spin, btn_r, btn_w
            else:
                self._spin2, self._btn2_r, self._btn2_w = spin, btn_r, btn_w

        body.grid_columnconfigure(1, weight=1)

        # --- Footer ---
        footer = tk.Frame(win, bg=THEME['surface'], height=48)
        footer.pack(fill='x', side='bottom')
        footer.pack_propagate(False)
        _HoverButton(footer, text="Close", bg=THEME['accent'], hover_bg='#a6c8ff',
                     fg=THEME['bg'], font=FONT['btn'], relief='flat', cursor='hand2',
                     padx=20, command=self._on_close).pack(side='right', padx=16, pady=10)

    def _on_close(self):
        """Persist max_duty values back to shared list before closing."""
        for i, spin in enumerate([self._spin1, self._spin2]):
            try:
                self._max_duty[i] = int(float(spin.get()))
            except ValueError:
                pass
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
        self.root.geometry("460x360")
        self.root.resizable(False, False)
        self.root.configure(bg=THEME['bg'])
        self.manager = MeterManager()

        # Shared state owned here, referenced by SettingsWindow
        self._interval_var = tk.StringVar(value=str(self.manager.setting.systemsetting.interval))
        self._max_duty = [448, 236]   # [meter1, meter2]

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

        # Combobox dropdown list colours (tk option database)
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
        hdr = tk.Frame(self.root, bg=THEME['surface'], height=48)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)

        tk.Label(hdr, text="PULSEMETER", bg=THEME['surface'],
                 fg=THEME['accent'], font=FONT['title']).pack(side='left', padx=18, pady=12)

        # Status indicator dot (green = running, red = idle)
        self._dot_cv = tk.Canvas(hdr, width=10, height=10,
                                 bg=THEME['surface'], highlightthickness=0)
        self._dot_cv.pack(side='right', padx=(0, 14), pady=19)
        self._dot = self._dot_cv.create_oval(1, 1, 9, 9, fill=THEME['red'], outline='')

        # Settings gear button
        _HoverButton(hdr, text="⚙", bg=THEME['surface'], hover_bg=THEME['border'],
                     fg=THEME['subtext'], font=('Segoe UI', 14),
                     relief='flat', cursor='hand2', padx=4,
                     command=self._open_settings).pack(side='right', padx=2, pady=8)

        # === Metric cards ===
        cards = tk.Frame(self.root, bg=THEME['bg'])
        cards.pack(fill='both', expand=True, padx=16, pady=14)
        cards.grid_columnconfigure(0, weight=1)
        cards.grid_columnconfigure(1, weight=1)

        self.combo1, self._val1, self._prog1 = self._build_card(
            cards, col=0, title="METER 1",
            default=self.manager.setting.systemsetting.meter1)
        self.combo2, self._val2, self._prog2 = self._build_card(
            cards, col=1, title="METER 2",
            default=self.manager.setting.systemsetting.meter2)

        # === Connection bar ===
        conn = tk.Frame(self.root, bg=THEME['surface'], height=60)
        conn.pack(fill='x', side='bottom')
        conn.pack_propagate(False)

        bar = tk.Frame(conn, bg=THEME['surface'])
        bar.pack(fill='both', expand=True, padx=16, pady=10)

        tk.Label(bar, text="IP", bg=THEME['surface'],
                 fg=THEME['subtext'], font=FONT['small']).pack(side='left', padx=(0, 6))

        self.ip_combo = ttk.Combobox(bar, width=18, style='Dark.TCombobox')
        self.ip_combo.set(self.manager.setting.systemsetting.server_ip)
        self.ip_combo.pack(side='left', padx=(0, 4))

        _HoverButton(bar, text="↻", bg=THEME['surface'], hover_bg=THEME['border'],
                     fg=THEME['subtext'], font=('Segoe UI', 14),
                     relief='flat', cursor='hand2',
                     command=self._rescan_devices).pack(side='left', padx=(0, 12))

        self._connect_btn = _HoverButton(
            bar, text="Connect  ▶",
            bg=THEME['accent'], hover_bg='#a6c8ff',
            fg=THEME['bg'], font=FONT['btn'],
            relief='flat', cursor='hand2', padx=14,
            command=self.toggle_start)
        self._connect_btn.pack(side='right')

    def _build_card(self, parent: tk.Frame, col: int, title: str, default: str):
        """Build and grid a single metric card. Returns (combo, value_label, progress_bar)."""
        padx = (0, 8) if col == 0 else (8, 0)
        card = tk.Frame(parent, bg=THEME['card'],
                        highlightbackground=THEME['border'], highlightthickness=1)
        card.grid(row=0, column=col, sticky='nsew', padx=padx)

        inner = tk.Frame(card, bg=THEME['card'], padx=14, pady=12)
        inner.pack(fill='both', expand=True)

        tk.Label(inner, text=title, bg=THEME['card'],
                 fg=THEME['subtext'], font=FONT['card_h']).pack(anchor='w')

        combo = ttk.Combobox(inner, values=self.manager.collector.get_available_metrics(),
                             width=15, state='readonly', style='Dark.TCombobox')
        combo.set(default)
        combo.pack(fill='x', pady=(6, 0))

        val_lbl = tk.Label(inner, text="—", bg=THEME['card'],
                           fg=THEME['accent'], font=FONT['value'])
        val_lbl.pack(pady=(10, 0))

        prog = _ProgressBar(inner, bg=THEME['card'])
        prog.pack(fill='x', pady=(8, 0))

        return combo, val_lbl, prog

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _open_settings(self):
        SettingsWindow(self.root, self.manager, self._interval_var, self._max_duty)

    def _on_devices_changed(self):
        """Called from the mDNS worker thread — marshal update to main thread."""
        devices = self.discovery.get_devices()
        values  = [ip for _, ip in devices]

        def update():
            self.ip_combo['values'] = values
            # Auto-select the first discovered device when the field is empty
            if values and not self.ip_combo.get():
                self.ip_combo.set(values[0])

        self.root.after(0, update)

    def _rescan_devices(self):
        """Restart mDNS discovery and clear stale device list."""
        self.ip_combo['values'] = []
        self.discovery.start()

    @staticmethod
    def _fmt(v) -> tuple:
        """Return (display_str, progress_pct 0–100) for a raw metric value."""
        if isinstance(v, dict):
            mb = v.get('MB/s', 0.0)
            return f"{mb:.1f}", min(mb * 20.0, 100.0)   # 5 MB/s → 100 %
        try:
            f = float(v)
            return f"{f:.1f}", f
        except (TypeError, ValueError):
            return "—", 0.0

    def update_meter_label(self, meter1, meter2):
        """Collector thread callback — must marshal to the main thread."""
        def _update():
            for val, lbl, prog in [
                (meter1, self._val1, self._prog1),
                (meter2, self._val2, self._prog2),
            ]:
                text, pct = self._fmt(val)
                lbl.config(text=text)
                prog.set_value(pct)

        self.root.after(0, _update)

    def _set_connected(self, connected: bool):
        if connected:
            self._dot_cv.itemconfig(self._dot, fill=THEME['green'])
            self._connect_btn._normal_bg = THEME['red']
            self._connect_btn._hover_bg  = '#ffa0b0'
            self._connect_btn.config(text="Disconnect  ■",
                                     bg=THEME['red'], fg=THEME['bg'])
        else:
            self._dot_cv.itemconfig(self._dot, fill=THEME['red'])
            self._connect_btn._normal_bg = THEME['accent']
            self._connect_btn._hover_bg  = '#a6c8ff'
            self._connect_btn.config(text="Connect  ▶",
                                     bg=THEME['accent'], fg=THEME['bg'])

    def toggle_start(self):
        if self.manager.is_running:
            self.manager.stop()
            self.manager.set_extra_display_callback(None)
            self._set_connected(False)
            print("[APP] stopped")
        else:
            self.manager.setting.systemsetting.server_ip = self.ip_combo.get()
            try:
                self.manager.setting.systemsetting.interval = float(self._interval_var.get())
            except ValueError:
                pass
            self.manager.setting.systemsetting.meter1 = self.combo1.get()
            self.manager.setting.systemsetting.meter2 = self.combo2.get()
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
            Image.open(ROOT / "icon.png"),
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
        app = PulseMeterApp(root)
        tray = TrayApp(root, app)
        tray.run()
        root.mainloop()
