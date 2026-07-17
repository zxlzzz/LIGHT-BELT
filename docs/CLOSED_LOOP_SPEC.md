# LIGHT-BELT 舱体灯光实体闭环改造任务书

> 本文件用于交给 Claude Code。它定义系统目标、架构边界、协议、约束和验收条件，不规定逐行实现方式。请在 LIGHT-BELT 仓库根目录使用 Plan Mode 阅读本文件。

## 1. 任务使命

将现有 LIGHT-BELT 从“视频/音频分析与模拟输出原型”改造为可部署到 RK3588 ARM64 Linux 的灯光主脑，并形成以下实体闭环。以下实体拓扑和同步行为均为 `NOT HARDWARE VERIFIED`，所有映射必须可配置：

```text
视频/音乐播放与统一时钟
        ↓
RK3588 上的 LIGHT-BELT
├─ 视频区域分析
├─ 音频 RMS / Bass / Mid / Treble / Flux / Beat
├─ 14 条独立逻辑灯光运行效果生成
├─ RGB → RGB+CCT 五通道转换
├─ zone_32 的可配置 STM32 RS-485 帧生成
└─ 13 条 WS2811 独立输出的完整多输出物理帧生成
        │
        ├─ RS-485 → 1 个可配置 STM32 节点 → RGB+CCT COB zone_32
        └─ UDP → 13 个 ESP32-S3 节点 → 每节点 GPIO4 → 24V WS2811
```

RK3588 是唯一在线主脑。RK3568 只作为备用、调试或降级主机，本任务不构建 RK3588/RK3568 分布式计算。

## 2. 已确认的硬件事实

### 2.1 舱体和模拟 COB

真实灯带不是 RGBW 四通道，而是：

```text
24V、六根线、共阳极、五个受控通道
+24V / R / G / B / WW / CW
```

系统名称统一为：

```text
RGB+CCT
```

代码字段统一为：

```text
r
g
b
warm_white
cool_white
```

目标舱体为 2100 mm x 1000 mm x 1800 mm。唯一模拟运行是物理标签 `32`，机器逻辑 ID 固定为 `zone_32`，位置为左侧舷窗/门区域。它使用一个可配置 STM32 RS-485 节点；物理标签 `32` 不强制成为总线地址。这些尺寸、位置和节点安排均为 `NOT HARDWARE VERIFIED`。

### 2.2 数字灯带

数字灯带为 13 条独立的 24V WS2811 RGB 运行。机器逻辑 ID 固定为 `strip_<physical-label>`。物理标签、逻辑 ID、ESP32 node ID、GPIO、协议 node ID 和 Host API target ID 是彼此独立的概念，不得互相推导。

下表的安装位置、长度和 group 数均为 `NOT HARDWARE VERIFIED`，必须可配置：

| 物理标签 | 逻辑 ID | 安装位置 | 长度 | WS2811 groups |
|---|---|---|---:|---:|
| 11 | `strip_11` | 屏幕环绕 | 0.5 m | 10 |
| 12 | `strip_12` | 顶棚边缘 | 2 m | 40 |
| 21 | `strip_21` | 屏幕环绕 | 0.5 m | 10 |
| 22 | `strip_22` | 地板/墙面边缘 | 2 m | 40 |
| 31 | `strip_31` | 屏幕环绕 | 0.5 m | 10 |
| 41 | `strip_41` | 屏幕环绕 | 0.5 m | 10 |
| 42 | `strip_42` | 右墙波浪 | 1 m | 20 |
| 43 | `strip_43` | 右墙波浪 | 1 m | 20 |
| 44 | `strip_44` | 右墙波浪 | 1 m | 20 |
| 45 | `strip_45` | 右墙波浪 | 1 m | 20 |
| 91 | `strip_91` | 预留/可拆卸安装运行 | 1 m | 20 |
| 92 | `strip_92` | 预留/可拆卸安装运行 | 1 m | 20 |
| 93 | `strip_93` | 预留/可拆卸安装运行 | 1 m | 20 |

总计 260 个 WS2811 digital groups。每条灯带保持独立数据输出，不得把多条灯带描述为一条电气串接灯带。Phase 31 生产拓扑中每个 ESP32 只连接一条灯带，每个逻辑帧接收一个完整节点帧并只刷新一次。跨 ESP32 的定时应用软件合同已经实现；真实锁存偏差仍为 `NOT HARDWARE VERIFIED`，必须通过上电和逻辑分析仪验收。

