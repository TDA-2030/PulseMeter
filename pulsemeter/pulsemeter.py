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

ROOT = Path(os.path.abspath(__file__)).parent
print(ROOT)


# -------------------- 数据发送类 --------------------
class DataSender:
    def __init__(self):
        self.sock = None
        self.host = None
        self.port = None

    def connect(self, host: str, port: int):
        self.host = host
        self.port = port
        try:
            print(f"[TCP] Connecting to {host}:{port}")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock.settimeout(2)
            self.sock.connect((host, port))
            return True
        except Exception as e:
            print(f"[TCP] Connection failed: {e}")
            self.sock = None
            return False

    def send_data(self, data1, data2) -> bool:
        if not self.sock:
            return False
        try:
            packet = struct.pack("!BBBbb", 0x23, 0x35, 2, data1, data2)
            self.sock.sendall(packet)
            return True
        except Exception as e:
            print(f"[TCP] Send failed: {e}")
            return False

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self.sock = None


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
        while not self._stop_event.is_set():
            start_time = time.time()
            data = {}

            # 常规指标
            if "cpu" in self.metrics:
                data["cpu"] = psutil.cpu_percent(interval=None)
            if "memory" in self.metrics:
                mem = psutil.virtual_memory()
                data["memory"] = mem.percent
            if "disk_io_read" in self.metrics or "disk_io_write" in self.metrics:
                disk = psutil.disk_io_counters()
                read_speed = (disk.read_bytes - self._prev_disk.read_bytes) / self.interval
                write_speed = (disk.write_bytes - self._prev_disk.write_bytes) / self.interval
                key = "disk_io_read" if "disk_io_read" in self.metrics else "disk_io_write"
                data[key] = {"MB/s": round((read_speed if key == "disk_io_read" else write_speed) / (1024 * 1024), 2)}
                self._prev_disk = disk
            if "net_up" in self.metrics or "net_down" in self.metrics:
                net = psutil.net_io_counters()
                up_speed = (net.bytes_sent - self._prev_net.bytes_sent) / self.interval
                down_speed = (net.bytes_recv - self._prev_net.bytes_recv) / self.interval
                key = "net_up" if "net_up" in self.metrics else "net_down"
                data[key] = {"MB/s": round((up_speed if key == "net_up" else down_speed) / (1024 * 1024), 2)}
                self._prev_net = net
            if "audio" in self.metrics:
                # 在 interval 内采样音频
                data["audio"] = self._get_audio_level(self.interval, samplerate=8000)

            # 回调输出
            if self.callback:
                self.callback(data)
            # 确保周期稳定
            elapsed = time.time() - start_time
            if elapsed < self.interval:
                print(f"[CPU] Sleeping for {self.interval - elapsed:.2f} seconds")
                time.sleep(self.interval - elapsed)


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


