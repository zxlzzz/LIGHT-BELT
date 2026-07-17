# ESP32-S3 一灯带一节点现场烧录手册（Windows）

状态：**NOT HARDWARE VERIFIED**。

本文用于 Phase 31 的 ESP32-S3 批量烧录与留档。生产合同是一条 WS2811
灯带对应一块 ESP32-S3；每个节点只有 `output_id: 1`，数据引脚为 GPIO4。
烧录成功只证明固件写入成功，不证明 Wi-Fi、UDP、灯带、电源或整场同步已经通过
硬件验收。

所有 `esp32-s3-node-N` 生产镜像强制使用 scheduled UDP v3：Host 广播单调
时钟 beacon，并对同一逻辑帧统一设置 20 ms 后的 `apply_at_us`。节点使用 beacon
有界窗口中的最小 local-minus-Host offset 换算本地时钟。生产固件不会把 immediate
frame 当作降级方案；显式 Node 2 诊断镜像才保留 immediate 行为。该软件合同已经
实现，真实多节点锁存同步仍须上电并用逻辑分析仪验收。

当前正式 profile 仍使用 20 ms lead、500 ms 运行 beacon 和 5 个间隔 10 ms
的启动 beacon；这些参数尚未通过硬件门禁。Node 2 robust A/B 使用的是 60 ms
lead、100 ms 运行 beacon 和 32 个间隔 50 ms 的启动 beacon。正式参数迁移属于
P1 Scheduled 门禁，不得混入 Immediate/SPI6 输出验收。

每次 scheduled show 启动时，Host 必须先完成所有节点的 sequence-1 KEY 编码，
再以相同 apply/media identity 和每节点相同 raw 连续发送三轮，轮间 2 ms。固件
幂等去重这些副本；完成 KEY preparation 后即准入该 generation。之后若定时物理
输出失败，固件恢复上一帧或安全黑，并允许下一张完整 scheduled frame 恢复，不能
在 deadline 后盲目重发同一 wire transaction。

## 1. 固定节点合同

| Node | 逻辑灯带 | Groups | Output / GPIO | 现场 IPv4 | 当前九节点 | 已记录 MAC |
|---:|---|---:|---|---|---|---|
| 1 | `strip_11` | 10 | 1 / GPIO4 | `192.168.31.201` | 是 | `e0:72:a1:d3:53:34` |
| 2 | `strip_41` | 10 | 1 / GPIO4 | `192.168.31.202` | 是 | `e0:72:a1:d3:30:3c` |
| 3 | `strip_44` | 20 | 1 / GPIO4 | `192.168.31.203` | 否 | 待实物分配 |
| 4 | `strip_12` | 40 | 1 / GPIO4 | `192.168.31.204` | 是 | `e0:72:a1:d2:7e:08` |
| 5 | `strip_22` | 40 | 1 / GPIO4 | `192.168.31.205` | 是 | `e0:72:a1:d3:08:b0` |
| 6 | `strip_21` | 10 | 1 / GPIO4 | `192.168.31.206` | 是 | 现场记录 |
| 7 | `strip_31` | 10 | 1 / GPIO4 | `192.168.31.207` | 是 | 现场记录 |
| 8 | `strip_42` | 20 | 1 / GPIO4 | `192.168.31.208` | 是 | 现场记录 |
| 9 | `strip_91` | 20 | 1 / GPIO4 | `192.168.31.209` | 是 | 现场记录 |
| 10 | `strip_92` | 20 | 1 / GPIO4 | `192.168.31.210` | 是 | 现场记录 |
| 11 | `strip_43` | 20 | 1 / GPIO4 | `192.168.31.211` | 否 | 待实物分配 |
| 12 | `strip_45` | 20 | 1 / GPIO4 | `192.168.31.212` | 否 | 待实物分配 |
| 13 | `strip_93` | 20 | 1 / GPIO4 | `192.168.31.213` | 否 | 待实物分配 |

当前现场批次只烧录节点 `1`、`2`、`4`、`5`、`6`、`7`、`8`、`9`、
`10`。没有对应实物板时，不得为了凑齐完整拓扑而烧录、贴签或记录节点 `3`、`11`、
`12`、`13`。新增实物板以后按同一流程单独完成剩余节点。

## 2. 开始前的停止条件

