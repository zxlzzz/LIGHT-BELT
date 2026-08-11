# LIGHT-BELT 声音反应模式 设计文档

> 版本：v0.3（设计草案，未实施）
> 日期：2026-08-11
> 状态：待评审。本文档不含任何已执行的操作。

---

## 0. v0.3 变更说明

**核心原则改变**：v0.2 里凡是"能从仓库配置文件读到的数据"（节点像素数、GPIO 映射、节点 IP 等），一律**不再抄进本文档**，只记录"去哪个文件读"。原因：v0.2 把某份 profile 的数字抄进了文档，结果发现仓库里另一份看起来同布局的 profile 数字对不上（node1 的像素数一份写 40 一份写 20），文档里的数字反而成了误导源。抄一次数据就多一处以后要手动同步的地方，抄的越详细，过期后错的越隐蔽。

之后所有涉及"具体数值"的地方，本文档只回答"读哪个文件/哪个字段"，不回答"值是多少"。实现代码同理，必须在运行时读取配置文件，不允许把这些数字写进代码或文档。

**遗留问题（需要你确认，不确认之前 §4 的分段设计无法真正落地）**：

仓库里 `config/profiles/` 下至少有 `wled-five-board-phase-17.yaml` 和 `rk3588-host-service.yaml` 两份文件，看起来描述同一套硬件布局，但至少有一处字段不一致。需要你确认：
1. 板子上 `ENGINE_PROFILE_PATH` 当前实际指向哪一份？
2. 这两份文件是否本该是同一份（其中一份是历史遗留，应该删除/合并），还是各自有不同用途？

在这个问题解决之前，本文档统一用「生产 profile」指代"板子上实际生效的那份文件"，不指定具体文件名。

---

## 1. 一页速览

| 项 | 结论 |
|---|---|
| 可行性 | 可行。节点硬件与固件均已具备，无需重新烧录固件 |
| 麦克风 | I2S PDM 数字麦，出厂已配好并在工作（具体 GPIO 见生产节点 `cfg.json`，不在此抄录） |
| 固件 | WLED 0.15.1，audioreactive 为官方 usermod，功能完整 |
| 关键约束 | DDP 实时流会完全旁路 WLED 特效引擎；本地声音特效与 DDP 二选一 |
| 关键发现 | 节点的"发送音频同步"与"渲染像素"是两条独立路径，可以并存（架构支点，见 §3） |
| 推荐配置 | 5 台节点统一静态配置为 `sync.mode = Send`，各占独立端口，一次配置终身不改 |
| 模式切换 | 全部在 Host 软件侧完成，不需要运行时改节点 cfg |
| 保护性算法 | Host 通过运行时可写的 `inputLevel` 对每个节点做慢速增益校正，独立/融合模式共用 |
| 阶段二/三渲染路径 | 复用现有 `AudioFeatures` 接口和 spectrum/audio_pulse/bass_pulse 灯效，不新建管线 |
| 分段所需像素数 | 运行时读取生产 profile，不写死在文档或代码里（见 §0 遗留问题） |
| 主要未验证项 | DDP 推流期间节点是否仍在发送 audioSync 包（tcpdump 验证，§8.1） |

---

## 2. WLED 音频链路与协议约束（协议事实，不随项目配置变化）

这一节的内容是 WLED 固件本身的行为和协议格式，跟仓库哪份 profile 生效无关，可以放心引用。

