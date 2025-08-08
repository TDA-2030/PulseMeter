import socket
import psutil
import time
import struct

HOST = '192.168.124.7'  # ESP32 IP
PORT = 5000

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print("尝试连接到 ESP32...")
        sock.connect((HOST, PORT))
        print(f"已连接到 ESP32 {HOST}:{PORT}")

        while True:
            cpu_percent = int(psutil.cpu_percent(interval=1))  # 0~100
            packet = struct.pack("!BBBb", 0x23, 0x35, 1, cpu_percent)
            sock.sendall(packet)
            print(f"发送二进制: {packet.hex()} (CPU={cpu_percent}%)")

    except KeyboardInterrupt:
        print("用户终止程序")
    except Exception as e:
        print(f"错误: {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    main()
