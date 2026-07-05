# LIGHT-BELT 闭环改造实施计划

> **权威版本** — 2026-07-04 批准。本文件是当前实施计划的唯一权威来源。
>
> 基线：`f56db3d Baseline before RGB+CCT closed-loop migration` (220 passed)

---

## 架构决策（已确认）

| 决策 | 结论 |
|---|---|
| RS-485 Sequence | 逻辑帧 uint32，RS-485 发 `seq & 0xFF`，UDP 发完整 uint32 |
| RS-485 帧布局 | 固定 16 字节，Byte 5 为 uint8 Sequence |
| UDP Flags | bit0=SAFE_STATE, bit1=KEY_FRAME, bit2-7 保留且发送端置 0 |
| STM32 PWM 引脚 | R:PA0(TIM2_CH1), G:PA1(TIM2_CH2), B:PA2(TIM2_CH3), WW:PA3(TIM2_CH4), CW:PA6(TIM3_CH1) |
| STM32 UART | USART1 TX:PA9, RX:PA10 |
| STM32 RS-485 | 自动收发 TTL-RS485 模块，初始不要求 DE/RE 引脚 |
| ESP32-S3 网络 | STA 模式，连接现有路由器 |
| 安全状态 | 全黑（RGB+CCT 全零，WS2811 全黑像素），可配置覆盖但默认全黑 |
| brightness 所有权 | OutputTransform 统一应用一次，效果层不乘，协议编码只量化 |
| 统计语义 | send_all() 只统计 submitted，各后端统计 sent/packets，不重复 |
| DigitalStrip | 纯逻辑模型，不含 node_id/IP/offset |
| Golden Vector | JSON 单一来源，生成脚本生成 C/C++ 测试头文件 |
| 阶段顺序 | 先稳定 LogicalFrame + Sequence + 物理映射，再实现 v2 协议 |
| v1 保留策略 | Phase 3-5 通过 RoutedFrame 过渡保留 v1，Phase 6 删除 v1 输出 |
| Wi-Fi 凭据 | config.example.h 提交，config.local.h 在 .gitignore，编译时缺失占位 |
| OutputTransform | Phase 1 最小可用，Phase 4 扩展功率/伽马/安全帧 |

---

## 核心所有权与边界

### Sequence 所有权

```
Engine.run() 分配 uint32 sequence（每次逻辑帧递增）
  └─→ LogicalFrame.sequence = sequence
      └─→ PhysicalFrame.sequence = sequence  (不变)
          ├─→ RS485v2Packet.sequence = sequence & 0xFF
          └─→ UdpV2Packet.sequence = sequence  (完整 uint32)
```

- **唯一来源**: `Engine._sequence`，在 `run()` 主循环中递增
- **消费者**: 物理映射层透传，协议编码层截断/保留
- **绝不**: 输出后端自行生成

### brightness 所有权

```
Config: system.smoothing.max_brightness (0.85)
  └─→ OutputTransform.apply(frame, global_brightness)
      └─→ 每个 RGBCCTColor: out_ch = clamp(ch * global_brightness)
      └─→ 每个 DigitalStrip 像素: out_px = clamp(px * global_brightness)
```

- **唯一应用点**: `OutputTransform` 层
- **效果层**: 产生纯 [0,1] 颜色，不乘 `ctx.global_brightness`
- **协议编码**: 只做 `round(value * 255)` — 纯量化，不乘任何系数
- **RGBCCTColor**: 不含 `brightness` 字段（从根本上消除重复缩放）

### LogicalFrame 与 PhysicalFrame 边界

```
┌─ LogicalFrame ─────────────────────────────┐
│  sequence: uint32                          │
│  timestamp: float (seconds)                │
│  zones: list[ZoneOutput]                   │
│    └─ zone_id: str ("ceiling_left", ...)   │
│    └─ color: RGBCCTColor (纯五通道)        │
│  strips: list[DigitalStrip]                │
│    └─ strip_id: str ("ceiling_left", ...)  │
│    └─ pixel_count: int                     │
│    └─ pixels: list[(r,g,b)]  [0,1]        │
│  metadata: dict                            │
└────────────────────────────────────────────┘
              │
              │  PhysicalMapping.map(logical_frame, layout)
              ▼
┌─ PhysicalFrame ────────────────────────────┐
│  sequence: uint32  (与 LogicalFrame 相同)   │
│  timestamp: float                          │
│  analog_commands: list[AnalogNodeCommand]  │
│    └─ node_id: int (1-6)                   │
│    └─ color: RGBCCTColor (已变换)          │
│    └─ fade_ms: int                         │
│  digital_frames: list[DigitalNodeFrame]    │
│    └─ node_id: int                         │
│    └─ host: str                            │
│    └─ port: int                            │
│    └─ pixels: list[(r,g,b)] (完整节点帧)   │
└────────────────────────────────────────────┘
```

关键约束：

- `DigitalStrip` 不含 `node_id`、`offset`、`IP` — 只存在于配置和 `PhysicalFrame`
- `PhysicalFrame` 由物理映射层生成，输出后端只接收 `PhysicalFrame`（Phase 6+）
- 一个 ESP32 节点的所有逻辑 strip 合并为一个完整 `DigitalNodeFrame`