- 麦克风采样 → Squelch 噪声门 → Gain → AGC → FFT → 16 段 GEQ → Frequency Scale → Dynamics Limiter（仅影响 ♪ 特效渲染，不影响 UDP 发送值——这点需要实测确认，见 §8.2）→ 共享变量 → ♪ 特效读取渲染。
- UDP Sound Sync：组播 `239.0.0.1`，端口默认 11988（可配置，用于给设备分组），发包间隔约 20ms，接收端约 20ms 插值延迟。组播在消费级路由器上不总是可靠。
- V2 包结构固定为 44 字节 packed 小端序：`header[6] + reserved1[2] + sampleRaw(f32) + sampleSmth(f32) + samplePeak(u8) + reserved2(u8) + fftResult[16] + reserved3(u16) + FFT_Magnitude(f32) + FFT_MajorPeak(f32)`。上游主线 `reserved1/2/3` 大概率恒为 0（MoonModules 分支才用作 pressure/frameCounter/zeroCrossingCount），需实测确认，见 §8.3。
- `sampleRaw`/`sampleSmth` 的语义随节点 AGC 设置改变：AGC 开启时传的是 AGC **之后**的值，原始电平不可得——这是融合模式必须关闭节点 AGC 的直接原因（§5.1）。
- DDP 实时模式**完全旁路**本地特效引擎，两者互斥。但"发送 audioSync"和"渲染像素"是两条独立代码路径，发送不受渲染模式影响——这是本方案"一套静态配置支撑三种模式"的技术基础，但依赖 WLED 在 realtime 模式下 usermod `loop()` 仍正常运行，**这是唯一会推翻整个架构的未验证假设**，见 §8.1。
- 运行时可写 vs 仅配置可写：`AudioReactive.enabled` 和 `AudioReactive.inputLevel` 走 `/json` 状态通道，可随时 POST，不重启不碰 WiFi。`squelch`/`gain`/`AGC`/`frequency.scale`/`dynamics.*`/`sync.port`/`sync.mode`/`digitalmic.*` 只能通过 `http://<node-ip>/settings/um` 网页手工改并保存——项目既有禁令是不用 `POST /json/cfg` 做局部写入（历史上清空过 SSID）。**`sync.mode` 运行时不可改**是整个架构最重要的一条约束，直接导致"节点配置必须静态、模式切换全在 Host 侧"的设计（§3）。

---

## 3. 总体架构

三条约束（`sync.mode` 静态、DDP 与本地特效互斥、发送与渲染正交）共同导出：

> **5 台节点统一静态配置为 `sync.mode = Send`，各占独立端口，一次配置永不再改。所有模式选择在 Host 软件侧完成，运行时零 cfg 写入。**

端口分配（这是本方案新分配的值，不来自任何现有配置文件，可以直接采用）：

| 节点 mDNS | audioSync 端口 |
|---|---|
| `wled-32f5f0` | 11988 |
| `wled-0fdc3c` | 11989 |
| `wled-8dfe78` | 11990 |
| `wled-8e1abc` | 11991 |
| `wled-32e8b4` | 11992 |
| 备用机 | 11993（仅测试用） |

三种模式：

| | A. 独立模式 | B. 单源模式 | C. 融合模式 |
|---|---|---|---|
| 渲染来源 | 节点本地 ♪ 特效 | Host light_engine → DDP | Host light_engine → DDP |
| 音频来源 | 各节点自己的麦 | 指定 1 个节点的麦 | 5 个麦融合 |
| 空间一致性 | 各自独立 | 完全一致 | 完全一致 |
| Host 依赖 | 低（可脱机运行） | 高 | 高 |
| 分段需求 | 需要（§4） | 不需要 | 不需要 |
| 灯效来源 | WLED 内置 ♪ 特效 | 复用现有 spectrum/audio_pulse/bass_pulse，零新灯效代码 | 同左 |

分阶段：阶段 0 备用机验证 → 阶段 1 独立模式（节点侧一次性 web UI 配置 + Host 侧分段下发/inputLevel 校正）→ 阶段 2 单源模式（UDP 接收器 + 接入现有灯效）→ 阶段 3 融合模式（融合算法）。阶段 1 完成后阶段 2/3 不需要再碰节点配置。

---

## 4. 阶段一：独立模式

### 4.1 模式切换时序

停止 DDP 后必须等节点退出 realtime（硬等 3.0s，或轮询 `GET /json/info` 直到所有节点 `"live": false`，更可靠）再下发本地状态，否则会被覆盖，并会闪现一次琥珀色默认色——这和历史上"播放结束灯变黄"是同一个 `if.live.timeout` 机制导致的。退出独立模式时对称地停校正线程 → 关 AudioReactive（可选）→ 灯关掉 → 恢复 DDP。

### 4.2 分段（Segment）设计

**这是本方案里最依赖具体数据、也最容易过期的一步**，所以明确写法：