# -------------------- GUI 类 --------------------
class PulseMeterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PulseMeter")
        self.root.geometry("480x260")
        self.root.resizable(False, False)
        self.manager = MeterManager()

        # 设置风格和字体
        style = ttk.Style()
        style.theme_use("clam")  # 选择更现代的主题
        default_font = ("Segoe UI", 11)
        style.configure(".", font=default_font)
        style.configure("TLabel", padding=6)
        style.configure("TButton", padding=6)
        style.configure("TCombobox", padding=4)
        style.configure("TSpinbox", padding=4)

        # 用grid布局上下分栏，上栏左右分栏
        top_frame = ttk.Frame(root, padding=10)
        top_frame.grid(row=0, column=0, sticky="nsew")
        bottom_frame = ttk.Frame(root, padding=10)
        bottom_frame.grid(row=1, column=0, sticky="ew")

        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)

        # 左右两个分区，宽度均分
        left_frame = ttk.LabelFrame(top_frame, text="表头 1 设置", padding=10)
        right_frame = ttk.LabelFrame(top_frame, text="表头 2 设置", padding=10)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        top_frame.grid_columnconfigure(0, weight=1)
        top_frame.grid_columnconfigure(1, weight=1)

        # 下拉框宽度统一
        combo_width = 18
        self.combo1 = ttk.Combobox(left_frame, values=list(self.manager.collector.get_available_metrics()), width=combo_width, state="readonly")
        self.combo1.set(self.manager.setting.systemsetting.meter1)
        self.combo1.grid(row=0, column=0, pady=5)
        self.meter_lebel1 = ttk.Label(left_frame, text="0")
        self.meter_lebel1.grid(row=1, column=0, sticky="e")

        self.combo2 = ttk.Combobox(right_frame, values=list(self.manager.collector.get_available_metrics()), width=combo_width, state="readonly")
        self.combo2.set(self.manager.setting.systemsetting.meter2)
        self.combo2.grid(row=0, column=0, pady=5)
        self.meter_lebel2 = ttk.Label(right_frame, text="0")
        self.meter_lebel2.grid(row=1, column=0, sticky="e")

        # 下栏，使用grid分布4列，间距合理
        ttk.Label(bottom_frame, text="服务器 IP:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.ip_entry = ttk.Entry(bottom_frame, width=18)
        self.ip_entry.insert(0, self.manager.setting.systemsetting.server_ip)
        self.ip_entry.grid(row=0, column=1, sticky="ew", padx=(0, 15))

        ttk.Label(bottom_frame, text="采样间隔(s):").grid(row=1, column=0, sticky="w", padx=(0, 5))
        self.value_spin = ttk.Spinbox(bottom_frame, from_=0.02, to=3, increment=0.1, width=8)
        self.value_spin.set(self.manager.setting.systemsetting.interval)
        self.value_spin.grid(row=1, column=1, sticky="ew", padx=(0, 15))

        self.start_button = ttk.Button(bottom_frame, text="启动", command=self.toggle_start)
        self.start_button.grid(row=0, column=4, sticky="e")

        bottom_frame.grid_columnconfigure(1, weight=1)
        bottom_frame.grid_columnconfigure(3, weight=0)

        # 给整个root设置统一背景色（需要导入tkinter的Style才能控制更细节，这里用root配置）
        root.configure(bg="#f0f0f0")

    def update_meter_label(self, meter1, meter2):
        self.meter_lebel1.after(0, lambda meter1=meter1: self.meter_lebel1.config(text=str(meter1)))
        self.meter_lebel2.after(0, lambda meter2=meter2: self.meter_lebel2.config(text=str(meter2)))


    def toggle_start(self):
        if self.manager.is_running:
            self.manager.stop()
            self.start_button.config(text="启动")
            print("[APP] 停止运行")
        else:
            self.manager.setting.systemsetting.server_ip = self.ip_entry.get()
            self.manager.setting.systemsetting.interval = float(self.value_spin.get())
            self.manager.setting.systemsetting.meter1 = self.combo1.get()
            self.manager.setting.systemsetting.meter2 = self.combo2.get()
            self.manager.setting.save(self.manager.setting.save_filename)
            self.manager.start()
            # self.manager.set_extra_display_callback(self.update_meter_label)
            self.start_button.config(text="停止")
            print("[APP] 开始运行")


class TrayApp:
    def __init__(self, root, app):
        self.root: tk.Tk = root
        self.app: PulseMeterApp = app
        self.icon = pystray.Icon(
            "PulseMeter",
            Image.open(ROOT / "icon.png"),
            "PulseMeter",
            menu=pystray.Menu(pystray.MenuItem("显示主界面", self.show_window, default=True), pystray.MenuItem("退出", self.exit_app)),
        )

    def run(self):
        # 启动托盘图标线程
        threading.Thread(target=self.icon.run, daemon=True).start()
        # 窗口关闭时隐藏
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

    def hide_window(self):
        self.root.withdraw()

    def show_window(self, icon=None, item=None):
        self.root.deiconify()
        self.root.after(0, self.root.focus_force)

    def exit_app(self, icon, item):
        self.icon.stop()
        self.app.manager.stop()
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