### RoutedFrame 过渡结构（Phase 3-5）

```python
@dataclass
class RoutedFrame:
    """Phase 3-5 过渡：同时携带逻辑和物理视图。Phase 6 删除。"""
    logical: LogicalFrame    # 供 JsonOutput, SimulatorOutput, legacy v1 输出消费
    physical: PhysicalFrame  # 供 v2 输出消费（Phase 5 起）
```

### 输出消费矩阵

| 输出 | Phase 0-2 | Phase 3-5 | Phase 6+ | 数据类型 |
|---|---|---|---|---|
| NullOutput | LogicalFrame | LogicalFrame | PhysicalFrame | trivial |
| JsonOutput | LogicalFrame | RoutedFrame.logical | PhysicalFrame 的 JSON 视图 (Phase 8) | Logical → Physical serialization |
| SimulatorOutput | LogicalFrame | RoutedFrame.logical | 物理视图显示 (Phase 8) | Logical → Physical display |
| SerialOutput (v1 legacy) | LogicalFrame | RoutedFrame.logical | **Phase 6 删除** | — |
| UdpOutput (v1 legacy) | LogicalFrame | RoutedFrame.logical | **Phase 6 删除** | — |
| SerialOutputV2 (v2) | 不存在 | RoutedFrame.physical | PhysicalFrame | Physical |
| UdpOutputV2 (v2) | 不存在 | RoutedFrame.physical | PhysicalFrame | Physical |

### v2 成为默认的时间线

| Phase | 默认输出 | v1 状态 | v2 状态 |
|---|---|---|---|
| 0-2 | simulator + json | 可用 | 不存在 |
| 3-5 | simulator + json + serial(v1) + udp(v1) | 可用（RoutedFrame 适配） | 可用（RoutedFrame 适配） |
| 6 | simulator + json(v2) + rs485_v2 + udp_v2 | **删除 SerialOutput v1 + UdpOutput v1** | **默认** |
| 8-10 | 同 Phase 6 | — | 默认 |

### 健康统计三层体系

```
send_all() 入口:
  for each output:
    output.health.logical_frames_submitted += 1

各后端完成完整逻辑帧发送后:
  self._health.logical_frames_sent += 1

每个实际协议包（RS-485 包或 UDP 数据报）发送后:
  self._health.packets_sent += 1
```

三层计数，互不重复：

| 字段 | 计数位置 | 含义 |
|---|---|---|
| `logical_frames_submitted` | `send_all()` | Engine 提交的逻辑帧总数 |
| `logical_frames_sent` | 各后端 | 该后端成功完成的逻辑帧数 |
| `packets_sent` | 各后端 | 该后端实际发送的协议包数（1逻辑帧→6 RS-485包；1逻辑帧→1 UDP数据报） |
| `frames_dropped` | 各后端 | 因队列满/错误丢弃的逻辑帧数 |
| `packets_dropped` | 各后端 | 因传输失败丢弃的协议包数 |
| `crc_errors` | 接收端固件 | CRC 校验失败数（主机端通过固件诊断获取） |
| `sequence_gaps` | 接收端固件 | Sequence 不连续次数 |

### Golden Vector 生成流程

```
firmware/shared/rs485_v2_golden.json  ← 单一事实来源（手工维护）
firmware/shared/udp_v2_golden.json

        │  generate_golden_headers.py
        ▼
firmware/stm32_rgbcct_node/test/golden_vectors.h  ← 生成物（不手工编辑）
firmware/esp32_ws2811_node/test/golden_vectors.h

主机测试直接读取 JSON:
  tests/test_rs485_v2.py → open("firmware/shared/rs485_v2_golden.json")
  tests/test_udp_v2.py   → open("firmware/shared/udp_v2_golden.json")

固件测试使用生成的头文件:
  firmware/stm32_rgbcct_node/test/test_protocol.cpp → #include "golden_vectors.h"
  firmware/esp32_ws2811_node/test/test_protocol.cpp  → #include "golden_vectors.h"
```

### 删除计划

| 删除项 | 阶段 | 原因 |
|---|---|---|
| `RGBWColor` | Phase 1 | 被 RGBCCTColor 替换 |
| `light_engine/outputs/compat.py` (过渡适配器) | Phase 6 | v1 输出删除后无消费者 |
| `SerialOutput` (整个 v1) | Phase 6 | 被 SerialOutputV2 替换 |
| `UdpOutput` (整个 v1) | Phase 6 | 被 UdpOutputV2 替换 |
| `RoutedFrame` | Phase 6 | send_all 直接接收 PhysicalFrame |
| `tests/test_serial.py` (v1) | Phase 8+ | 保留为 legacy regression test |
| `tests/test_udp.py` (v1) | Phase 8+ | 同上 |

---

## Phase 0: 关键 BUG 修复

**目标**: 消除崩溃级 BUG，建立安全的修改基线。

**修改**:

- `light_engine/outputs/serial_output.py`: `self._health()` → `self._health`（3处）
- `light_engine/outputs/udp_output.py`: `self._health()` → `self._health`（3处）
- `light_engine/models.py`: `RGBWColor.__post_init__` — 修正 `clamp_rgb` 调用逻辑，分别验证 r/g/b/w
- `light_engine/outputs/__init__.py`: `send_all()` — 准备后续三层统计的代码清理