- node2–node5 每台驱动两条物理灯带（两个 GPIO bus），必须按 bus 边界建 2 个 WLED segment，否则一个特效实例会跨两条物理灯带渲染，流星会串带、频谱条会错位。
- 每台节点每路 bus 的像素数、GPIO、对应 strip_id，**运行时从生产 profile 的 `layout.digital_outputs` 段读取**，不允许写进代码或本文档。生产 profile 是哪一份、板子实际用哪份，见 §0 遗留问题——这个问题不解决，分段代码就不知道该读哪个文件。
- segment 下发用 `POST /json/state`，`stop` 是开区间，多余的旧 segment 用 `{"id":N,"stop":0}` 删除防止残留，全程不碰 `/json/cfg`。

### 4.3 ♪ 特效候选

WLED 187 个特效里，跟"独立模式不依赖 Host、现场演示直观"这个目标最匹配的是 VU-meter 类——点亮长度随音量实时伸缩：

- **Gravimeter**：音量驱动，带重力下落感，官方教程首推入门音频特效，建议作为独立模式默认值。
- **Gravcenter** / **Gravcentric**：从中心展开，后者额外用调色板色相随音量变化。
- **Noisemeter**：叠加 perlin 噪声纹理。

以上只依赖总音量，参数少、行为可预期，建议作为起点。具体效果 ID 需要在设备上通过 `GET /json/eff` 现取（版本间会变，不能硬编码猜测），跟仓库配置无关，允许运行时查。

### 4.4 API 形态

沿用 host-api v1.1 风格，新增 `GET/POST /api/v1/audio-reactive`、`/audio-reactive/set`、`/audio-reactive/calibrate`，新增 scope `audio_reactive:write`，新增错误码 `AUDIO_REACTIVE_UNAVAILABLE`/`MIC_NODE_OFFLINE`，`runtime.state` 追加 `audio_reactive_mode` 字段（非破坏性）。具体字段形状留到实现时定，不在设计阶段固化。
实际接口需要依对方需求而定，在此仅举例，无实际含义

---

## 5. 阶段二/三：Host 侧接收与融合

### 5.1 节点侧目标配置（融合模式）

融合模式下节点 AGC 必须改 Off、squelch 降到最低、5 台 gain 必须完全一致（差异靠 `inputLevel` 补）、sync.mode 改 Send。理由：AGC 开启时 UDP 发送的电平已经是"各自归一化过"的失真值，5 个独立收敛的 AGC 本身就是"不同位置响应不一致"这个问题的成因，不是解决办法——挪到 Host 集中做一次才对。具体目标数值（比如 squelch 设成几）留给实现时在节点 web UI 上填，不需要在设计文档里定死。

### 5.2 Host 接收器

5 个 UDP socket 各绑一个端口加入组播组 `239.0.0.1`，必须显式指定 wlan0 本地 IP（不能用 `INADDR_ANY`，否则可能加入到错误网卡）。板子 IP 是 DHCP，走接口名动态取，不用 `socket.getaddrinfo` 解析 `.local`（这块板子 libnss-mdns 有已知问题，按项目既有约定用 `avahi-resolve`/`avahi-browse`）。

### 5.3 融合算法（七步）

静态增益标定 → 延迟对齐（互相关求各路时延，不做这步多麦融合低频会互相抵消而不是叠加）→ 中位数鲁棒融合（不用平均值，避免一个麦被挡住拖垮全局）→ 置信度门控（包率/数值冻结/电平离群/削顶任一超阈值就踢出，最坏退化到剩 1 个麦仍正常工作）→ 融合后统一做一次噪声门/AGC/beat 检测 → 映射到灯带（见 §5.4）→ 可选注入受控空间差异（避免 5 组灯完全同步显得单调）。

### 5.4 融合结果的落点：复用 `AudioFeatures`

项目里 `light_engine/models.py` 已经定义了 `AudioFeatures`（`rms/bass/mid/treble/spectral_flux/beat/onset/silence`），`SpectrumEffect`/`CueAudioModulator` 已经在消费这个结构，`bass/mid/treble` 的频段定义（20–200/200–2000/2000–12000Hz）跟本方案要做的三段映射天然一致——**不需要新写一套映射逻辑**，融合结果包装成 `AudioFeatures` 对象即可直接喂给现有灯效。

真正需要新写的唯一衔接点：现在 `ctx.audio_features` 是通过按播放时间戳查表得到的（面向"预分析好的媒体音轨"），要接实时麦克风数据，需要新写一个满足同一接口、忽略 timestamp、直接返回最新融合结果的 live data source，插进现有查表逻辑旁边，不用改调用方代码。这是阶段二/三真正的新增工作量。

