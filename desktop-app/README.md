# PulseMeter Desktop App

Python 桌面客户端，用于发现 PulseMeter 设备、选择指标并驱动两根仪表指针。

## 你可以在这里做什么

- 本地开发和调试桌面客户端
- 直接运行源码版本的 App
- 打包为便携可执行文件

## 开发运行

```bash
cd desktop-app
python -m venv .venv
. .venv/bin/activate
pip install -e .
python -m pulsemeter_desktop
```

如果你在 Windows PowerShell 中运行，激活命令改为：

```powershell
.venv\Scripts\Activate.ps1
```

应用会将用户设置保存在系统配置目录中，而不是仓库内。

首次启动后，在 GUI 中填写设备 IP，或等待 mDNS 自动发现；为两根指针分别选择系统指标后即可开始驱动仪表。

## Windows 硬件监控

如果你想在仪表里显示 CPU/GPU/硬盘温度、GPU 负载或风扇转速，可以接入 LibreHardwareMonitor：

1. 安装 Windows 依赖：

```powershell
cd desktop-app
pip install -e .
```

2. 从 LibreHardwareMonitor 官方发布包中取出 `LibreHardwareMonitorLib.dll`，放到固定目录：

```text
desktop-app/src/pulsemeter_desktop/vendor/librehardwaremonitor/LibreHardwareMonitorLib.dll
```

如果发布包里还有 `LibreHardwareMonitorLib.xml`，也建议一起放进去，便于后续查阅传感器说明，但运行时只依赖 DLL。

3. 重新启动应用。Windows 下如果 DLL 成功加载，指标列表里会出现：

- `CPU Temp`
- `CPU Power`
- `CPU Clock`
- `CPU Voltage`
- `GPU Temp`
- `GPU Load`
- `GPU Power`
- `GPU Core Clock`
- `GPU Memory Clock`
- `GPU Memory Load`
- `SSD Temp`
- `Mainboard Temp`
- `Fan Speed`

LibreHardwareMonitor 官方 README 给出的集成方式核心是：

- 创建 `Computer`
- 打开 `IsCpuEnabled` / `IsGpuEnabled` / `IsStorageEnabled` 等开关
- `Open()` 后定期 `Update()` 硬件树并读取 `Sensors`

本项目已经按这个模式封装成可选 provider，并挂进现有 `DataCollector` 轮询流程。

注意：

- 这部分仅在 Windows 上启用。
- 某些主板/风扇/温度传感器需要管理员权限才能读到。
- 如果选中了硬件指标但读不到值，应用会显示 `—` 并在底部提示尝试用管理员权限启动。
- 仓库不会让用户在运行时手动配置 DLL 路径；只认上面的固定 vendor 目录。

## 打包

```bash
cd desktop-app
python scripts/build.py          # 单文件可执行程序
python scripts/build.py --onedir # 目录包，启动更快
```

## 相关文档

- 设备端烧录和源码构建见 [固件文档](../firmware/README.md)
- 项目总览见 [根 README](../README.md)