### 2.3 生产控制器与电气分配

Phase 31 采用一条灯带一块 ESP32-S3。每个生产节点只有 `output_id: 1`，数据引脚固定为 GPIO4。以下完整 13 节点分配是当前可配置合同；它不是硬件验收证据：

| ESP32 node | 逻辑灯带 | Groups | Output | GPIO | 现场 IPv4 |
|---:|---|---:|---:|---:|---|
| 1 | `strip_11` | 10 | 1 | 4 | `192.168.31.201` |
| 2 | `strip_41` | 10 | 1 | 4 | `192.168.31.202` |
| 3 | `strip_44` | 20 | 1 | 4 | `192.168.31.203` |
| 4 | `strip_12` | 40 | 1 | 4 | `192.168.31.204` |
| 5 | `strip_22` | 40 | 1 | 4 | `192.168.31.205` |
| 6 | `strip_21` | 10 | 1 | 4 | `192.168.31.206` |
| 7 | `strip_31` | 10 | 1 | 4 | `192.168.31.207` |
| 8 | `strip_42` | 20 | 1 | 4 | `192.168.31.208` |
| 9 | `strip_91` | 20 | 1 | 4 | `192.168.31.209` |
| 10 | `strip_92` | 20 | 1 | 4 | `192.168.31.210` |
| 11 | `strip_43` | 20 | 1 | 4 | `192.168.31.211` |
| 12 | `strip_45` | 20 | 1 | 4 | `192.168.31.212` |
| 13 | `strip_93` | 20 | 1 | 4 | `192.168.31.213` |

当前现场九条灯带只使用节点 `1`、`2`、`4`、`5`、`6`、`7`、`8`、`9`、`10`。节点 `3`、`11`、`12`、`13` 属于完整目标，不得在九节点现场 profile 中伪装为已连接节点。

每条灯带的数据引脚经过该节点自己的 SN74LVC1T45；24V 灯带电源并联；电平转换器 B 侧使用 5V 逻辑电源；所有电源和控制器必须共地。该电气方案、现场地址可达性、电源分段和实际同步性能均为 `NOT HARDWARE VERIFIED`。物理标签、逻辑 ID、协议 node ID、Host API target ID 和 IP 字段仍须分开保存，不得互相推导。

### 2.4 Show 不变与原子切换合同

Show、layout 和效果继续引用稳定的 `strip_*` 逻辑 ID，不包含 ESP32 node、output、GPIO、IP 或固件选择。将一条逻辑灯带从旧控制器输出迁移到独立 ESP32 时，不得通过重写 cue、效果参数、时间线或虚拟路径来补偿物理拓扑；相同逻辑帧在迁移前后必须产生相同的逻辑灯带内容。

现场切换必须在输出禁用并断电的维护窗口中原子完成：所选部署集的固件、标签、数据接线和 Host profile 必须作为一个整体从旧五节点拓扑切到 Phase 31 拓扑。不得让旧多输出固件、新单输出固件、旧 profile 和新接线在一次 live run 中混用。失败时先停止输出，再将 profile、固件集和接线整体回滚。九节点现场验收不得扩展为对缺席节点 3、11、12、13 的验收声明。

## 3. 当前仓库基线

Phase 30 已完成 Show v2 brightness tracks。Phase 31 将生产物理拓扑迁移为一灯带一节点，同时保留 UDP v3 通用多输出能力。开始工作前仍必须运行完整测试，不得依赖历史测试数量：

```text
.\.python\Scripts\python.exe -m pytest -q
```

原始 220-test 起点、RGBW/11-byte v1 缺口和 Phase 0-29 迁移过程保存在
`docs/history/implementation/implementation-plan-phases-0-29.md`。它们解释
开发历史，但不再描述当前实现。

## 4. 强制架构边界

内部类名和文件拆分可由你决定，但以下边界必须成立。

### 4.1 分层

系统必须清晰分为：

```text
媒体时钟与媒体控制
分析
逻辑效果
逻辑到物理映射
协议编码
传输
控制器固件
```

约束：

- 分析模块不得知道 RS-485、UDP、STM32、ESP32 或具体端口。
- 效果模块不得直接编码通信包。
- 协议编码必须是纯逻辑，可在无硬件环境下测试。
- 传输层必须可注入 fake/memory transport，不得靠串口打开失败自动进入测试模式。
- 物理像素数量、节点地址、区段偏移和方向全部来自配置。
- 同一个逻辑灯光帧必须具有唯一 Sequence 和时间戳，并同时用于 RS-485 与 UDP 输出。
- 输出后端不得各自生成互不相关的 Sequence。

