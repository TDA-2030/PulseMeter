# PulseMeter

<div align="center">

![logo](desktop-app/src/pulsemeter_desktop/assets/logo.png)

**把电脑负载变成一根会动的表针**

[![ESP32-C3](https://img.shields.io/badge/ESP32--C3-ESP--IDF%205.x-blue?logo=espressif)](https://docs.espressif.com/projects/esp-idf/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

ESP32-C3 通过 PWM 驱动两根指针式仪表，实时显示 CPU 占用、内存、音频电平等系统指标——一个赛博朋克风格的桌面小摆件。

## 效果预览

> *两根模拟表针，数值升高时针头跳动，就像老式 VU 表一样。*

## 特性

- **双通道** — 两根独立指针，可分配任意指标组合
- **低延迟** — TCP 直连，PWM 实时响应
- **多指标** — CPU、内存、温度、网络、音频电平随意切换
- **桌面客户端** — Tkinter GUI + 系统托盘，最小化后台运行
- **mDNS 发现** — 局域网内自动找到设备，无需手填 IP
- **Web 配置页** — 通过浏览器修改 WiFi 和参数，无需重新烧录

## 硬件

| 组件 | 说明 |
|---|---|
| ESP32-C3 开发板 | 主控，运行 TCP 服务器 |
| 指针式仪表头 × 2 | 电压表 / 电流表表头均可，PWM 驱动 |
| 局域网 | 电脑与 ESP32 同一网络 |

## 快速开始

**烧录固件**

```bash
cd firmware
idf.py set-target esp32c3
idf.py build flash monitor
```

**运行客户端**

```bash
cd desktop-app
pip install -e .
python -m pulsemeter_desktop
```

首次启动后在 GUI 中填入设备 IP（或等待 mDNS 自动发现），选择每根针对应的指标，保存即生效。

## 打包为可执行文件

```bash
cd desktop-app
python scripts/build.py          # 生成单文件可执行程序
python scripts/build.py --onedir # 生成目录包（启动更快）
```

## TCP 数据包格式

```
0x23  0x35  0x02  <meter1: 0–100>  <meter2: 0–100>
```

5 字节二进制帧，Python 端 `struct.pack("!BBBbb", 0x23, 0x35, 2, v1, v2)`。

## GPIO 引脚（ESP32-C3）

| 功能 | GPIO |
|---|---|
| 仪表 1 PWM | 5 |
| 仪表 2 PWM | 6 |
| LED 红 | 10 |
| LED 绿 | 1 |
| I2C SDA / SCL | 2 / 3 |