**新增测试**:

- `tests/test_output_health.py` — `_health` 属性访问不崩溃，health 对象正确更新

**依赖**: 无（独立阶段）

**风险**: 极低（纯 BUG 修复）

**完成条件**: `pytest -q` ≥ 220 passed

**提交边界**: `Phase 0: Fix _health() attribute bug and RGBWColor validation`

---

## Phase 1: RGBCCTColor 数据模型 + 最小 OutputTransform

**目标**: 五通道颜色模型替换 RGBW，效果层解除 brightness 自行乘法，引入最小 OutputTransform 保证全局亮度不丢失。

**核心变更**:

1. `light_engine/models.py`:
   - 新增 `RGBCCTColor(r, g, b, warm_white, cool_white)` — **不含 brightness 字段**
   - `to_uint8()`: `round(ch * 255)` — 纯量化，不乘系数
   - `all_pixels_valid()`: 覆盖 `warm_white`, `cool_white`
   - 删除 `RGBWColor`
   - `ZoneOutput.color: RGBCCTColor`

2. `light_engine/color/__init__.py`:
   - 新增 `rgb_to_rgbcct(r, g, b, *, warm_bias=1.0, cool_bias=1.0, white_strength=0.8, power_limit=1.0)` → `RGBCCTColor`
   - 保留 `rgb_to_rgbw()` 但标记 deprecated（仅 legacy 测试使用）

3. 全部 12 个效果文件 — 两项变更:
   - `RGBWColor(r,g,b,w=0.0,brightness=bri)` → `RGBCCTColor(r,g,b,ww,cw)`
   - **移除 `* ctx.global_brightness`** — 效果只产生纯颜色

4. `light_engine/models.py` (EffectContext):
   - **移除** `global_brightness` 字段（效果不使用）

5. 新增 `light_engine/outputs/transform.py` — **最小 OutputTransform**:
   ```python
   @dataclass
   class OutputTransform:
       global_brightness: float = 1.0
       def apply_to_zone(self, color: RGBCCTColor) -> RGBCCTColor: ...
       def apply_to_pixels(self, pixels) -> list: ...
       def apply_to_frame(self, frame: LogicalFrame) -> LogicalFrame: ...
   ```
   - **唯一 brightness 应用点**
   - Phase 4 在已有基础上扩展（功率限制、Gamma、安全帧），不重写

6. `light_engine/outputs/json_output.py`: `"w"` → `"warm_white"`, `"cool_white"`

7. `light_engine/simulator/__init__.py`: 终端显示 WW/CW

8. `light_engine/mapping/__init__.py`: `zone_type: "rgbw"` → `"rgbcct"`

9. `config/layout.yaml`: `type: "rgbw"` → `type: "rgbcct"`

**Phase 1 结束时的数据流**:

```
Effect.process(ctx) → LogicalFrame (纯颜色)
  → OutputTransform.apply(frame)
    → 每个 RGBCCTColor: ch *= global_brightness
    → 每个 DigitalStrip pixel: ch *= global_brightness
  → RGBCCTColor.to_uint8(): round(ch * 255)  ← 纯量化
  → 输出后端
```

**Phase 4 扩展 OutputTransform（不重写）**:

| 能力 | Phase 1 | Phase 4 新增 |
|---|---|---|
| global_brightness 单次应用 | ✅ | — |
| to_uint8 纯量化 | ✅ | — |
| 功率限制 | — | ✅ |
| Gamma 校正 | — | ✅ |
| per-zone warm/cool bias | — | ✅ |
| 健康统计三层 | — | ✅ |
| 安全帧 | — | ✅ |

**Engine.run() 集成**:

```python
transform = OutputTransform(
    global_brightness=config.get("system.smoothing.max_brightness", 0.85)
)
frame = self._effect.process(ctx)
frame = transform.apply_to_frame(frame)
send_all(self._outputs, frame)
```

**测试**:

- 更新 `tests/test_models.py`: `TestRGBWColor` → `TestRGBCCTColor`
- 更新 `tests/test_color.py`: 新增暖白/冷白/功率限制/单调性测试
- 更新 `tests/test_video_mapping.py`: `TestRGBWChannel` → `TestRGBCCTChannel`
- 新增 `tests/test_rgbcct.py`: 黑场/RGB 原色/中性白/暖白/冷白/功率限制
- 新增 `tests/test_output_transform.py`: brightness 只应用一次，全局亮度行为与 Phase 0 等价
- 所有效果测试更新断言：检查 RGBCCTColor 而非 RGBWColor

**依赖**: Phase 0

**风险**: 中（12 个效果全部修改，但变更机械）

**回滚点**: Phase 0 提交

**完成条件**: ≥220 passed，JSON 中可见 `warm_white`/`cool_white`，全局亮度行为与 Phase 0 一致

**提交边界**: `Phase 1: RGBCCTColor model + minimal OutputTransform, single brightness application`

---

## Phase 2: LogicalFrame 统一 Sequence

**目标**: `LogicalFrame` 携带统一 sequence，Engine 统一分配。

**修改**:

