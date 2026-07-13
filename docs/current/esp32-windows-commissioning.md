# ESP32-S3 现场批量烧录操作手册（Windows）

状态：**NOT HARDWARE VERIFIED**。

本文只说明如何把当前仓库中的 ESP32-S3 固件依次烧入现场控制板，以及一块烧完后
怎样切换到下一块。不要在这份流程中顺带修改灯带映射、GPIO、像素数、协议或现场
拓扑。遇到不一致时停止，不要靠猜测继续烧录。

## 1. 本批次固定烧录清单

严格按下列顺序操作，一次只连接一块板：

| 顺序 | 实物板 | 已记录 MAC | 烧入配置 | 烧后标签 |
|---:|---|---|---|---|
| 1 | ESP32 1 | `e0:72:a1:d3:53:34` | `node_configs/node_1.h` | `ESP32 1 / Node 1` |
| 2 | ESP32 2 | `e0:72:a1:d3:30:3c` | `node_configs/node_2.h` | `ESP32 2 / Node 2` |
| 3 | ESP32 4 | `e0:72:a1:d2:7e:08` | `node_configs/node_4.h` | `ESP32 4 / Node 4` |
| 4 | ESP32 5 | `e0:72:a1:d3:08:b0` | `node_configs/node_5.h` | `ESP32 5 / Node 5` |

Node 3 仅为未来逻辑预留，当前没有对应实物板，本批次不烧录 Node 3。

## 2. 每次开始前的硬性规则

1. PowerShell 当前目录必须是 `A:\BaiduNetdiskDownload\LIGHT-BELT`。
2. 电脑上一次只连接当前要烧的那一块 ESP32。
3. 每块板开始前都重新识别串口，不沿用上一块板的 COM 号假设。
4. 每块板都先确认 `config.local.h` 选中了正确的 Node，再清理、构建、上传。
5. 上一块板没有贴完标签、退出串口监视器并断开 USB 前，不连接下一块板。
6. 看到 `SUCCESS` 只能说明对应步骤成功；构建成功不等于上传成功。
7. 不把真实 Wi-Fi 密码写入本文、聊天、截图、提交记录或受 Git 跟踪的文件。

## 3. 一次性准备 PowerShell 和本地配置

### 3.1 打开仓库根目录

新开一个 PowerShell 窗口，执行：

```powershell
Set-Location 'A:\BaiduNetdiskDownload\LIGHT-BELT'
Get-Location
Get-Command pio
```

`Get-Location` 必须显示本仓库；`Get-Command pio` 必须能找到 PlatformIO。任一命令报错
都先停止，不要连接控制板开始烧录。

### 3.2 只在文件不存在时创建本地配置

先检查：

```powershell
$ConfigPath = 'firmware\esp32_ws2811_node\src\config.local.h'
Test-Path $ConfigPath
```

如果输出 `True`，不要再执行复制命令，以免覆盖已经填写的现场密码。

只有输出 `False` 时才执行：

```powershell
Copy-Item `
  firmware\esp32_ws2811_node\src\config.local.example.h `
  firmware\esp32_ws2811_node\src\config.local.h
```

### 3.3 填写 Wi-Fi，并先选择 Node 1

```powershell
notepad $ConfigPath
```

第一次烧 ESP32 1 时，文件的有效配置应为：

```cpp
#define WIFI_SSID "灵境"
#define WIFI_PASSWORD "现场真实密码"

#include "node_configs/node_1.h"
```

真实密码只写在 `config.local.h`。保存并关闭记事本。不要把密码粘贴回 PowerShell，
也不要运行会把整份配置内容打印到屏幕上的命令。

用下面的检查确认占位值已经被替换，但不显示真实密码：

```powershell
$LocalConfig = Get-Content -LiteralPath $ConfigPath -Raw
if ($LocalConfig -match 'REPLACE_WITH_WIFI|PLACEHOLDER_') {
  throw 'config.local.h 仍包含 Wi-Fi 占位值，停止烧录。'
}
Write-Host 'Wi-Fi 占位值检查通过。'
```

## 4. 每块板共用的标准动作

后面四块板都重复本节动作。先设置固定变量：

```powershell
$Project = 'firmware\esp32_ws2811_node'
$ConfigPath = "$Project\src\config.local.h"
```

### 4.1 只连接当前板并识别串口

连接当前板后执行：

```powershell
Get-CimInstance Win32_SerialPort |
  Sort-Object DeviceID |
  Select-Object DeviceID, Name
```

找到当前 USB 转串口设备，把实际端口写入变量。例如本机显示 COM9 时：

```powershell
$Port = 'COM9'
Write-Host "本次烧录端口：$Port"
```

COM5、COM9 等编号会随电脑变化，这是正常现象。不要因为另一台电脑曾使用 COM5，
就在本机直接写死 COM5。

如果不能确定哪一个端口属于当前板：拔下 USB、执行一次串口查询；重新插入当前板、
再执行一次。新增的端口才是本次应使用的端口。

### 4.2 修改并核对 Node 选择

打开配置：