### 4.2 逻辑帧

逻辑帧必须能够表达：

```text
sequence
timestamp / media_position
一个 RGB+CCT 模拟区域 zone_32
十三条数字逻辑灯带 strip_11 ... strip_93
metadata / diagnostics
```

可保留 `PixelFrame` 名称，也可引入新模型；若重构公共模型，应提供清晰迁移路径，并更新全部效果、输出和测试。

### 4.3 物理映射

逻辑区域与物理设备分离：

- `zone_32` 映射到可配置的 RS-485 `node_id`，物理标签 32 不等于强制总线地址。
- 数字逻辑灯带映射到 `digital_node_id + gpio/output_index + group_count + direction`。
- UDP v3 通用模型允许一个 ESP32 节点包含一到三条独立输出；Phase 31 生产映射严格使用一条输出，即 `output_id: 1` 和 GPIO4。
- 数字物理帧必须按节点合并为一个完整多输出帧发送，而不是由各效果直接发送多个 strip 包，也不得拼成一条电气串接灯带。
- `DigitalStrip` 保持纯逻辑模型，不包含 node ID、host、port、offset、GPIO 或其他物理拓扑；这些信息只进入映射、配置、协议、固件和 `PhysicalFrame` 层。

## 5. RGB+CCT 数据模型与色彩效果

### 5.1 数据模型

新增或迁移到五通道颜色模型：

```text
RGBCCTColor
r
g
b
warm_white
cool_white
brightness 或等效的单一亮度语义
```

约束：

- 所有通道内部范围为 `[0,1]`。
- NaN、Inf 和越界值必须拒绝或有明确、统一的钳位策略。
- 亮度只应用一次。
- `to_uint8()` 或最终量化步骤必须明确唯一。
- `all_pixels_valid()` 等验证逻辑必须覆盖 WW/CW。
- JSON、模拟器、诊断和导出必须展示 WW/CW。

### 5.2 RGB 到 RGB+CCT 转换

实现可配置、可测试的 RGB→RGB+CCT 转换。实现算法可自主选择，但必须满足：

- 黑色输出五通道全零。
- 高饱和纯红、纯绿、纯蓝主要使用 RGB，WW/CW 接近零。
- 中性白场同时使用 WW 和 CW，RGB 残余受配置控制。
- 暖白输入满足 `WW > CW`。
- 冷白输入满足 `CW > WW`。
- 转换前后感知亮度不应出现明显非单调行为。
- 有全局及每区域功率/通道限制，防止 RGB、WW、CW 同时满载造成不必要功耗。
- 暖白/冷白偏置、白光提取强度、总输出限制均可配置。
- 不假装从普通 RGB 视频精确恢复真实色温；这是视觉映射策略，文档中必须如实说明。

### 5.3 效果兼容

现有主要效果必须继续工作：

```text
static
video_ambient
audio_pulse
bass_pulse
spectrum
breath
color_wave
chase
comet
calm
demo
video_audio_fusion
```

目标效果：

- `video_ambient`：视频区域决定基础颜色和冷暖白倾向。
- `spectrum`：低频驱动顶部，中频驱动左右墙，高频驱动前后。
- `video_audio_fusion`：视频决定基础颜色，音频决定亮度、脉冲、饱和度和动态幅度。
- 数字 WS2811 保持 RGB 像素，不扩展为 CCT。
- 视频分析区域继续保持硬件无关；分析区域到 `zone_32` 和十三条 `strip_*` 的效果映射来自配置，不从物理标签或控制器分配推导。

不得为了 RGB+CCT 重写已验证的视频/音频分析算法，除非测试证明存在必要缺陷。

## 6. RS-485 v2 协议

### 6.1 物理模型

```text
RK3588 / Windows PC
→ 一个 USB-RS485 适配器
→ 一条半双工 RS-485 总线
→ zone_32 的一个带可配置地址的 STM32 节点
```

初始版本是主机单向下发灯光数据，不要求每帧 ACK。可以预留诊断命令，但不能让 ACK 阻塞 30 FPS 灯光输出。

### 6.2 固定帧

协议 v2 固定为 16 字节：

```text
Byte 0   0xA5
Byte 1   0x5A
Byte 2   Version = 0x02
Byte 3   Command
Byte 4   Node ID
Byte 5   Sequence
Byte 6   R
Byte 7   G
Byte 8   B
Byte 9   WW
Byte 10  CW
Byte 11  Fade High
Byte 12  Fade Low
Byte 13  Flags
Byte 14  CRC16 High
Byte 15  CRC16 Low
```