- `light_engine/models.py`:
  - `LogicalFrame`（原 `PixelFrame`）新增 `sequence: int = 0`
  - `EffectContext` 新增 `sequence: int = 0`（效果可记录但不应修改）

- `light_engine/engine/__init__.py`:
  - 新增 `self._sequence: int = 0`
  - 每逻辑帧递增：`self._sequence += 1`
  - `LogicalFrame(sequence=self._sequence, ...)`

- `light_engine/outputs/__init__.py`:
  - `send_all()` 使用 `frame.sequence` 传递到各后端（日志记录，Phase 4 正式使用）

- `light_engine/outputs/udp_output.py`:
  - 移除 `self._sequence` 独立递增
  - `send_frame()` 从 `frame.sequence` 读取

- `light_engine/outputs/serial_output.py`:
  - 当前 v1 协议无 sequence 字段，Phase 5 切换到 v2 后使用

**数据所有权**:

- **sequence 唯一来源**: `Engine._sequence`
- **不创建**: 任何输出后端不得自行递增 sequence
- **透传**: EffectContext → LogicalFrame → send_all → 输出后端

**测试**:

- 更新 `tests/test_engine.py`: 验证 `frame.sequence` 每帧递增
- 新增测试：同一逻辑帧 RS-485 和 UDP 使用相同 sequence（Phase 3 完成后可充分验证）

**依赖**: Phase 1

**风险**: 低（新增字段，不改变现有行为）

**完成条件**: 所有测试通过，LogicalFrame.sequence 随帧递增

**提交边界**: `Phase 2: Unified sequence on LogicalFrame`

---

## Phase 3: 物理映射层 + RoutedFrame 过渡

**目标**: LogicalFrame → PhysicalFrame 转换，RoutedFrame 过渡保证现有输出不中断。

**新增文件**:

- `light_engine/mapping/physical.py`:
  - `AnalogNodeMapping(node_id, zone_id, channel_order, fade_ms)`
  - `DigitalNodeMapping(node_id, host, port, pixel_count)`
  - `DigitalSegmentMapping(strip_id, node_id, offset, pixel_count, direction)`
  - `PhysicalFrame(sequence, timestamp, analog_commands, digital_frames)`
  - `PhysicalMapping.__init__(layout)` — 从 Layout 加载映射配置
  - `PhysicalMapping.map(logical_frame) → PhysicalFrame`
    - 6个 zone → 6个 `AnalogNodeCommand(node_id, color, fade_ms)`
    - 6个 logical strip → 按 node_id 合并为 `DigitalNodeFrame(node_id, host, port, pixels)`
    - 验证：segment 不重叠不越界，总 pixel_count 不超 UDP 上限

- `light_engine/outputs/compat.py` (**Phase 6 删除**):
  - `logical_to_legacy_serial(frame)` → v1 11-byte 包列表
  - `logical_to_legacy_udp(frame)` → v1 UdpPacket 列表

- `light_engine/models.py`:
  - 新增 `RoutedFrame(logical: LogicalFrame, physical: PhysicalFrame)` (**Phase 6 删除**)

**修改**:

- `light_engine/mapping/__init__.py`:
  - `Layout` 新增 `analog_nodes`, `digital_nodes`, `digital_segments`
  - 配置验证：node_id 唯一性、segment 不重叠不越界、UDP payload 不超限、6个 zone 都有合法 node_id
  - 非法配置启动时 `ConfigError` 失败

- `light_engine/engine/__init__.py`:
  - 集成 `PhysicalMapping`
  - `run()` 中：effect.process() → LogicalFrame → PhysicalMapping.map() → RoutedFrame → send_all()

- `light_engine/outputs/__init__.py`:
  - `send_all()` 接受 `RoutedFrame`，根据输出类型分发 `.logical` 或 `.physical`

**配置结构**:

```yaml
layout:
  analog_nodes:
    - node_id: 1, zone_id: "ceiling_left", video_zone: "top", channel_order: "RGBWC"
    - node_id: 2, zone_id: "ceiling_right", video_zone: "top"
    - node_id: 3, zone_id: "wall_left", video_zone: "left"
    - node_id: 4, zone_id: "wall_right", video_zone: "right"
    - node_id: 5, zone_id: "front", video_zone: "center"
    - node_id: 6, zone_id: "rear", video_zone: "center"

  digital_nodes:
    - node_id: 1, host: "192.168.1.100", port: 9001, pixel_count: 632

  digital_segments:
    - strip_id: "ceiling_left", node_id: 1, offset: 0, pixel_count: 144, direction: "forward", video_zone: "top"
    - strip_id: "ceiling_right", node_id: 1, offset: 144, pixel_count: 144, direction: "forward", video_zone: "top"
    - strip_id: "wall_left", node_id: 1, offset: 288, pixel_count: 100, direction: "forward", video_zone: "left"
    - strip_id: "wall_right", node_id: 1, offset: 388, pixel_count: 100, direction: "forward", video_zone: "right"
    - strip_id: "front", node_id: 1, offset: 488, pixel_count: 72, direction: "forward", video_zone: "center"
    - strip_id: "rear", node_id: 1, offset: 560, pixel_count: 72, direction: "reverse", video_zone: "center"
```

**Phase 3 CLI 兼容性**:

