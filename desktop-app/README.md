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

## 打包

```bash
cd desktop-app
python scripts/build.py          # 单文件可执行程序
python scripts/build.py --onedir # 目录包，启动更快
```

## 相关文档

- 设备端烧录和源码构建见 [固件文档](../firmware/README.md)
- 项目总览见 [根 README](../README.md)