**范围决策，需要你确认**：融合结果要不要同时驱动 `music_control_state`（供 cue 级的 `audio_modulation.brightness/speed/intensity` 使用），还是只驱动 `audio.*` 系列（供 spectrum/audio_pulse/bass_pulse 使用）？两条是独立消费路径，如果只是想要"能看见跟着响"，接 `audio.*` 就够。

### 5.5 延迟预算

麦克风采样+FFT ~20ms + 组播发包间隔 ~20ms（协议下限）+ 网络与解包 ~5ms + 融合与对齐缓冲 ~10ms + light_engine 渲染与 DDP 帧周期 ~33ms（30fps）+ WLED 接收到点亮 ~5ms ≈ **93ms**。独立/声音模式下 mpv 不播视频，CPU 空闲，DDP 可以提到 50–60fps 省约 13ms；beat 也可以用前几拍间隔外推做预测性提前触发。对包络类、氛围类效果够用，强鼓点会有可察觉滞后，人对灯光延迟的容忍度通常高于音画不同步。

---

## 6. 保护性算法（跨模式共用）

### 6.1 问题

同一段音乐，5 个麦克风因距音箱距离、朝向、外壳遮挡、周围反射面不同，会得到显著不同的电平和频谱。不做处理会导致 5 组灯观感"乱"而不是"随音乐律动"。

### 6.2 静态标定流程

进入标定模式 → 全部节点 inputLevel 置 128 → 现场播一段固定素材（≥30s）→ 采集 5 路电平中位数 → 反算校正系数并下发 inputLevel → 复播验证收敛到彼此 ±15% 以内 → 结果写入 profile。**注意**：标定结果属于运行产出，应该写进 `config/<子目录>/` 下的独立文件（遵守既有的 profile 路径约束），而不是揉进上面提到的、来源尚待确认的那份布局 profile 里——两者关注点不同，混在一起会让"哪份文件管什么"更难追踪。

### 6.3 动态慢速 AGC（Host 侧集中式）

每 3 秒取各节点最近窗口电平的 P90，算出目标值和各节点校正误差，用阻尼系数（建议 0.3）慢速调整 `inputLevel` 并在变化超过死区时下发。这个循环独立模式和融合模式共用，独立模式下它就是全部的保护性算法。实现直接扩展 `host_services/wled_brightness.py`——这个文件已经有 `apply_scale`/`apply_off` 两个函数用 `ThreadPoolExecutor` 并发 POST `/json/state`，`inputLevel` 校正照这个写法加一个函数即可，不新建模块。

现场演示价值：遮住某个麦克风，界面上能看到该节点 `inputLevel` 缓慢上升并被置信度门控踢出，松开后缓慢恢复——这是一个可观测、可解释的保护性算法。

### 6.4 独立模式下的额外一致性措施

5 台节点的 squelch/gain/frequency.scale/dynamics 参数必须完全一致（差异只用 inputLevel 补）；用同一个特效 ID、同一个调色板、同一组 sx/ix；各节点 segment 亮度统一，整体亮度用节点级 `bri` 调；上电默认状态一致。

**安全提醒**：项目里 `system.smoothing.max_brightness` 只在 Host 渲染（DDP）链路生效，独立模式下灯是节点自己渲染，不受这个上限约束。如果现场已经习惯了这个安全余量，独立模式需要单独在节点侧设一个等效的亮度天花板，具体值现场看效果定。

---

## 7. 节点一次性配置清单（阶段一，5 台各执行一次）

全程通过浏览器 `http://<node-ip>/settings/um` 网页操作，**不使用 `POST /json/cfg`**：

- AudioReactive 保持启用，Digitalmic 类型/引脚不动（出厂已正确，不要碰）。
- Config → AGC 改 Off（融合模式最重要的一项；独立模式若单独运行可以保留原值，看 §5.1 的取舍）。
- Sync → Port：5 台分别填 §3 表格里的端口。
- Sync → Mode：改成 Send。
- 不要动页面上方的 I2C/SPI Global GPIO 下拉框（当前未使用，误改需要重启且可能与 LED 输出引脚冲突）。