```
light_engine demo         → simulator + json 输出, 正常
light_engine simulator    → 终端模拟器, 正常
light_engine export       → JSONL, 正常（显示逻辑区域颜色）
light_engine benchmark    → NullOutput, 正常
```

**测试**:

- 新增 `tests/test_physical_mapping.py` — 6节点映射，segment 合并，多节点，重叠检测
- 新增 `tests/test_legacy_compat.py` — v1 输出通过 RoutedFrame.logical 正确接收数据
- 新增 `tests/test_phased_output_matrix.py` — 按输出消费矩阵验证每个输出收到的数据类型
- 更新 `tests/test_engine.py` — 验证 RoutedFrame 包含 logical 和 physical

**依赖**: Phase 2

**风险**: 中（新增核心抽象层和过渡结构）

**完成条件**: 物理映射测试通过，segment 合并验证正确，全部 CLI 命令可运行，现有测试绿色

**提交边界**: `Phase 3: Physical mapping layer with RoutedFrame transition adapter`

---

## Phase 4: OutputTransform 扩展 + 三层健康统计

**目标**: OutputTransform 扩展功率/伽马/安全帧能力；三层统计体系完整实现。

**修改**:

- `light_engine/outputs/transform.py` (扩展，不重写 Phase 1 基础):
  - 新增 `power_limit`: 防止 RGB + WW + CW 同时满载
  - 新增 `gamma`: gamma_correct 应用
  - 新增 `per_zone_warm_bias` / `per_zone_cool_bias`
  - 新增 `generate_safe_frame()` → LogicalFrame（全黑 + SAFE_STATE 元数据）

- `light_engine/outputs/__init__.py`:
  - `OutputHealth` 完整字段：
    ```python
    logical_frames_submitted: int = 0
    logical_frames_sent: int = 0
    packets_sent: int = 0
    frames_dropped: int = 0
    packets_dropped: int = 0
    last_error: Optional[str] = None
    last_success_time: float = 0.0
    ```
  - `send_all()`: **仅** `output.health.logical_frames_submitted += 1`
  - 新增 `health_summary(outputs) → dict`

- `light_engine/outputs/serial_output.py`:
  - `send_frame()` 完成时：`self._health.logical_frames_sent += 1`
  - 每个 zone 包发送后：`self._health.packets_sent += 1`
  - 移除 `send_all()` 中的外层 `frames_sent` 递增

- `light_engine/outputs/udp_output.py`:
  - 同上

- `light_engine/cli/__init__.py`:
  - 所有命令退出前打印 `health_summary()`

- `light_engine/engine/__init__.py`:
  - `_shutdown()` 发送安全帧

**测试**:

- 新增 `tests/test_output_transform.py`: 功率限制、伽马、per-zone bias、安全帧
- 新增 `tests/test_output_health.py`: 三层计数不重复，线程安全，字段完整性

**依赖**: Phase 3

**风险**: 中（改变统计语义）

**完成条件**: brightness 单次应用验证，三层统计测试通过，安全帧发送验证

**提交边界**: `Phase 4: Extended OutputTransform and three-tier health statistics`

---

## Phase 5: RS-485 v2 + UDP v2 协议编解码器

**目标**: 实现 v2 纯协议编解码器，含 Golden Vector。

**新增**:

- `light_engine/outputs/rs485_v2.py`:
  ```
  RS485v2Packet:
    sync: bytes = b'\xA5\x5A'
    version: int = 2
    command: int
    node_id: int (1-6)
    sequence: int (逻辑帧 sequence & 0xFF)
    r, g, b, ww, cw: int (uint8)
    fade_ms: int (uint16 big-endian)
    flags: int
    crc: int (CRC-16/CCITT-FALSE, 覆盖 byte 0-13)

    encode() → bytes (16 bytes)
    decode(data: bytes) → Optional[RS485v2Packet]
  ```
  - 固定 16 字节帧
  - CRC-16/CCITT-FALSE
  - 解析器：双字节同步 + 固定长度读取 + CRC 验证

- `light_engine/outputs/udp_v2.py`:
  ```
  UdpV2Packet:
    magic: int = 0x4C45
    version: int = 2
    message_type: int
    digital_node_id: int
    flags: int  (bit0=SAFE_STATE, bit1=KEY_FRAME, bit2-7=0)
    sequence: int (uint32)
    pixel_count: int (uint16)
    payload_length: int (uint16)
    pixels: list[(r,g,b)] (uint8)
    crc32: int (CRC32 over header+payload)

    encode() → bytes
    decode(data: bytes) → Optional[UdpV2Packet]
  ```
  - 不分片（超限配置阶段失败）
  - CRC32
  - 旧 sequence/尺寸不匹配/CRC 错误拒绝

- `firmware/shared/rs485_v2_golden.json` — Golden Vector
- `firmware/shared/udp_v2_golden.json` — Golden Vector
- `firmware/shared/generate_golden_headers.py` — JSON → C/C++ 头文件

- `light_engine/outputs/__init__.py`:
  - `create_outputs()` 新增 `rs485_v2`, `udp_v2` 输出类型

**修改**:

