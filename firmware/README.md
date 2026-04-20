# PulseMeter Firmware

ESP32-C3 固件负责接收桌面端发送的系统指标，并通过 PWM 驱动两根指针式仪表。

## 你可以在这里做什么

- 在线一键烧录到开发板
- 使用 ESP-IDF 从源码构建和刷写固件
- 查看设备端的大致工作方式和引脚分配

## 从源码构建

### 环境要求

- ESP-IDF v5.5
- ESP32-C3 开发板

### 构建与烧录

```bash
cd firmware
idf.py set-target esp32c3
idf.py build
idf.py flash monitor
```

如果已经设置过 target，后续通常只需要执行：

```bash
cd firmware
idf.py build flash monitor
```

## 配置与联调

烧录完成后，设备会运行 TCP 服务，等待桌面客户端连接并发送双通道表针数据。

- 桌面端开发、运行和打包说明见 [桌面客户端文档](../desktop-app/README.md)
- 根项目概览见 [README](../README.md)

## GPIO 引脚

| 功能 | GPIO |
|---|---|
| 仪表 1 PWM | 5 |
| 仪表 2 PWM | 6 |
| LED 红 | 10 |
| LED 绿 | 1 |
| I2C SDA / SCL | 2 / 3 |



## TCP 数据包格式

PulseMeter 使用自定义二进制帧协议，通过 TCP `5000` 端口通信，不再是早期的 5 字节裸数据格式。

### 通用帧结构

所有数值均按大端序编码：

```text
magic[2]  type[1]  seq[1]  len[2]  payload[len]  crc8[1]
```

| 字段 | 长度 | 说明 |
|---|---:|---|
| `magic` | 2 | 固定为 `0x23 0x35` |
| `type` | 1 | 消息类型 |
| `seq` | 1 | 序号；`0` 表示单向发送，不期待响应 |
| `len` | 2 | 负载长度，大端序 |
| `payload` | 可变 | 消息体 |
| `crc8` | 1 | `type ^ seq ^ len_hi ^ len_lo ^ payload...` 的逐字节异或结果 |

### 消息类型

| `type` | 方向 | 含义 |
|---|---|---|
| `0x01` | Host → Device | `MSG_STREAM`，推送两路表针数值，不返回响应 |
| `0x02` | Host → Device | `MSG_READ_REQ`，读取设备参数 |
| `0x03` | Device → Host | `MSG_READ_RSP`，返回参数值 |
| `0x04` | Host → Device | `MSG_WRITE_REQ`，写入设备参数 |
| `0x05` | Device → Host | `MSG_WRITE_RSP`，返回写入结果 |

### `MSG_STREAM` 实时表针数据

负载固定为 2 字节：

```text
meter1[1]  meter2[1]
```

- `meter1`：第 1 根指针的百分比，范围 `0-100`
- `meter2`：第 2 根指针的百分比，范围 `0-100`
- `seq` 固定为 `0`

示例：

```text
23 35 01 00 00 02 32 64 55
```

含义：

- `23 35`：魔数
- `01`：`MSG_STREAM`
- `00`：单向帧
- `00 02`：负载长度为 2
- `32 64`：两路数据分别为 `50` 和 `100`
- `55`：CRC8

### `MSG_READ_REQ` / `MSG_READ_RSP`

读取请求负载：

```text
param_id[2]
```

读取响应负载：

```text
param_id[2]  status[1]  value[4]
```

### `MSG_WRITE_REQ` / `MSG_WRITE_RSP`

写入请求负载：

```text
param_id[2]  value[4]
```

写入响应负载：

```text
param_id[2]  status[1]
```

### 状态码

| `status` | 含义 |
|---|---|
| `0x00` | 成功 |
| `0x01` | 通用错误，例如写入只读参数 |
| `0x02` | 未知参数 ID |

### 参数 ID

| 参数 | ID | 类型 | 说明 |
|---|---:|---|---|
| `PARAM_METER1_MAX_DUTY` | `0x0001` | `uint32` | 仪表 1 的 PWM 占空比上限，可读写 |
| `PARAM_METER2_MAX_DUTY` | `0x0002` | `uint32` | 仪表 2 的 PWM 占空比上限，可读写 |
| `PARAM_MODE` | `0x0003` | `uint8` | 设备模式，可读写 |
| `PARAM_METER1_VALUE` | `0x0010` | `uint8` | 仪表 1 当前百分比，只读 |
| `PARAM_METER2_VALUE` | `0x0011` | `uint8` | 仪表 2 当前百分比，只读 |