```powershell
notepad $ConfigPath
```

只修改最后的 `#include`。SSID 和密码在整个批次中保持不变。保存并关闭记事本后，执行：

```powershell
$NodeIncludes = Get-Content -LiteralPath $ConfigPath |
  Where-Object { $_ -match '^#include "node_configs/node_[1-5]\.h"$' }
$NodeIncludes
if (@($NodeIncludes).Count -ne 1) {
  throw '必须且只能启用一个 node_X.h，停止烧录。'
}
```

屏幕只能出现一条 Node include，并且必须与当前实物板同号。

### 4.3 清理上一块板的构建产物

切换 Node 后必须清理，避免把上一块板生成的固件误传给下一块板：

```powershell
pio run -d $Project -e esp32-s3-devkitc-1 -t clean
```

必须看到清理命令正常结束。若失败，不继续构建。

### 4.4 构建当前板固件

```powershell
pio run -d $Project -e esp32-s3-devkitc-1
```

构建通过时必须同时满足：

- 末尾出现 `[SUCCESS]`。
- 硬件摘要显示 `16MB Flash`。
- 没有 `Error` 或 `FAILED`。

PlatformIO 可能仍显示基础板名称中的 `N8 (8 MB QD, No PSRAM)`，那是继承的基础板
显示名；本项目展开后的实际构建参数必须是 16MB Flash、`qio_opi` 和
`BOARD_HAS_PSRAM`。以本项目已验证的构建配置和 `HARDWARE ... 16MB Flash` 为准。

### 4.5 上传到当前板

先确保没有其他串口工具占用 `$Port`，然后执行：

```powershell
pio run -d $Project -e esp32-s3-devkitc-1 `
  -t upload --upload-port $Port