1. PowerShell 当前目录必须是仓库根目录。
2. 一次只连接一块 ESP32；每块板都重新识别 COM 口。
3. 实物板、Node、逻辑灯带、groups、IP 和 MAC 必须能落在同一条记录中。
4. `config.local.h` 只保存 Wi-Fi 凭据；Node 只能由本次构建的
   `esp32-s3-node-N` PlatformIO 环境选择。
5. 不修改 `node_X.h` 来绕过映射、GPIO、groups 或地址不一致。
6. 不把真实 Wi-Fi 密码写入本文、终端历史、截图或 Git 跟踪文件。
7. 上一块板未贴签、未退出串口监视器、未断开 USB 前，不连接下一块板。
8. 任一检查失败只处理当前板，不上传旧 `firmware.bin`，也不跳到下一块。

## 3. 一次性准备

打开 PowerShell：

```powershell
$Repository = (Get-Location).Path
if (-not (Test-Path -LiteralPath `
    (Join-Path $Repository 'config\profiles\ws2811-installed-one-esp-per-strip.yaml'))) {
  throw '当前目录不是包含 Phase 31 改动的仓库 checkout。请先进入正确 worktree 或已集成分支。'
}
git branch --show-current
git status --short --branch

$Project = (Resolve-Path 'firmware\esp32_ws2811_node').Path
$ConfigPath = Join-Path $Project 'src\config.local.h'
$Pio = (Get-Command pio).Source
if (-not $Pio.StartsWith('A:\', [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "PlatformIO 不在 A 盘：$Pio"
}

$env:PLATFORMIO_CORE_DIR = Join-Path $Project '.pio\core'
$env:PLATFORMIO_PLATFORMS_DIR = Join-Path $Project '.pio\platforms'
$env:PLATFORMIO_PACKAGES_DIR = Join-Path $Project '.pio\packages'
$env:PLATFORMIO_CACHE_DIR = Join-Path $Project '.pio\cache'
$env:PLATFORMIO_BUILD_CACHE_DIR = Join-Path $Project '.pio\cache\build'
$BuildTemp = Join-Path $Project '.pio\tmp'
New-Item -ItemType Directory -Force -Path $BuildTemp | Out-Null
$env:TEMP = $BuildTemp
$env:TMP = $BuildTemp
$env:TMPDIR = $BuildTemp
$env:PLATFORMIO_SETTING_ENABLE_TELEMETRY = 'No'
```

`$Repository`、`$Project`、`$Pio`、PlatformIO 状态目录和临时目录必须全部
位于 A 盘。不要让构建重新使用用户目录中的 `.platformio` 或 C 盘临时目录。

只在本地配置不存在时创建：

```powershell
if (-not (Test-Path -LiteralPath $ConfigPath)) {
  Copy-Item `
    "$Project\src\config.local.example.h" `
    $ConfigPath
}
```

用记事本只填写本地 Wi-Fi：

```powershell
notepad $ConfigPath
```

示例结构：

```cpp
#define WIFI_SSID "REPLACE_WITH_WIFI_SSID"
#define WIFI_PASSWORD "REPLACE_WITH_WIFI_PASSWORD"
```

不要在 `config.local.h` 中加入 `node_X.h`、`NODE_ID`、`OUTPUT_COUNT` 或
`LIGHT_BELT_NODE_CONFIG`。密码只保存在这个未跟踪文件中。以下检查不打印密码：

```powershell
$LocalConfig = Get-Content -LiteralPath $ConfigPath -Raw
if ($LocalConfig -match 'REPLACE_WITH_WIFI|PLACEHOLDER_') {
  throw 'config.local.h 仍包含 Wi-Fi 占位值，停止烧录。'
}
if ($LocalConfig -match 'node_configs|NODE_ID|OUTPUT_COUNT|LIGHT_BELT_NODE_CONFIG') {
  throw 'config.local.h 只能包含 Wi-Fi 凭据，停止烧录。'
}
```

## 4. 每块板的标准动作

### 4.1 识别当前板

只连接当前板，然后查询串口：

```powershell
Get-CimInstance Win32_SerialPort |
  Sort-Object DeviceID |
  Select-Object DeviceID, Name
```

将实际端口写入 `$Port`，不要沿用上一块板的 COM 号：

```powershell
$Port = 'COM9'
Write-Host "本次烧录端口：$Port"
```

不能确定端口时，拔下当前板查询一次，再插入并重新查询；新增端口才属于当前板。

### 4.2 选择并验证 Node

为当前实物板设置 Node，并由它生成唯一构建环境。下面以 Node 8 为例：

```powershell
$Node = 8
if ($Node -notin 1..13) {
  throw "Node 必须在 1 至 13 之间：$Node"
}
$Environment = "esp32-s3-node-$Node"
$EnvironmentHeader = "[env:$Environment]"
if (-not (Select-String `
    -LiteralPath (Join-Path $Project 'platformio.ini') `
    -SimpleMatch $EnvironmentHeader -Quiet)) {
  throw "platformio.ini 缺少环境：$Environment"
}
Write-Host "本次 Node：$Node；构建环境：$Environment；端口：$Port"
```

屏幕显示的 `$Node`、`$Environment` 和 `$Port` 必须与实物标签及第 1 节的
同一目标行一致。切换实物板时只重新设置 `$Node`、`$Environment` 和 `$Port`；
不要修改 `config.h`、`config.local.h` 或 `node_X.h` 来选择 Node。

### 4.3 Clean、构建和上传

每次切换 Node 都执行 clean：

```powershell
pio run -d $Project -e $Environment -t clean
pio run -d $Project -e $Environment
```

构建末尾必须出现 `[SUCCESS]`，硬件摘要必须显示 16MB Flash，且没有 `Error`
或 `FAILED`。然后上传当前板：

```powershell
pio run -d $Project -e $Environment `
  -t upload --upload-port $Port
```

只有上传命令末尾出现 `[SUCCESS]` 才算写入完成。上传日志中的 MAC 必须：

- 节点 1、2、4、5：与第 1 节已有记录完全一致；
- 节点 6-10：立即写入现场记录，后续不得把另一块板沿用为同一 Node；
- 未来节点 3、11-13：分配实物时首次记录，并经第二人复核。

MAC 不符时停止，不修改 Node 配置来迁就错误实物板。

### 4.4 上传失败时进入下载模式

只有出现 `Failed to connect`、`No serial data received` 或持续连接超时时：

1. 按住 `BOOT`。
2. 点按并松开 `RST/EN`。
3. 松开 `BOOT`。
4. 重新识别 `$Port` 并重试上传。

若 COM 口变化，必须更新 `$Port`。仍失败时检查 USB 数据线、串口连接和供电，不更换
Node 配置碰运气。

### 4.5 启动、地址和标签复核

上传成功后打开监视器：

```powershell
pio device monitor --port $Port --baud 115200
```

复位并观察约 10 秒：

- 不得反复出现 Wi-Fi 占位错误；
- 不得出现无效输出配置；
- 当前 Node、groups、output 1 / GPIO4 和 IPv4 必须与第 1 节目标行一致；
- 生产镜像必须显示固定 `spi_dma_fixed_gpio4` 后端，且不得出现
  `fatal scheduled_output_unsupported`；
- 未实际联网或接灯时，不得把无报错当成硬件验收。

按 `Ctrl+C` 退出监视器。立即贴
`Node X / strip_YY / GPIO4 / 192.168.31.2ZZ` 标签，填写记录并拔下 USB。

## 5. 当前九节点烧录顺序

严格按以下顺序重复第 4 节：

```text
1 -> 2 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10
```

每一步都必须重新设置 `$Node` 和 `$Environment`，再 clean、构建、上传、核对 MAC、
复核启动信息、贴签并断开。不要在这一批次插入节点 3、11、12、13，也不要复用旧
五节点拓扑中 Node 1、2、4 的多输出固件。

## 6. 逐板上电验收

烧录和标签完成后，每次仍只接一块控制器和它对应的一条灯带：

1. 核对数据线只来自该 ESP32 的 GPIO4，经独立 SN74LVC1T45 到该灯带 DI。
2. 核对 Host 使用
   `config/profiles/ws2811-installed-one-esp-per-strip.yaml`。
3. 验证该 Node 的 IP 可达，UDP v3 帧只包含 output 1，groups 与表格一致；
   同时确认 beacon 被接收、`clock_ready=1` 且 scheduled frame 开始提交。
4. 确认生产帧包含同一 Host-monotonic `apply_at_us`，其值约为发送准备时刻后
   20 ms；不得向生产固件发送 immediate frame。
5. 依次验证全黑、低亮度红、绿、蓝和动态效果；全黑期间不得存在常亮区段。
6. 停止发送并验证超时进入安全黑；恢复发送后不得回放陈旧帧。
7. 不复位 ESP32，结束并重新启动同一 show；确认新的 `KEY_FRAME`/sequence 1
   被接受；确认三轮 KEY 只产生一次物理 commit，`session_key_dupes` 记录冗余
   副本，而普通重复或陈旧非 KEY 帧仍被拒绝。
8. 记录供电、固件版本、profile/show、beacon/clock/scheduled 统计、结果和任何异常。

固件 output task 每轮必须先检查安全超时，即使队列持续有帧也不能推迟安全黑。
scheduled SPI 失败后不得越过已校验 deadline 盲目重发；应 fail closed 并恢复已提交
帧或安全黑。

一块板通过不能证明其他节点或多节点同时运行已通过。

## 7. 原子切换到现场九节点

逐板验收完成后再安排维护窗口：

1. 冻结九节点的 Node/strip/MAC/IP/固件记录并归档 `validate-show` 和
   `inspect-topology` 输出。
2. 停止 Host 物理输出并关闭灯光系统电源。
3. 完成九条数据线的独立连接；每块 ESP32 只连接表中自己的灯带。
4. Host 一次性选择
   `config/profiles/ws2811-installed-one-esp-per-strip.yaml`。
5. 上电后先发全黑，再验证逐节点隔离、同时主色、共享 sequence 和
   `apply_at_us`、beacon/clock readiness、超时和恢复。
6. 按第 7.3 节用逻辑分析仪记录 10/20/40 groups 的发送时长与跨节点锁存偏差。
7. 运行第 7.1 节当前九条的 300 秒 staged show，记录丢帧、重启、deadline
   error、可见偏差、温升和电源异常。

不得在 live run 中混用旧五节点 profile、旧多输出固件、新单输出固件和新接线。任一
门禁失败时先停止输出并断电，再把 profile、固件集和接线作为整体回滚。九节点通过也
不能写成完整 13 节点通过。

### 7.1 当前九节点：验证、检查和运行

在仓库根目录依次执行；三条命令必须使用同一组 profile/show：

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/ws2811-installed-one-esp-per-strip.yaml `
  validate-show --show config/shows/ws2811-stage3-installed-300s.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/ws2811-installed-one-esp-per-strip.yaml `
  inspect-topology --show config/shows/ws2811-stage3-installed-300s.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/ws2811-installed-one-esp-per-strip.yaml run `
  --show config/shows/ws2811-stage3-installed-300s.yaml
```

`inspect-topology` 必须显示九条数字灯带，Node 集合为
`1, 2, 4, 5, 6, 7, 8, 9, 10`，每个 Node 只有 output 1 / GPIO4。

### 7.2 完整十三数字节点：验证、检查和运行

只有节点 1-13 全部具有已核对的实物板、标签、MAC、IP、固件和独立灯带后，才执行：

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/cabin-lighting-v3-site-local.yaml `
  validate-show --show config/shows/ws2811-stage3-full-300s.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/cabin-lighting-v3-site-local.yaml `
  inspect-topology --show config/shows/ws2811-stage3-full-300s.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/cabin-lighting-v3-site-local.yaml run `
  --show config/shows/ws2811-stage3-full-300s.yaml
```

该组合每个逻辑帧向十三个 ESP32 各发送一个 UDP v3 数据报。两个 site profile 都是
UDP-only，均未启用 RS-485；它们不能控制或验收 `zone_32` COB。COB 必须使用已明确
配置串口并启用 RS-485 的独立现场流程验收，不能把数字节点全通过写成 COB 通过。

### 7.3 多节点 scheduled latch 验收

此项必须在灯带、控制器和共同地全部上电后执行，软件测试或肉眼视频不能代替逻辑
分析仪记录：

1. 同时采集至少一条 10 groups、一条 20 groups 和一条 40 groups 节点的
   GPIO4/电平转换后数据线，并关联同一 sequence / `apply_at_us`。
2. 核对 3.2 MHz 四位 `1000`/`1100` 编码完整事务及前后各 200-byte
   低电平 guard：10 groups 为 520 bytes / 1300 us，20 groups 为 640 bytes /
   1600 us，40 groups 为 880 bytes / 2200 us。三种长度必须从不同
   `tx_start` 开始，而不是同时开始发送。
3. 核对 Host 使用 `192.168.31.255:9001` 的 monotonic clock beacon 和统一
   20 ms apply 提前量；节点统计中的 `beacon_ok`、`clock_samples`、
   `clock_ready`、`scheduled_commit` 与 `deadline_error_us` 必须留档。
4. 确认 sequence-1 KEY 在所有节点发送前已全部编码，三轮间隔 2 ms，单节点三份
   raw 完全相同，且只产生一次 session generation 和物理 commit；
   `session_key_dupes` 应记录冗余副本。
5. `clock_not_ready`、`scheduled_late`、`scheduled_far`、
   `scheduled_invalid`、`scheduled_start_late`、`scheduled_cancelled` 或
   `immediate_dropped` 在稳定运行中增加时停止验收并定位，不得切换为 immediate。
6. 保存原始逻辑分析仪捕获、固件/Host版本、节点映射、profile/show、统计日志和
   实测跨节点锁存偏差。没有这些记录时，只能写“软件已实现”，不能写“严格同步
   已通过硬件验收”。

## 8. 烧录与验收记录模板

| 时间 | 操作者 | Node | 灯带 | MAC | IP | COM | 构建/上传 | 单节点颜色/黑场 | 标签 |
|---|---|---:|---|---|---|---|---|---|---|
|  |  | 1 | `strip_11` | `e0:72:a1:d3:53:34` | `.201` |  |  |  |  |
|  |  | 2 | `strip_41` | `e0:72:a1:d3:30:3c` | `.202` |  |  |  |  |
|  |  | 4 | `strip_12` | `e0:72:a1:d2:7e:08` | `.204` |  |  |  |  |
|  |  | 5 | `strip_22` | `e0:72:a1:d3:08:b0` | `.205` |  |  |  |  |
|  |  | 6 | `strip_21` |  | `.206` |  |  |  |  |
|  |  | 7 | `strip_31` |  | `.207` |  |  |  |  |
|  |  | 8 | `strip_42` |  | `.208` |  |  |  |  |
|  |  | 9 | `strip_91` |  | `.209` |  |  |  |  |
|  |  | 10 | `strip_92` |  | `.210` |  |  |  |  |

完整 13 节点后续验收必须为节点 3、11、12、13 新增真实记录，不得用空白行、预留 IP
或软件测试代替实物证据。

## 9. 常见故障的停止条件

| 现象 | 处理 |
|---|---|
| 找不到或占用 COM 口 | 拔插当前板、关闭监视器、重新识别，不继续上传 |
| `$Node` 超出 1-13 或缺少对应环境 | 修正 `$Node`，确认 `esp32-s3-node-N` 环境后重新 clean |
| 构建或上传 `FAILED` | 不上传或复用旧 `firmware.bin`，只处理当前板 |
| MAC 与已有记录不符 | 停止并重新确认实物板，不修改配置迁就 |
| Node、groups、output、GPIO 或 IP 不符 | 停止，不修改 `node_X.h`，交回项目负责人 |
| 全黑仍有灯段常亮或其他灯带受影响 | 停止多节点上电，记录接线、地参考、信号和帧证据 |
| UDP 中断后未进入安全黑 | 停止，不进入整组验收 |
| 多节点 sequence 不一致或出现陈旧帧 | 停止 300 秒 show，检查 profile、Host 和固件版本 |
| `clock_ready` 不为 1 或 beacon/drop 计数异常 | 停止，检查广播地址、子网、Host 时钟和固件环境 |
| scheduled drop 或 `immediate_dropped` 增加 | 停止，不降级为 immediate；检查 deadline、时钟窗口和生产 profile |
| 三轮 KEY 产生多次 generation/commit，或 generation 0 接受非 KEY | 停止，核对 Host/固件版本、session admission 和 `session_key_dupes` |
| KEY preparation 后的输出失败使后续完整帧永久被门禁 | 停止；固件必须回滚物理输出但保留该 generation 的 admission |
| scheduled SPI 失败后出现第二次越期事务 | 停止，固件必须 fail closed，不得盲目 retry |
| 逻辑分析仪时长不是 1300/1600/2200 us 或跨节点锁存偏差未留档 | 不得声称严格同步硬件通过 |

完成真实记录前，所有物理结果仍为 **NOT HARDWARE VERIFIED**。