- `light_engine/outputs/serial_output.py`: 新增 `SerialOutputV2`（消费 PhysicalFrame）
- `light_engine/outputs/udp_output.py`: 新增 `UdpOutputV2`（消费 PhysicalFrame）

**测试**:

- 新增 `tests/test_rs485_v2.py`:
  - Golden Vector 编解码
  - CRC 损坏拒绝
  - 噪声 + 拆包恢复
  - 错地址拒绝（node_id 不匹配）
  - Sequence 回卷 (255→0)
  - 一逻辑帧六节点同 sequence
  - 加载 `firmware/shared/rs485_v2_golden.json` 验证

- 新增 `tests/test_udp_v2.py`:
  - Golden Vector 编解码
  - CRC32/长度/旧 Sequence/超尺寸拒绝
  - 加载 `firmware/shared/udp_v2_golden.json` 验证

- 新增 `tests/test_golden_consistency.py`:
  - JSON Golden Vector 加载和字段完整性
  - 生成脚本运行和 C 头文件语法检查

- 保留 `tests/test_serial.py` 和 `tests/test_udp.py` (legacy v1) 不变

**依赖**: Phase 3 (PhysicalFrame 可用)

**风险**: 低-中（纯协议层）

**完成条件**: v2 协议测试全部通过，Golden Vector 一致性验证通过

**提交边界**: `Phase 5: RS-485 v2 and UDP v2 protocol codecs with golden vectors`

---

## Phase 6: 输出传输层加固 + 删除 v1

**目标**: 严格 production/memory/fake 模式，最新帧覆盖队列，删除 v1 输出和 RoutedFrame。

**修改**:

- `light_engine/outputs/__init__.py`:
  - 新增 `OutputMode = Enum('OutputMode', ['PRODUCTION', 'MEMORY', 'FAKE'])`
  - `create_outputs()` 读取 `outputs.mode` 配置
  - PRODUCTION: 串口打开失败 → unhealthy + 报错，不降级
  - MEMORY: 显式内存传输，标记 `NOT HARDWARE`
  - FAKE: 无条件成功，仅用于 benchmark
  - `send_all()` 直接接收 `PhysicalFrame`（不再使用 RoutedFrame）

- `light_engine/outputs/serial_output.py`:
  - 移除 `_attempt_reconnect()` 中的静默 memory fallback
  - 新增 `LatestFrameQueue(1)` — 覆盖语义队列
  - 发送时保证六节点包连续无交错
  - `send_frame()` → 入队最新帧（覆盖旧帧）
  - `_writer_loop()` → 取出最新完整帧 → 逐包发送

- `light_engine/outputs/udp_output.py`:
  - 同上 `LatestFrameQueue(1)`
  - 接收完整 `DigitalNodeFrame`（已合并），不再自行分片
  - `send_frame()` → 入队最新帧 → 单 UDP 数据报发送

- **删除文件**:
  - `light_engine/outputs/compat.py` (过渡适配器)
  - `RoutedFrame` 类（从 `light_engine/models.py`）
  - `SerialOutput` v1 类（`light_engine/outputs/serial_output.py` 中）
  - `UdpOutput` v1 类（`light_engine/outputs/udp_output.py` 中）

- `light_engine/engine/__init__.py`:
  - `_shutdown()`: 发送安全帧后关闭
  - 安全帧: `SAFE_STATE` flag 置位，RGB+CCT 全零，数字像素全黑

**测试**:

- 新增 `tests/test_output_safety.py`:
  - PRODUCTION 模式串口失败报错（不降级）
  - MEMORY 模式显式启用可运行
  - 最新帧覆盖（快速发送 5 帧，仅 1 帧被消费）
  - 六节点包不交错
  - 安全帧发送验证（SAFE_STATE flag, 全黑内容）

- 更新输出测试：只测试 v2 路径

**依赖**: Phase 4 + Phase 5

**风险**: 中高（改变故障语义，删除代码）

**完成条件**: 安全测试全部通过，production 模式拒绝静默降级，v1 代码已删除

**提交边界**: `Phase 6: Harden output transport, delete v1 outputs and RoutedFrame`

---

## Phase 7: 媒体时钟集成

**目标**: 使用 `clock.py` 抽象，支持 mpv IPC 时钟。

**修改**:

- `light_engine/engine/__init__.py`:
  - `__init__(config, clock=None)`: 接受 `Clock` 注入
  - `run()`: `dt = self._clock.tick()` 替代 `time.sleep() + += frame_period`
  - Seek 检测：`dt > frame_period * 2` → 重置分析器和效果状态
  - 暂停检测：`dt < frame_period * 0.1` → 跳过分析但保持输出
  - `self._timestamp = self._clock.now()`

- `light_engine/clock.py`:
  - 新增 `MpvIPCClock`：通过 mpv JSON IPC 获取 `playback-time`
  - 媒体结束检测：`idle-active` 或 `eof-reached` 事件
  - mpv 不可用/退出时 `tick()` 抛出明确异常

- 新增 `light_engine/media/mpv_adapter.py`:
  - mpv `--input-ipc-server` socket 连接
  - `get_position()`, `is_paused()`, `is_ended()`
  - 连接失败明确报错（不静默回退）

- `light_engine/cli/__init__.py`:
  - 新增 `--clock` 参数: `internal` (默认), `mpv`, `fake`
  - 新增 `run-mpv` 子命令