```

正常上传通常会依次经历连接、识别 ESP32-S3、擦除/写入、校验和复位。只有命令末尾
出现 `[SUCCESS]` 才算上传完成。把日志中显示的 MAC 与本手册表格核对。

### 4.6 自动连接失败时手动进入下载模式

只有上传出现 `Failed to connect`、`No serial data received` 或持续连接超时时才执行：

1. 按住板上的 `BOOT` 键不放。
2. 点按一次 `RST` 或 `EN` 键，然后松开 `RST/EN`。
3. 再松开 `BOOT` 键，使板保持在下载模式。
4. 确认 `$Port` 仍是当前串口。
5. 重新执行上传命令。

若操作 BOOT 后 COM 号发生变化，重新查询串口并更新 `$Port`，不要继续使用已经消失
的端口。仍失败时检查 USB 数据线、USB 转串口连接和供电，但不要改 Node 配置碰运气。

### 4.7 上传后做串口复核

上传成功后打开串口监视器：

```powershell
pio device monitor --port $Port --baud 115200
```

点按一次 `RST/EN` 让新固件重新启动，观察约 10 秒：

- 不应反复出现 `WiFi placeholder SSID`。
- 不应出现 `Invalid multi-output configuration`。
- 当前固件在配置正常时可能不主动打印成功信息；没有日志本身不代表烧录失败。

按 `Ctrl+C` 退出监视器。必须先退出监视器，否则下一次上传可能报串口被占用。

### 4.8 立即贴签、记录并断开

完成当前板后立刻执行三件事：

1. 在实物板上贴本手册规定的 `ESP32 X / Node X` 标签。
2. 在烧录记录中填写实物编号、Node、MAC、COM 号、上传结果和操作者。
3. 拔下当前板 USB，确认电脑上已经没有这块板的串口，再开始下一块。

不要把未贴签的已烧板放回待烧板区域。每次构建会覆盖同一输出目录中的
`firmware.bin`，所以不能仅凭文件时间或文件名判断它属于哪个 Node。

## 5. 流水线逐块执行

### 5.1 烧录 ESP32 1 为 Node 1

1. 只连接 ESP32 1。
2. 查询并设置本次 `$Port`。
3. 确认唯一 include 是：

   ```cpp
   #include "node_configs/node_1.h"
   ```

4. 执行清理、构建、上传。
5. 核对上传日志 MAC 为 `e0:72:a1:d3:53:34`。
6. 用 115200 波特率复核启动日志，然后按 `Ctrl+C`。
7. 贴 `ESP32 1 / Node 1` 标签并填写记录。
8. 拔下 ESP32 1。

如果 MAC 不符，立刻停止。不要把错误实物板继续当作 ESP32 1。

### 5.2 ESP32 1 完成后，开始烧录 ESP32 2

1. 确认 ESP32 1 已贴签、已记录、已拔下。
2. 连接且只连接 ESP32 2。
3. 重新查询 COM 号，并重新设置 `$Port`；即使仍显示 COM9，也要重新确认。
4. 打开 `config.local.h`，只把 Node include 改成：

   ```cpp
   #include "node_configs/node_2.h"
   ```

5. 运行 Node include 唯一性检查，确认屏幕只显示 `node_2.h`。
6. 重新执行 clean。不能复用 Node 1 的构建产物。
7. 重新构建并确认 `[SUCCESS]`、16MB Flash。
8. 上传到当前 `$Port`，核对 MAC 为 `e0:72:a1:d3:30:3c`。
9. 串口复核后按 `Ctrl+C` 退出。
10. 贴 `ESP32 2 / Node 2` 标签、填写记录、拔下 ESP32 2。

Node 2 的第三路即使暂未接灯带，也必须保留现有 `node_2.h` 完整配置；烧录人员不得
修改该头文件。

### 5.3 ESP32 2 完成后，开始烧录 ESP32 4

1. 确认 ESP32 2 已贴签、已记录、已拔下。
2. 连接且只连接 ESP32 4，重新识别 `$Port`。
3. 把唯一 Node include 改成：

   ```cpp
   #include "node_configs/node_4.h"
   ```

4. 依次执行唯一性检查、clean、构建和上传。
5. 核对上传日志 MAC 为 `e0:72:a1:d2:7e:08`。
6. 串口复核后退出监视器。
7. 贴 `ESP32 4 / Node 4` 标签、填写记录、拔下 ESP32 4。

### 5.4 ESP32 4 完成后，开始烧录 ESP32 5

开始前必须确认现场连接的是独立标号为 ESP32 5 的板。

1. 确认 ESP32 4 已贴签、已记录、已拔下。
2. 连接且只连接 ESP32 5，重新识别 `$Port`。
3. 把唯一 Node include 改成：

   ```cpp
   #include "node_configs/node_5.h"
   ```

4. 依次执行唯一性检查、clean、构建和上传。
5. 核对上传日志 MAC 为 `e0:72:a1:d3:08:b0`。
6. 串口复核后退出监视器。
7. 贴 `ESP32 5 / Node 5` 标签，并把 MAC 和上传结果填入记录。
8. 拔下 ESP32 5。

## 6. 烧录完成后的收尾

四块板烧完后，不再修改或重烧任何板，先完成以下收尾：

1. 确认桌面上只有四块已贴签板：Node 1、Node 2、Node 4、Node 5。
2. 确认未来预留的 Node 3 没有在本批次被烧录。
3. 对照上传日志逐项确认 Node 1、2、4 的 MAC 与留档一致。
4. 确认 Node 5 的 MAC 为 `e0:72:a1:d3:08:b0`。
5. 确认每一块板都有一次构建 `[SUCCESS]` 和一次上传 `[SUCCESS]` 记录。
6. 确认所有串口监视器均已按 `Ctrl+C` 退出。
7. 保留 `config.local.h` 在本机，不提交、不发送，也不要删除到需要重新询问密码。
8. 将四块板分别装入防静电袋或明确分区，保持标签可见，交给下一步网络地址绑定和
   上电验收流程。

烧录完成只证明固件写入成功，不等于 Wi-Fi、UDP、灯带输出或整车效果已经通过硬件
验证。未完成后续上电验收前，状态仍为 **NOT HARDWARE VERIFIED**。

## 7. 烧录记录模板

每块板烧完立即填一行，不要等四块全部完成后凭记忆补写：

| 时间 | 操作者 | 实物板 | Node | MAC | COM | 构建 | 上传 | 启动日志复核 | 标签 |
|---|---|---|---:|---|---|---|---|---|---|
|  |  | ESP32 1 | 1 | `e0:72:a1:d3:53:34` |  | 成功/失败 | 成功/失败 | 通过/异常 | 已贴/未贴 |
|  |  | ESP32 2 | 2 | `e0:72:a1:d3:30:3c` |  | 成功/失败 | 成功/失败 | 通过/异常 | 已贴/未贴 |
|  |  | ESP32 4 | 4 | `e0:72:a1:d2:7e:08` |  | 成功/失败 | 成功/失败 | 通过/异常 | 已贴/未贴 |
|  |  | ESP32 5 | 5 | `e0:72:a1:d3:08:b0` |  | 成功/失败 | 成功/失败 | 通过/异常 | 已贴/未贴 |

## 8. 常见烧录故障的停止条件

| 现象 | 处理 |
|---|---|
| 找不到 COM 口 | 拔插当前板、重新查询；检查数据线和 USB 转串口，不继续上传 |
| COM 口被占用 | 关闭串口监视器和其他串口软件，再重试 |
| `No serial data received` | 按第 4.6 节手动进入下载模式，重新识别 COM |
| 上传日志 MAC 与表格不符 | 停止并重新确认实物编号，不继续下一块 |
| 配置检查出现两个 Node include | 停止，修正到只剩当前 Node 的一条 include |
| 构建显示 `FAILED` | 不上传旧的 `firmware.bin`，先解决本次构建失败 |
| 上传显示 `FAILED` | 不贴已完成标签，不开始下一块 |
| 启动日志出现 Wi-Fi 占位值 | 修正本机配置后 clean、重建、重新上传当前板 |
| 启动日志提示输出配置无效 | 停止，不修改 Node 头文件，交回项目负责人检查 |

任何失败都只重做当前板。不要跳到下一块，也不要用上一块的固件文件继续上传。