协议约束：

- `Node ID`：协议范围内的可配置地址；物理标签 `32` 不强制成为该地址，可预留广播地址但必须文档化。
- `Sequence`：uint8，允许自然回卷。
- `Fade`：uint16，大端，单位毫秒。
- CRC：CRC-16/CCITT-FALSE。
- CRC 覆盖 Byte 0～13。
- 解析器搜索双字节同步头，固定长度读取，再验证 CRC。
- STM32 接收端字节间超时目标 5 ms；超时重置解析状态。
- 错包、未知版本、未知命令、错误节点不得改变当前灯光状态。
- 必须生成并文档化至少一个主机与固件共享的 Golden Vector。

### 6.3 主机输出语义

每个逻辑帧包含 `zone_32` 的一个节点命令：

```text
同一 sequence
同一逻辑 timestamp
按 zone_32 的可配置 node_id 编码
```

主机输出队列必须保存“最新完整逻辑帧”，而不是保存大量旧包：

- 队列容量语义为最新帧覆盖。
- 一帧的 RS-485 命令不能与下一帧交错。
- 串口不可用时，生产模式必须明确失败并标记 unhealthy。
- memory/fake transport 只能通过配置或依赖注入显式启用。
- 不允许静默回退并继续宣称硬件输出成功。
- 统计必须区分 logical frames、wire packets、drops、errors。
- 统计必须线程安全且只计数一次。

## 7. UDP v3 与 WS2811 节点物理帧

现有 UDP v2 是必须保留的 legacy codec：一个 `pixel_count` 和一个连续 RGB pixel payload。其主机 codec、测试和 `firmware/shared/udp_v2_golden.json` 不得被多输出格式追溯改写。Phase 26 新增 UDP v3 承载以下多输出合同；新舱体生产配置在 Phase 26 后默认使用 v3。

### 7.1 原子帧原则

每个 ESP32-S3 物理节点每个灯光帧只接收一个完整 UDP 数据报；通用 UDP v3 数据报保留一到三个独立输出边界：

```text
一个 node_id
一个 sequence
一个完整输出描述集合（每个 output 的 GPIO/output index、group count 和 RGB payload）
一次校验
```

初始 v3 不做应用层分片。若某节点输出总量超出配置的单数据报上限，应在配置阶段失败并要求增加 ESP32 节点，而不是运行时发送局部帧。Phase 31 生产节点的 `Output Count` 必须为 1，唯一描述符必须是 `output_id: 1`、GPIO4；这不改变通用 codec 接受一到三个输出的合同。

Phase 31 Host session restart uses UDP v3 `KEY_FRAME`: a newly opened UDP v3
output marks sequence 1, and firmware may reset committed sequence only for
that exact flag/sequence pair. All other duplicate or stale sequences remain
invalid.

Scheduled sequence 1 is an atomic multi-node start. Host must finish encoding
every node datagram before any send, then transmit three complete rounds at
2 ms spacing. For each node the three raw datagrams are byte-identical, and
every node/round shares the same apply/media identity. Firmware must treat
repeated KEY packets with that identity idempotently rather than creating new
session generations. Completing KEY preparation admits that generation;
non-KEY frames remain rejected before that boundary. If its later timed
physical transaction fails, the backend restores the previous committed frame
or black and keeps the generation admitted, because every following frame is
complete and can recover without replaying an already-expired KEY.

Production presentation is scheduled in the Host monotonic time domain. One
logical frame owns one common nonzero `apply_at_us`, normally Host monotonic
time plus 20 ms, and every node datagram sets `SCHEDULED_APPLY`. A separate
fixed-length UDP v3 clock-beacon message broadcasts beacon sequence and Host
monotonic microseconds with CRC32. Scheduled flag and nonzero `apply_at_us`
must appear together; an immediate frame uses neither. Production firmware
rejects immediate frames, while explicit legacy diagnostic images retain
immediate application.

### 7.2 当前协议

当前 UDP v3 frame 在保持以下字段和语义的前提下编码：

```text
Magic
Version = 3
Message Type
Digital Node ID
Flags
Sequence（至少uint32）
Media Timestamp
Apply At（Host monotonic microseconds）
Output Count
Payload Length
重复 Output Descriptor（GPIO/output index、Group Count、Output Payload Length）
各输出独立 RGB payload
CRC32
```