- `docs/rk3588_deployment.md` (NOT HARDWARE VERIFIED):
  - RK3588 安装、依赖、运行文档
  - mpv IPC socket 配置
  - systemd service 示例（设备路径和用户名不写死）

**测试**:

- 新增 `tests/test_clock_integration.py`:
  - `FakeClock` 运行/暂停/结束/seek → 效果状态重置
  - `OfflineRenderClock` 确定性输出
  - `FakeClock` seek 后 sequence 不跳变

**依赖**: Phase 6

**风险**: 中（改变时间推进）

**实现状态（Iteration 1）**:

- Engine accepts an injected `Clock`.
- Internal/offline clocks use deterministic fixed-step ownership.
- `MpvIPCClock` reads mpv JSON IPC `playback-time`, `pause`, `idle-active`, and
  `eof-reached`.
- Seek jumps reset analyzer/effect state while preserving Engine sequence
  ownership.
- Paused clocks skip analysis updates and keep deterministic output.
- `run-mpv` and CLI `--clock` selection are available.
- RK3588 deployment notes are documented as `NOT HARDWARE VERIFIED`.

**完成条件**: FakeClock 端到端通过，benchmark 与 Phase 0 一致

**提交边界**: `Phase 7: Media clock integration with mpv IPC support`

---

## Phase 8: 配置体系升级 + 双 Profile

**目标**: 完整 v2 配置验证，JsonOutput/SimulatorOutput 切换到 PhysicalFrame 视图。

**新增/修改**:

- `config/layout.yaml` → v2 结构（analog_nodes + digital_nodes + digital_segments）
- `config/outputs.yaml` → 新增 `mode`, `exit_safe_state`
- `config/system.yaml` → 新增 `clock.mode`, `platform` 字段
- `config/profiles/windows_dev.yaml`:
  ```yaml
  outputs.mode: "memory"
  clock.mode: "internal"
  platform: "windows"
  ```
- `config/profiles/rk3588_production.yaml`:
  ```yaml
  outputs.mode: "production"
  clock.mode: "mpv"
  platform: "linux_arm64"
  ```

- `light_engine/config/__init__.py`:
  - `validate_config()` — 启动时全面验证
  - 非法配置: `ConfigError` with path + field + value + expected

- `light_engine/outputs/json_output.py`:
  - 切换到 `PhysicalFrame` 序列化（显示 node_id、物理分组）
  - 保留逻辑区域颜色在 metadata 中

- `light_engine/simulator/__init__.py`:
  - 切换到物理视图显示（按 node 分组）

**测试**:

- 新增 `tests/test_config_validation.py` — 非法配置启动失败
- 更新 JSON 和模拟器测试：验证物理视图输出

**依赖**: Phase 6 + Phase 7

**风险**: 低

**完成条件**: 双 profile 加载成功，配置验证测试通过，JSON/模拟器显示物理分组

**提交边界**: `Phase 8: Configuration upgrade with dual profiles and PhysicalFrame views`

---

## Phase 9: 固件工程

**目标**: 可独立编译的 STM32 和 ESP32-S3 PlatformIO 工程。

### STM32 RGB+CCT 节点

`firmware/stm32_rgbcct_node/`:

- `platformio.ini` — STM32F103C8T6, Arduino STM32 或 libopencm3 框架
- `src/config.h` — 集中定义（不得散落硬编码）:
  ```c
  #define NODE_ID 1  // 每节点烧录前修改
  #define PWM_PIN_R PA0    // TIM2_CH1
  #define PWM_PIN_G PA1    // TIM2_CH2
  #define PWM_PIN_B PA2    // TIM2_CH3
  #define PWM_PIN_WW PA3   // TIM2_CH4
  #define PWM_PIN_CW PA6   // TIM3_CH1
  #define UART_TX PA9
  #define UART_RX PA10
  #define RS485_BAUDRATE 115200
  #define BYTE_TIMEOUT_MS 5
  #define SAFE_STATE_TIMEOUT_MS 1000
  ```
- `src/protocol.h` — v2 16-byte 帧常量和结构体
- `src/protocol.cpp` — CRC-16/CCITT-FALSE, 帧解析, 验证
- `src/pwm_output.h/cpp` — 五路 PWM, 目标值/当前值分离, 非阻塞 fade 插值
- `src/main.cpp` — 非阻塞主循环
- `test/test_protocol.cpp` — Golden Vector 验证（include 生成的头文件）
- `README.md`

### ESP32-S3 WS2811 节点

`firmware/esp32_ws2811_node/`:

- `platformio.ini` — ESP32-S3, Arduino 框架
- `src/config.example.h` — **提交**: 非秘密参数
  ```c
  #define NODE_ID        1
  #define LED_PIN        4
  #define PIXEL_COUNT    632
  #define UDP_PORT       9001
  #define COLOR_ORDER    GRB
  #define BRIGHTNESS_MAX 255
  #define SAFE_TIMEOUT_MS 1000
  // Wi-Fi 凭据在 config.local.h 中定义（不提交）
  ```
- `src/config.local.h` — **不提交，在 .gitignore 中**
  ```c
  #define WIFI_SSID     "my-actual-ssid"
  #define WIFI_PASSWORD "my-actual-password"
  ```
