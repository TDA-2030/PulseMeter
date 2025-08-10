import tkinter as tk
from tkinter import ttk
import yaml
import time
import os
import threading
import socket
import struct
import psutil
import sounddevice as sd
import sys
import traceback
import pystray
from PIL import Image
from pathlib import Path

ROOT = Path(os.path.abspath(__file__)).parent
print(ROOT)
CONFIG_FILE = "_config.yaml"
DEFAULT_CONFIG = {
    "server_ip": "192.168.124.7",
    "meter1": "CPU",
    "meter2": "CPU",
    "net_dev": "eth0",
    "interval": 1.0,
}

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


# -------------------- 仪表管理类 --------------------
class MeterManager:
    def __init__(self):
        self.running_event = threading.Event()
        self.last_network_recv = 0
        self.last_network_sent = 0
        self.sender = DataSender()
        self.thread = None
        self.extra_display_callback = None

        self.data_sources = {"CPU" : self._get_cpu_percent, 
                             "网络上传速率": self._get_network_speed,
                             "网络下载速率": self._get_network_speed}

    def _get_cpu_percent(self):
        return psutil.cpu_percent()

    def _get_network_speed(self, interface: str, interval: float = 1.0):
        counters = psutil.net_io_counters(pernic=True)
        if interface not in counters:
            return 0, 0
        sent = counters[interface].bytes_sent
        recv = counters[interface].bytes_recv
        if self.last_network_recv == 0:
            self.last_network_recv = recv
            self.last_network_sent = sent
        upload_speed = (sent - self.last_network_sent) / interval / 1024 * 8
        download_speed = (recv - self.last_network_recv) / interval / 1024 * 8
        self.last_network_recv = recv
        self.last_network_sent = sent
        return download_speed

    def _loop(self, interval, source1, source2):
        while self.running_event.is_set():
            try:
                print(f"[CPU] Looping with interval {interval}, source1 {source1}, source2 {source2}")
                time.sleep(float(interval))
                data1 = self.data_sources[source1]()
                if source1 != source2:
                    self.data_sources[source2]()
                else:
                    data2 = data1
                print(f"[CPU] Sending data: {data1}, {data2}")
                if not self.sender.send_data(int(data1), int(data2)):
                    break
                if self.extra_display_callback:
                    self.extra_display_callback(data1, data2)
            except Exception as e:
                print(f"[CPU] Loop error: {e}")
                traceback.print_exc()
                break
        self.running_event.clear()

    def start(self, server_ip, interval, meter1, meter2, **kwargs):
        if not self.running_event.is_set():
            self.sender.connect(server_ip, 5000)
            self.running_event.set()
            self.thread = threading.Thread(target=self._loop, args=(interval, meter1, meter2), daemon=True).start()

    def stop(self):
        self.running_event.clear()
        if self.thread:
            self.thread.join()
            self.sender.send_data(0, 0)
            self.sender.close()
            self.thread = None

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

        self.config = self.load_config()

        # 设置风格和字体
        style = ttk.Style()
        style.theme_use('clam')  # 选择更现代的主题
        default_font = ("Segoe UI", 11)
        style.configure('.', font=default_font)
        style.configure('TLabel', padding=6)
        style.configure('TButton', padding=6)
        style.configure('TCombobox', padding=4)
        style.configure('TSpinbox', padding=4)

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
        self.combo1 = ttk.Combobox(left_frame, values=list(self.manager.data_sources.keys()), width=combo_width, state="readonly")
        self.combo1.set(self.config.get("meter1", "CPU"))
        self.combo1.grid(row=0, column=0, pady=5)
        self.meter_lebel1 = ttk.Label(left_frame, text="0")
        self.meter_lebel1.grid(row=1, column=0, sticky="e")


        self.combo2 = ttk.Combobox(right_frame, values=list(self.manager.data_sources.keys()), width=combo_width, state="readonly")
        self.combo2.set(self.config.get("meter2", "CPU"))
        self.combo2.grid(row=0, column=0, pady=5)
        self.meter_lebel2 = ttk.Label(right_frame, text="0")
        self.meter_lebel2.grid(row=1, column=0, sticky="e")

        # 下栏，使用grid分布4列，间距合理
        ttk.Label(bottom_frame, text="服务器 IP:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.ip_entry = ttk.Entry(bottom_frame, width=18)
        self.ip_entry.insert(0, self.config.get("server_ip", "127.0.0.1"))
        self.ip_entry.grid(row=0, column=1, sticky="ew", padx=(0, 15))

        ttk.Label(bottom_frame, text="采样间隔(s):").grid(row=1, column=0, sticky="w", padx=(0, 5))
        self.value_spin = ttk.Spinbox(bottom_frame, from_=0.02, to=3, increment=0.1, width=8)
        self.value_spin.set(self.config.get("interval", 1))
        self.value_spin.grid(row=1, column=1, sticky="ew", padx=(0, 15))

        self.start_button = ttk.Button(bottom_frame, text="启动", command=self.toggle_start)
        self.start_button.grid(row=0, column=4, sticky="e")

        bottom_frame.grid_columnconfigure(1, weight=1)
        bottom_frame.grid_columnconfigure(3, weight=0)

        # 给整个root设置统一背景色（需要导入tkinter的Style才能控制更细节，这里用root配置）
        root.configure(bg="#f0f0f0")

    def update_meter_label(self, meter1, meter2):
        self.meter_lebel1.config(text=str(meter1))
        self.meter_lebel2.config(text=str(meter2))

    def toggle_start(self):
        if self.manager.running_event.is_set():
            self.manager.stop()
            self.start_button.config(text="启动")
            print("[APP] 停止运行")
        else:
            self.save_config()
            self.manager.start(
                server_ip=self.ip_entry.get(),
                interval=float(self.value_spin.get()),
                meter1=self.combo1.get(),
                meter2=self.combo2.get()
            )
            self.manager.set_extra_display_callback(self.update_meter_label)
            self.start_button.config(text="停止")
            print("[APP] 开始运行")

    @staticmethod
    def load_config():
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or DEFAULT_CONFIG.copy()
        else:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                yaml.safe_dump(DEFAULT_CONFIG, f, allow_unicode=True)
            return DEFAULT_CONFIG.copy()

    def save_config(self):
        self.config["server_ip"] = self.ip_entry.get()
        self.config["meter1"] = self.combo1.get()
        self.config["meter2"] = self.combo2.get()
        self.config["interval"] = float(self.value_spin.get())
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.config, f, allow_unicode=True)


class TrayApp:
    def __init__(self, root, app):
        self.root:tk.Tk = root
        self.app:PulseMeterApp = app
        self.icon = pystray.Icon("PulseMeter", Image.open(ROOT/"icon.png"), "PulseMeter", menu=pystray.Menu(
            pystray.MenuItem('显示主界面', self.show_window, default=True),
            pystray.MenuItem('退出', self.exit_app)
        ))

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
        cfg = PulseMeterApp.load_config()
        manager = MeterManager()
        manager.start(**cfg)
        while True:
            time.sleep(1)
    else:
        root = tk.Tk()
        app = PulseMeterApp(root)
        tray = TrayApp(root, app)
        tray.run()
        root.mainloop()