配置后只读验证：`GET /json/info` 里应看到 `Sound Processing: running`、`UDP Sound Sync` 从 `off` 变成 send 相关字样；`GET /cfg.json` 核对 `um.AudioReactive.sync` 已生效，且 `nw.ins[0].ssid` 没有被意外改动。

---

## 8. 必须实测验证的项目（按优先级，全部可在备用机完成）

1. 🔴 **架构级**：DDP 推流期间节点是否仍在发送 audioSync 包。板子上先在无 DDP 时 `tcpdump -i wlan0 -n udp port 11988 -c 20`，再在 DDP 推流期间跑同一条命令对比包率。若停发或包率显著下降，融合模式架构需要重新评估（改分时设计或独立传感节点）。**这是唯一会推翻整个架构的风险点，放行前必须先做**。
2. 🟠 **语义级**：`sampleSmth` 是否受节点侧 dynamics limiter 影响——分别设 `fall=100` 和 `fall=1400`，抓包对比同一段音频的衰减曲线。
3. 🟠 **字段级**：offset 17 的 `frameCounter`（以及 offset 6-7、34-35）是否递增，可用则白捡一个健康度判据。
4. 🟠 **网络级**：组播在场地 WiFi 上的可靠性，建议跟场地 WiFi 迁移测试一起做，持续测 10 分钟丢包率。
5. 🟡 GEQ 16 段的实际中心频率标定（扫频测试）。
6. 🟡 audioreactive 开启后对 DDP 接收帧率/丢帧的影响。
7. 🟡 麦克风在实际安装状态（装进外壳后）的拾音表现，不能只在桌面测。

---

## 9. 与现有系统的集成约束（不变，摘要）

- profile 路径陷阱：新增的标定结果/端口映射等配置必须放在 `config/<子目录>/` 下，不能放 `data/`，否则 `config_dir` 推导错误导致设备列表静默为空。
- 禁止为找音频节点新增子网扫描逻辑，节点发现只用现有 `resolve_nodes.py` 的 MAC 四级发现。
- 不用 `socket.getaddrinfo` 解析 `.local`。
- 新增 YAML 用 `git add -f` 追踪，板子上用 `git stash -u` 代替 `git clean -fd`。
- 本方案应转化为 CC prompt 实现，pytest 为验证门禁，板子 `git pull --ff-only` 同步。

---

## 10. 待你确认的问题清单

1. **（阻塞 §4.2 分段设计）** `wled-five-board-phase-17.yaml` 和 `rk3588-host-service.yaml` 哪份是板子当前生效配置？两者是否该合并为一份？
2. 融合结果要不要同时驱动 `music_control_state`（cue 级调制），还是只驱动 `audio.*` 系列灯效？
3. 验收想要的视觉形态：是"看得出跟着音乐跳的频谱/律动"，还是"随音量整体明暗呼吸"？后者可以不分段，实现量小很多。
4. 验收方对"一个麦克风控制所有 ESP32"这句话有没有更具体的要求（比如必须外置独立麦克风、必须能现场演示切换）？
5. 物理布局：音箱位置、5 个控制器各自位置和到音箱的距离、是否装在外壳内、场地尺寸。如果各麦到音箱距离差都在 3 米以内，§5.3 延迟对齐这步可以省略。
6. 操作分工：5 台节点 web UI 配置谁来执行（远程还是现场）？标定流程谁配合现场播放？备用机现在谁手上？
7. 阶段优先级：按当前理解阶段 1（独立模式）先做，但阶段 2（单源模式）实际工作量可能更小（不用分段、不用选特效），如果验收更看重"统一控制"这个卖点，要不要反过来先做阶段 2？

---

## 11. 结论

架构不变：`sync.mode` 运行时不可改 → 节点配置统一静态设为 Send + 分端口，所有模式切换在 Host 侧完成。v0.3 相比 v0.2 的变化不是架构上的，而是文档写法上的收紧：**不再把任何"活的"配置数据（像素数、GPIO、IP）抄进设计文档**，只记录去哪个文件读；发现两份 profile 不一致本身就是这条原则要解决的问题的例证。

放行前第一件事仍然是 §8.1 的 tcpdump 验证。第二件事是 §10 问题 1——不确定读哪份 profile，分段代码没法开始写。