时钟 beacon 使用独立的固定长度消息，不伪装为灯光帧：

```text
Magic / Version / Clock Beacon Message Type
Beacon Sequence
Host Monotonic Microseconds
CRC32
```

强制要求：

- 明确定义字节序。
- CRC 覆盖头部和 payload。
- 总长度、Output Count、每输出 Group Count 和 Output Payload Length 必须交叉校验。
- 拒绝重复、陈旧、损坏或尺寸不匹配的帧。
- 新增并文档化 UDP v3 Golden Vector；不得覆盖 UDP v2 Golden Vector。
- 十三条运行的 group count 与控制器分配来自配置，不能由逻辑 ID 硬编码推导。
- 配置必须校验每个物理节点是否能放入一个安全 UDP 数据报。
- 通用 UDP v3 保留每节点一到三条独立 GPIO 输出；Phase 31 完整生产拓扑为 13 节点、每节点一条 GPIO4 输出。
- 同一逻辑帧的所有生产节点数据报必须共享同一个 `apply_at_us`；默认生产提前量为 20 ms。
- `SCHEDULED_APPLY` 与非零 `apply_at_us` 必须同时存在或同时不存在；不得把零值解释为已调度。
- Host 必须从同一个单调时钟生成 beacon 和 apply deadline，并通过一个可配置的局域网广播地址周期发送 beacon。
- 未来可增加多个数字节点而不修改效果层。

### 7.3 ESP32-S3 固件

若仓库没有固件工程，在 `firmware/` 下新增可独立编译的 PlatformIO 工程，或采用同等可复现结构。

固件架构必须实现：

```text
Core 0
├─ Wi-Fi
├─ UDP帧与Host monotonic clock beacon接收
├─ 长度/版本/CRC/Sequence/调度语义校验
├─ 有界窗口 minimum-offset 时钟估计
└─ 最新完整帧写入长度1队列

Core 1
├─ 读取最新帧
├─ 在不触碰GPIO的情况下准备完整编码帧
├─ 按 apply deadline 减去实际 wire time 等待发送起点
├─ 固定GPIO4 SPI硬件后端输出
└─ 物理成功后提交状态，一帧只刷新一次
```

约束：

- 使用 `xTaskCreatePinnedToCore()` 或等效机制明确任务核心。
- 队列长度为1，使用覆盖语义，不积压旧帧。
- UDP回调/接收任务不得直接调用灯带刷新。
- GPIO、node_id、每输出 group_count、色序、亮度上限、超时均可配置。
- Phase 31 生产 GPIO4 分配只存在于配置、映射、协议和固件层；通用固件仍可表达一到三个输出。物理结果为 `NOT HARDWARE VERIFIED`。
- 生产固件必须要求 scheduled frame；clock 样本不足、过期、不确定、deadline 太晚或太远时必须丢弃并明确计数，不得退化为收到即显示。
- 时钟估计使用有界样本窗口中的最小 `local_receive_us - host_monotonic_us` 作为 offset，并用窗口极差作为 uncertainty；Host 重启或样本过期后必须可重新获取时钟。
- 固定 GPIO4 SPI 生产候选后端必须先 `prepare`、再在计算出的发送起点 `transmit`。3.2 MHz 四位编码使用 `0=1000`、`1=1100`，即 T0H/T0L 为 312.5/937.5 ns、T1H/T1L 为 625/625 ns；前后各 200-byte 低电平 guard 均为 500 us。完整 wire time 为：10 groups / 520 bytes / 1300 us，20 groups / 640 bytes / 1600 us，40 groups / 880 bytes / 2200 us。该候选仍为 `NOT HARDWARE VERIFIED`。
- 公共 `apply_at_us` 表示完整编码事务结束后保证 WS2811 已锁存的时刻；不同长度的节点必须通过上述 wire time 提前启动，而不是同时开始发送。
- 显式 Node 2 FastLED、QIO、hybrid、GPIO timing 等诊断环境保留 immediate 行为，不属于生产同步合同。
- output task 每轮循环必须先检查安全超时，即使长度1队列持续有 scheduled frame，也不能让安全黑检查饥饿。
- scheduled SPI transaction 在已校验的 `tx_start` 失败后不得盲目再发第二个完整事务；它必须恢复已提交帧或安全黑，并保留已完成 KEY preparation 的 session admission，让下一张完整 scheduled frame 恢复。显式 immediate 诊断路径可保留其独立重试语义。
- 超时后进入可配置安全状态，桌面默认全黑。
- 串口诊断至少输出收包数、CRC错误、序号间隙、beacon/clock readiness、scheduled queue/commit/drop、deadline error、刷新数和超时数。
- 固件必须能在无实体灯带时编译。
- 不得声称已通过实体硬件验收，除非提供真实测试证据。