- `src/main.cpp`:
  ```cpp
  #include "config.h"
  #ifdef HAS_LOCAL_CONFIG
  #include "config.local.h"
  #else
  #define WIFI_SSID     "PLACEHOLDER_SSID"
  #define WIFI_PASSWORD "PLACEHOLDER_PASSWORD"
  #endif
  ```
- `src/protocol.h` — v2 UDP 常量
- `src/protocol.cpp` — CRC32, 帧解析, 验证
- `src/led_output.h/cpp` — RMT 输出, 双缓冲
- `test/test_protocol.cpp` — Golden Vector 验证
- `README.md`

### 共享 Golden Vector

`firmware/shared/`:

- `rs485_v2_golden.json` — 单一事实来源
- `udp_v2_golden.json` — 单一事实来源
- `generate_golden_headers.py` — JSON → C/C++ 头文件

### Wi-Fi 凭据编译行为

| 场景 | 行为 |
|---|---|
| `config.local.h` 存在 | 使用真实凭据编译，WiFi 正常连接 |
| `config.local.h` 不存在 | 使用占位凭据编译通过，运行时报 "WiFi placeholder SSID" |
| CI 编译 | 无 `config.local.h`，编译通过，固件测试仅验证协议（不需 WiFi） |

### .gitignore 补充

```gitignore
# 固件本地凭据
firmware/**/config.local.h
firmware/**/config.local.ini
```

### 验证命令

```bash
pio run -d firmware/stm32_rgbcct_node
pio run -d firmware/esp32_ws2811_node
```

**依赖**: Phase 5 (Golden Vector 可用)

**风险**: 中（协议逻辑正确性，可编译验证）

**完成条件**: 两个固件编译通过，Golden Vector 测试通过

**标记**: 所有固件功能标注 `NOT HARDWARE VERIFIED`

**提交边界**: `Phase 9: STM32 and ESP32-S3 firmware projects`

---

## Phase 10: 端到端集成与验收

**目标**: 10 秒视频+音频无硬件端到端验收。

**新增**:

- `tests/test_e2e_acceptance.py`:
  ```python
  def test_10s_video_audio_e2e():
      # 输入：生成 10 秒测试视频 + 10 秒测试音频
      # 效果：video_audio_fusion
      # 输出：fake RS-485 v2 + fake UDP v2 + JSON
      # 验证：
      #   - 约 300-301 个逻辑帧
      #   - 每帧 6 个 RS-485 v2 包
      #   - 每帧 1 个 UDP v2 数据报
      #   - 同帧 sequence 完全一致
      #   - 无 NaN/Inf
      #   - 协议 decode 成功
      #   - 队列无旧帧积压
      #   - 安全帧发送
  ```

**运行命令**:

```bash
.\.python\python.exe -m pytest -q
.\.python\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
pio run -d firmware/stm32_rgbcct_node
pio run -d firmware/esp32_ws2811_node
.\.python\python.exe -m pytest tests/test_e2e_acceptance.py -v
```

**输出报告**: 实际命令、返回码、测试数量、失败项、benchmark P50/P95/P99、修改文件清单、`NOT HARDWARE VERIFIED` 标记

**依赖**: Phase 8 + Phase 9

**风险**: 低

**完成条件**: 全部测试通过，验收报告完整

**提交边界**: `Phase 10: End-to-end acceptance tests`

---

## 阶段依赖图

```
Phase 0 (BUG修复)
  └─→ Phase 1 (RGBCCTColor + 最小OutputTransform)
        └─→ Phase 2 (LogicalFrame + 统一Sequence)
              └─→ Phase 3 (物理映射 + RoutedFrame过渡)
                    ├─→ Phase 4 (OutputTransform扩展 + 健康统计)
                    │     └─→ Phase 5 (RS-485 v2 + UDP v2 协议)
                    │           └─→ Phase 6 (输出加固 + 删除v1)
                    │                 └─→ Phase 7 (时钟)
                    │                       └─→ Phase 8 (配置 + PhysicalFrame视图)
                    │                             └─→ Phase 10 (验收)
                    │
                    └─→ Phase 9 (固件) ←── Phase 5 Golden Vectors
                          └─→ Phase 10 (验收)
```

Phase 9 在 Phase 5（Golden Vector）完成后可启动，与 Phase 6-8 完全并行。

---

## 回滚策略

每个 Phase 独立提交到 Git。如果某 Phase 引入问题：

1. `git revert <phase-commit>` 回滚该 Phase
2. 后续 Phase 需要 rebase 到回滚后的分支
3. Phase 0-3 为核心架构，Phase 4-9 为加固和配套
4. 每个 Phase 结束运行 `pytest -q` 确认不低于基线通过数

---

## 非目标（本计划不涵盖）

- 安卓平板 App
- 最终舱体施工和商业配电设计
- 确定最终 COB/WS2811 米数
- 自动选择电源和线径
- RK3588 与 RK3568 分布式计算
- NPU/GPU 优化
- 云服务
- 摄像头实时输入
- 完整 Web 管理后台
- 声称完成真实硬件验收
- 为保持 v1 二进制协议而牺牲新架构
