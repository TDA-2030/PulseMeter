import socket
import struct
import time
import psutil
import sounddevice as sd
import numpy as np
import threading


class CPULoadSender:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        print(f"[CPU] Connected to {self.host}:{self.port}")

    


class AudioLevelSender:
    def __init__(self, host: str, port: int, samplerate: int = 8000, blocksize: int = 512):
        self.host = host
        self.port = port
        self.sock = None
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.stream = None
        self.running = False

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 关闭 Nagle 算法，降低延迟
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock.connect((self.host, self.port))
        print(f"[Audio] Connected to {self.host}:{self.port}")

    def send_data(self, data1, data2) -> bool:
        # 按协议打包：0x23, 0x35, 长度, 数据
        packet = struct.pack("!BBBbb", 0x23, 0x35, 2, data1, data2)
        try:
            self.sock.sendall(packet)
            print(f"Sent data: {data1}, {data2}")
            return True
        except BrokenPipeError:
            return False

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print("[Audio] Status:", status)

        # 计算 RMS（音量等级 0~100）
        rms = np.sqrt(np.mean(np.square(indata)))
        level = min(int(rms * 7000), 100)  # 缩放到 0~100

        if(self.send_data(level, 0) == False):
            self.running = False

    def start(self):
        self.running = True
        self.stream = sd.InputStream(
            device=1,
            channels=1,
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            callback=self._audio_callback
        )
        self.stream.start()
        print("[Audio] Started.")

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()

    def send_cpu_load(self):
        while True:
            cpu_percent = int(psutil.cpu_percent(interval=0.6))  # 0~100
            self.send_data(cpu_percent, 0)


if __name__ == "__main__":
    HOST = "192.168.124.7"  # ESP32 的 IP
    PORT_CPU = 5000         # CPU 数据端口
    PORT_AUDIO = 5000       # 音频数据端口
    print(sd.query_devices())
    # exit()

    audio_sender = AudioLevelSender(HOST, PORT_AUDIO)
    audio_sender.connect()
    audio_sender.send_cpu_load()
    exit()
    # audio_sender.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        audio_sender.stop()
        print("Stopped.")