## 8. STM32 RGB+CCT 节点固件

若仓库没有固件工程，在 `firmware/` 下新增可独立编译的 PlatformIO 工程，或采用同等可复现结构。

功能要求：

- STM32F103C8T6 BluePill。
- 每块板一个可配置 Node ID。
- 五路硬件 PWM：R/G/B/WW/CW。
- UART/RS-485 接收 v2 固定帧。
- CRC16、版本、命令、Node ID、长度验证。
- 5 ms 字节间超时。
- 目标值与当前值分离。
- 按 Fade 毫秒进行非阻塞插值。
- 通信超时进入可配置安全状态，桌面默认全黑。
- 主循环不得使用会阻塞接收和 PWM 更新的长延时。
- 记录 valid frames、CRC errors、address misses、timeouts 和 sequence gaps。
- PWM、UART、可选 DE/RE 引脚通过集中配置定义。
- 自动收发 RS-485 模块不需要 DE 引脚时应支持该模式。
- 固件必须能编译并包含协议 Golden Vector 测试或宿主侧等效验证。

可以选择 Arduino STM32、HAL 或其他合理实现，但必须说明选择理由，并保持 PlatformIO 可复现编译。

## 9. 媒体时钟与 RK3588 主脑

### 9.1 时钟抽象

保留确定性内部时钟用于测试和离线导出，同时新增媒体播放时钟适配层。

LIGHT-BELT 必须支持：

```text
internal/deterministic clock
mpv IPC media clock
```

要求：

- 正式播放时，灯光位置以播放器实际媒体位置为准，而不是独立累加固定帧周期。
- 支持开始、暂停、继续和媒体结束。
- Seek 或时间跳变时，分析器和效果状态必须有明确重置/恢复策略。
- 测试使用 fake clock，不依赖 CI 中真正启动 mpv。
- mpv 不存在、IPC不可用或播放器退出时必须明确报错或进入安全状态。
- 不实现完整图形界面。
- 提供一个面向 RK3588 的命令或 supervisor 入口，可启动/连接 mpv、运行灯光引擎并在结束时发送安全帧。

媒体时间与展示 deadline 是两个不同维度。效果仍以媒体位置计算；UDP v3
生产输出另外读取 Host 单调时钟，为一个逻辑帧生成同一
`apply_at_us = host_monotonic_us + 20000`，并从同一时钟发送广播 beacon。
ESP32 不把媒体时间当作本地系统时钟，也不使用 wall-clock/UTC 对齐；它只从
beacon 估算 Host 单调时钟到本地 `esp_timer` 的偏移。该软件机制已经实现，
真实跨节点锁存性能仍为 `NOT HARDWARE VERIFIED`。

### 9.2 平台要求

- 保持 Windows 开发/模拟模式可用。
- 支持 RK3588 ARM64 Linux。
- 不提交 Windows 私有 Python 解释器作为 Linux 依赖。
- 修正 `pyproject.toml` 的串口依赖策略。
- Linux 设备路径来自配置，不硬编码 `/dev/ttyUSB0`。
- 文档说明可通过 udev 规则建立稳定名称，但不要要求测试环境拥有 root。
- 提供 RK3588 安装、依赖、运行和 benchmark 文档。
- 可提供 systemd 示例，但不得把设备路径、用户名和媒体目录写死。

## 10. 配置体系

配置必须覆盖：

### 模拟区域

```text
zone_id
node_id
video_zone
channel order
brightness/power limit
warm/cool bias
safe state
```

目标配置只包含 `zone_32`；其物理标签与 `node_id` 分字段保存。

### 数字物理节点

```text
protocol node_id
host
port
outputs[]
outputs[].gpio / output_index
outputs[].group_count
color_order
brightness limit
timeout
max_udp_payload
```

### 数字逻辑区段

```text
logical strip id
physical node id
gpio / output_index
group_count
direction
video_zone
```

### 输出

```text
strict production mode
explicit memory/fake mode
RS-485 port/baudrate
UDP nodes
diagnostics
```

验证要求：

