# PulseMeter

![logo](desktop-app/src/pulsemeter_desktop/assets/logo.png)


[![ESP32-C3](https://img.shields.io/badge/ESP32--C3-ESP--IDF%205.x-blue?logo=espressif)](https://docs.espressif.com/projects/esp-idf/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

PulseMeter 使用 ESP32-C3 通过 PWM 驱动两个指针式仪表，实时显示 CPU 占用、内存、音频电平等系统指标，做成一个赛博朋克风格的桌面小摆件。

## 开始之前

PulseMeter 由三部分组成：

- [固件说明](firmware/README.md)：烧录 ESP32-C3、从源码构建固件、配置网络
- [桌面客户端](desktop-app/README.md)：本地开发、运行和打包桌面 App
- [硬件资料](hardware/README.md)：结构件和硬件相关文件

## 特性

- **双通道** — 两个独立指针，可分配任意指标组合
- **低延迟** — TCP 直连，PWM 实时响应
- **多指标** — CPU、内存、磁盘、网络、音频电平随意切换
- **桌面客户端** — Tkinter GUI + 系统托盘，最小化后台运行
- **自动发现** — 局域网内自动找到设备，无需手填 IP

## 硬件

| 组件 | 说明 |
|---|---|
| ESP32-C3 开发板 | 主控，运行 TCP 服务器 |
| 指针式仪表头 × 2 | 电压表 / 电流表表头均可，PWM 驱动 |
| 局域网 | 电脑与 ESP32 同一网络 |

## 快速开始

🚀 适合快速体验，浏览器连接开发板后即可直接刷写。

1. 🔥 烧录固件

    <a href="https://espressif.github.io/esp-launchpad/?flashConfigURL=https://raw.githubusercontent.com/TDA-2030/PulseMeter/refs/heads/master/firmware/config.toml">
        <img alt="使用ESP Launchpad一键烧录！" src="https://esp.eterill.xyz/assets/try_with_launchpad.png" width="250" height="70">
    </a>

    或查看 [固件说明](firmware/README.md)，从源码构建和烧录。

2. 🖥️ 启动桌面客户端

    从 [Releases](https://github.com/TDA-2030/PulseMeter/releases) 下载桌面客户端
    或按照 [桌面客户端说明](desktop-app/README.md) 安装依赖并启动 App。

3. 📶 配置网络

    设备首次启动后，未配置网络会自动进入配置模式，两个指针会来回摆动，此时连接设备的热点 `PulseMeter`，打开浏览器访问 `http://192.168.4.1`，按照提示配置 WiFi 和参数，点击保存后设备会自动重启并连接到 WiFi。

4. 🔗 连接设备

   首次启动后等待设备自动发现，当设备未被发现时，点击设置⚙️ 按钮，在 GUI 中填入设备 IP，点击连接。
