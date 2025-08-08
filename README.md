# PulseMeter

PulseMeter 是一个基于 ESP32 的实时 CPU 利用率指针仪表显示项目。通过 TCP 通信，PulseMeter 能够连接电脑，接收并显示 CPU 负载，采用指针仪表风格的视觉效果，直观反映系统性能状态。

## 特性

- 实时显示电脑 CPU 利用率  
- 基于 ESP32 的 TCP 服务器，稳定接收数据  
- 采用指针式仪表界面，简单易读  
- Python 客户端程序，跨平台获取 CPU 负载数据  
- 支持二进制数据包传输，通信高效可靠  

## 硬件需求

- ESP32 开发板  
- 指针式仪表（例如电压表表头）  
- 局域网内可连接的电脑  

## 软件需求

- ESP-IDF 开发环境（版本 4.x 或更高）  
- Python 3（用于运行 CPU 利用率发送脚本）  
- Python 库：`psutil` （安装命令：`pip install psutil`）

## 快速开始

### 1. 配置并运行 ESP32 端



### 2. 运行 Python 客户端脚本

```bash
pip install psutil
python cpu_load_sender.py