- 协议 Node ID 唯一，且不与物理标签或 Host API target ID 混用。
- `zone_32` 有合法、可配置的 STM32 RS-485 Node ID。
- 完整现场 profile `cabin-lighting-v3-site-local.yaml` 的十三条数字运行均且仅映射到一个独立节点；每个节点只有 `output_id: 1`、GPIO4，并匹配 2.3 节的 group count 和现场地址。通用 production-shape template `cabin-lighting-v3-production.yaml` 保持相同节点映射，但有意保留 TEST-NET endpoints 和 RS-485 占位值，不得作为现场 profile 运行。
- 当前现场 profile 只包含节点 1、2、4、5、6、7、8、9、10 及其九条灯带，不包含未接入节点的占位输出。
- 单节点完整帧不超过 UDP 上限。
- 非法配置在启动时失败，错误信息指出配置路径和具体字段。
- 提供至少两个配置 profile：
  - Windows/无硬件开发与模拟
  - RK3588/RS-485+UDP 实体闭环

## 11. 诊断、错误语义与安全状态

必须修复和统一输出健康状态。

至少提供：

```text
healthy
last_error
logical_frames_submitted
logical_frames_sent
packets_sent
frames_dropped
packets_dropped
crc_errors
sequence_gaps
reconnects
last_success_time
```

要求：

- 线程安全。
- 不重复计数。
- 后端失败相互隔离，但生产模式可配置为关键输出失败即退出。
- 严禁把 memory fallback 计为实体发送成功。
- CLI结束时打印各输出健康摘要。
- JSONL记录 sequence、timestamp、RGB+CCT、数字节点帧摘要及输出状态。
- 程序退出、媒体结束或严重错误时尽力发送安全帧并关闭资源。

## 12. 测试与验收

### 12.1 不得回退

现有测试必须全部通过，或在数据模型迁移时被等价、合理地更新。不得删除测试以获得绿色结果。

### 12.2 必需新增测试

至少覆盖：

1. RGBCCTColor 验证、量化和亮度只应用一次。
2. RGB→RGB+CCT 的黑、RGB原色、中性白、暖白、冷白和单调性。
3. 功率限制。
4. `zone_32` 与十三条 `strip_*` 逻辑输出的合法性。
5. RS-485 v2 encode/decode、Golden Vector、CRC损坏、噪声、拆包、错地址、Sequence回卷。
6. 同一逻辑帧的全部输出使用同一 Sequence，且包不跨帧交错。
7. latest-frame 覆盖语义。
8. 严格生产模式不静默回退。
9. UDP v2 legacy roundtrip、Golden Vector、CRC/长度/旧Sequence/超尺寸拒绝。
10. UDP v3 roundtrip、独立输出边界、CRC/长度/旧 Sequence/未知输出/超尺寸拒绝。
11. 通用多输出映射按数字节点合并为一个完整 UDP v3 物理帧且边界不丢失；Phase 31 生产映射对每节点生成且只生成一个 output 1 / GPIO4 描述符。
12. 多数字节点映射。
13. 相同逻辑帧的 RS-485 与 UDP 使用相同 Sequence。
14. 输出健康统计不重复。
15. fake media clock 的运行、暂停、结束和 seek/reset。
16. CLI/config smoke tests。
17. 固件协议常量与主机协议一致，或通过共享生成物/Golden Vector防止漂移。
18. `SCHEDULED_APPLY` 与 `apply_at_us` 一致性、共享 20 ms apply deadline、clock beacon 编解码/CRC/发送失败和生产模式强制调度。
19. 固件 minimum-offset 窗口、样本不足/过期/不确定、Host epoch 重获、过早/过晚 deadline 和新 session 取消 pending frame。
20. 10/20/40 groups 的 3.2 MHz 四位编码长度分别为 520/640/880 bytes，含前后 500 us 低电平 guard 的完整 wire time 分别为 1300/1600/2200 us，并从相同 latch deadline 得到不同发送起点。
21. scheduled sequence-1 KEY 必须先全节点编码，再以同一 apply/media 和每节点相同 raw 发送三轮、轮间 2 ms；固件覆盖幂等去重、generation 0 非 KEY 门禁、KEY preparation 后会话准入、输出失败后由下一张完整帧恢复、安全超时每轮检查和 scheduled SPI 不重试。

### 12.3 端到端软件验收

提供一个可重复执行的无硬件验收命令或测试：

```text
输入：10秒视频 + 10秒音频
效果：video_audio_fusion
输出：fake RS-485 + fake UDP + JSON
```

验证：

- 约 300～301 个逻辑帧。
- 每帧一个 `zone_32` 模拟节点命令。
- 每个数字物理节点每帧一个完整数据报，并只刷新一次；Phase 31 生产数据报恰好包含一个 output 1 / GPIO4 描述符。
- 同帧 Sequence 完全一致。
- 同帧生产数据报共享一个非零 scheduled `apply_at_us`，clock beacon 与 apply deadline 来自同一个 Host monotonic clock。
- session-start 同帧在任何节点发送前完成全节点编码，随后三轮保持相同节点 raw、apply 和 media identity；重复 KEY 不得产生额外逻辑帧或 session generation。
- 无 NaN/Inf。
- 无协议解码失败。
- 队列无旧帧积压。
- 结束后安全关闭。
- 输出一份机器可读和人类可读的验收摘要。

### 12.4 编译与运行证据

最终必须实际运行并报告：

```text
.\.python\Scripts\python.exe -m pytest -q
.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
```

若新增 PlatformIO 固件：

```text
pio run -d firmware/stm32_rgbcct_node
powershell.exe -NoProfile -ExecutionPolicy Bypass -File firmware/esp32_ws2811_node/scripts/run_native_tests_msvc.ps1
1..13 | ForEach-Object { pio run -j 2 -d firmware/esp32_ws2811_node -e "esp32-s3-node-$_"; if ($LASTEXITCODE -ne 0) { throw "ESP32 Node $_ build failed with exit code $LASTEXITCODE" } }
```

Windows 使用仓库内的 MSVC wrapper；已提供 `gcc` 和 `g++` 的主机可改用
`pio test -d firmware/esp32_ws2811_node -e native` 执行同一组测试。

执行 ESP32 命令前，必须确认 `pio` 位于 A 盘，并按固件 README 将
`PLATFORMIO_CORE_DIR`、`PLATFORMIO_PLATFORMS_DIR`、
`PLATFORMIO_PACKAGES_DIR`、`PLATFORMIO_CACHE_DIR`、`TEMP`、`TMP` 和
`TMPDIR` 全部设为 `firmware/esp32_ws2811_node/.pio` 下的项目本地路径。
13 个生产环境必须按 Node 顺序低并发串行构建，不能并行放大内存和 Windows 分页
压力；项目缓存、构建临时文件和测试临时文件均不得重新写入 C 盘。

报告必须包含：

- 实际命令。
- 返回码。
- 测试数量。
- 失败项。
- benchmark P50/P95/P99 和 processing capacity。
- 修改文件清单。
- 仍需真实硬件验证的项目。

不要只说“应该通过”。

## 13. 非目标

本任务不包括：

- 安卓平板 App。
- 最终舱体施工和商业配电设计。
- 最终施工、电源分段和真实同步性能；Phase 31 已定义映射和现场地址合同，但在真实记录完成前仍标记 `NOT HARDWARE VERIFIED`。
- 自动选择电源和线径。
- RK3588 与 RK3568 分布式计算。
- NPU/GPU优化。
- 云服务。
- 摄像头实时输入。
- 完整Web管理后台。
- 声称完成真实硬件验收。
- 为保持 v1 二进制协议而牺牲新架构；如保留 v1，只能是显式 legacy 模式。

## 14. 实施原则

- 先审计，再计划，再实现。
- 优先复用已经通过验证的视频、音频、效果和映射代码。
- 解决根因，不添加临时旁路。
- 不以巨大重写代替必要迁移。
- 每个阶段保持测试可运行。
- 对协议、配置和安全行为写文档。
- 对无法在当前环境验证的硬件行为明确标记 `NOT HARDWARE VERIFIED`。
- 内部文件和类结构由你根据现有代码选择；如偏离本架构边界，必须在计划中说明理由和权衡。

## 15. Claude Code 的第一阶段输出要求

第一次运行请处于 Plan Mode，禁止编辑文件。完成以下内容：

1. 运行或检查基线测试。
2. 阅读相关模型、效果、映射、引擎、输出、CLI、配置和测试。
3. 列出真实调用链与状态所有权。
4. 确认上述已知缺口，补充遗漏问题。
5. 提出分阶段实施计划。
6. 指出每阶段修改的接口和受影响模块。
7. 指出迁移兼容策略。
8. 指出风险、回滚点和验证命令。
9. 只在存在会改变硬件线序、协议字节布局或安全状态的阻塞歧义时提问。
10. 不要在计划获批前修改代码。

计划获批后，在新的干净会话中实施，并持续运行验证。
