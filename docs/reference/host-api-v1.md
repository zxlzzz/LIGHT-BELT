# LIGHT-BELT Host API V1.0 对接说明

本文档面向 APP 开发人员，说明 APP 如何通过 HTTPS REST JSON 与 WSS WebSocket JSON 接入 RK3588 Host Service。RK3588 IP 已确定为 `192.168.31.236`；当前 LIGHT-BELT Host Service 尚未部署到 RK3588，本文档用于 APP 开发、Mock 和接口冻结。

## 1. 快速接入

RK3588 部署后联调信息：

| 项目 | 值 |
|---|---|
| RK3588 IP | `192.168.31.236` |
| HTTPS Base URL | `https://192.168.31.236:8443/api/v1` |
| WebSocket URL | `wss://192.168.31.236:8443/ws` |
| Certificate Fingerprint | 预生成证书指纹：`0A:14:3C:FA:A3:FD:4F:CA:54:94:F4:7E:FE:EE:68:33:F9:BC:5E:29:91:76:DF:66:7C:95:A5:F8:E7:44:9D:4D` |
| Certificate SAN | `DNS: light-belt-rk3588.local`, `IP: 192.168.31.236` |

HTTPS Base URL 和 WebSocket URL 是部署后的固定对接地址。实际联调以部署到 RK3588 的 Host Service 使用的证书为准。

APP 首次接入建议步骤：

1. 配置 `base_url = https://192.168.31.236:8443/api/v1`。
2. 配置 `ws_url = wss://192.168.31.236:8443/ws`。
3. 使用预生成证书指纹进行 APP 开发和 Mock；实际联调时校验 RK3588 Host Service 使用的证书指纹和 SAN。
4. 调用 `GET /status` 确认 Host Service 在线。
5. 调用 `POST /auth/pair` 完成配对，保存 `access_token` 与 `refresh_token`。
6. 后续 REST 请求携带 `Authorization: Bearer <access_token>`。
7. 调用 `GET /capabilities` 获取 APP 可见目标、灯效与消息能力。
8. 调用 `POST /session/ws-ticket` 获取 `ws_ticket`。
9. 使用 `wss://192.168.31.236:8443/ws?ticket=<ws_ticket>` 建立 WebSocket。

## 2. 认证流程

### 配对

APP 调用 `POST /api/v1/auth/pair`，提交：

- `pairing_code`: 当前配对码。
- `client_id`: APP 生成并长期保存的客户端 ID。
- `client_name`: 用户可识别的设备名称。
- `client_type`: `tablet`、`phone` 或 `debug`。
- `app_version`: APP 版本。

服务端返回：

- `access_token`: REST 访问令牌。
- `refresh_token`: 刷新令牌。
- `token_type`: 固定为 `Bearer`。
- `expires_in`: access token 有效秒数。
- `scope`: 当前 token 权限列表。

### REST 鉴权

除 `/auth/pair` 与 `/auth/refresh` 外，REST 请求使用：

```http
Authorization: Bearer <access_token>
```

### 刷新 token

当 REST 返回 `TOKEN_EXPIRED` 时，APP 调用 `POST /api/v1/auth/refresh`，提交 `refresh_token`，获得新的 `access_token` 和 `refresh_token`。

### WebSocket ticket

WebSocket 连接前，APP 调用 `POST /api/v1/session/ws-ticket`：

```json
{
  "subscribe": [
    "runtime.state",
    "playback.progress",
    "device.status",
    "error.event",
    "heartbeat"
  ]
}
```

服务端返回 `ws_ticket` 后，APP 连接：

```text
wss://192.168.31.236:8443/ws?ticket=<ws_ticket>
```

## 3. 通用 HTTP Header

| Header | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `Content-Type` | POST 请求必填 | string | 固定使用 `application/json`。 |
| `Authorization` | 鉴权接口必填 | string | `Bearer <access_token>`。 |
| `X-Request-Id` | 否 | string | APP 生成的请求 ID。服务端会在响应中返回同一个 `request_id`，便于日志关联。 |

## 4. 通用 REST 响应格式

所有 REST 接口返回 JSON envelope。

成功响应：

```json
{
  "ok": true,
  "request_id": "req-20260709-0001",
  "data": {}
}
```

错误响应：

```json
{
  "ok": false,
  "request_id": "req-20260709-0001",
  "error": {
    "code": "INVALID_ARGUMENT",
    "message": "target_id is required",
    "details": {
      "field": "target_id"
    }
  }
}
```

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `ok` | 是 | boolean | `true` 表示请求成功，`false` 表示请求失败。 |
| `request_id` | 是 | string | 请求 ID。优先使用 APP 传入的 `X-Request-Id`。 |
| `data` | 成功时必填 | object | 成功响应数据。 |
| `error.code` | 失败时必填 | string | 错误码。 |
| `error.message` | 失败时必填 | string | 可展示或记录的错误说明。 |
| `error.details` | 否 | object | 字段级或上下文级错误详情。 |

## 5. REST API 详细说明

### GET /api/v1/status

用途：APP 在配对前检测 Host Service 是否在线。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/status` |
| Method | `GET` |
| Header | `X-Request-Id` 可选 |

Request JSON 示例：无请求体。

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| 无 | 否 | - | - | GET 请求不提交 JSON body。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-status-001",
  "data": {
    "service": "light-belt-host",
    "host_id": "rk3588-main",
    "api_version": "1.0",
    "version": "1.0.0",
    "time_ms": 1720000000000
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `service` | 是 | string | 服务名称。 |
| `host_id` | 是 | string | 主机 ID。 |
| `api_version` | 是 | string | Host API 版本。 |
| `version` | 是 | string | Host Service 版本。 |
| `time_ms` | 是 | number | 服务端当前时间，Unix epoch 毫秒。 |

可能的 `error.code`：

- `INTERNAL_ERROR`

### POST /api/v1/auth/pair

用途：APP 使用配对码换取访问令牌。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/auth/pair` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `X-Request-Id` 可选 |

Request JSON 示例：

```json
{
  "pairing_code": "123456",
  "client_id": "tablet-main-room-001",
  "client_name": "Main Room Tablet",
  "client_type": "tablet",
  "app_version": "1.0.0"
}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| `pairing_code` | 是 | string | 非空字符串 | 当前配对码。 |
| `client_id` | 是 | string | 非空字符串 | APP 生成并长期保存的客户端 ID。 |
| `client_name` | 是 | string | 非空字符串 | 设备展示名称。 |
| `client_type` | 是 | string | `tablet`, `phone`, `debug` | 客户端类型。 |
| `app_version` | 是 | string | 非空字符串 | APP 版本号。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-pair-001",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "rt_7d4f3b8f...",
    "token_type": "Bearer",
    "expires_in": 3600,
    "scope": [
      "state:read",
      "playback:write",
      "lights:write",
      "effects:write"
    ]
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `access_token` | 是 | string | REST 访问令牌。 |
| `refresh_token` | 是 | string | 刷新令牌。 |
| `token_type` | 是 | string | 固定为 `Bearer`。 |
| `expires_in` | 是 | number | access token 有效秒数。 |
| `scope` | 是 | string[] | token 权限列表。 |

可能的 `error.code`：

- `INVALID_ARGUMENT`
- `PAIRING_CODE_INVALID`
- `CONFLICT`
- `INTERNAL_ERROR`

### POST /api/v1/auth/refresh

用途：使用 refresh token 获取新的访问令牌。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/auth/refresh` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `X-Request-Id` 可选 |

Request JSON 示例：

```json
{
  "refresh_token": "rt_7d4f3b8f..."
}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| `refresh_token` | 是 | string | 非空字符串 | 配对或刷新时获得的刷新令牌。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-refresh-001",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "rt_90a2c1d5...",
    "token_type": "Bearer",
    "expires_in": 3600,
    "scope": [
      "state:read",
      "playback:write",
      "lights:write",
      "effects:write"
    ]
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `access_token` | 是 | string | 新的 REST 访问令牌。 |
| `refresh_token` | 是 | string | 新的刷新令牌。 |
| `token_type` | 是 | string | 固定为 `Bearer`。 |
| `expires_in` | 是 | number | access token 有效秒数。 |
| `scope` | 是 | string[] | token 权限列表。 |

可能的 `error.code`：

- `INVALID_ARGUMENT`
- `UNAUTHORIZED`
- `TOKEN_EXPIRED`
- `INTERNAL_ERROR`

> `/auth/register`、`/auth/login`、`/auth/logout`、`/auth/password`：预留，当前版本未实现。

### POST /api/v1/session/ws-ticket

用途：申请一次 WebSocket 连接票据。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/session/ws-ticket` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：

```json
{
  "subscribe": [
    "runtime.state",
    "playback.progress",
    "device.status",
    "error.event",
    "heartbeat"
  ]
}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| `subscribe` | 是 | string[] | WebSocket type 枚举 | 希望订阅的 WebSocket 消息类型。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-ticket-001",
  "data": {
    "ws_ticket": "wst_3f610c1a...",
    "session_id": "sess_20260709_0001",
    "expires_in": 60,
    "ws_url": "wss://192.168.31.236:8443/ws?ticket=wst_3f610c1a..."
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `ws_ticket` | 是 | string | WebSocket 连接票据。 |
| `session_id` | 是 | string | 会话 ID。 |
| `expires_in` | 是 | number | ticket 有效秒数。 |
| `ws_url` | 是 | string | 可直接连接的 WebSocket URL。 |

可能的 `error.code`：

- `INVALID_ARGUMENT`
- `UNAUTHORIZED`
- `FORBIDDEN`
- `TOKEN_EXPIRED`
- `INTERNAL_ERROR`

### GET /api/v1/state

用途：获取当前系统、播放、灯光和设备状态。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/state` |
| Method | `GET` |
| Header | `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：无请求体。

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| 无 | 否 | - | - | GET 请求不提交 JSON body。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-state-001",
  "data": {
    "system_state": "running",
    "playback_state": "playing",
    "show_id": "teacher-demo-v1",
    "position_ms": 126000,
    "duration_ms": 300000,
    "brightness": 0.8,
    "color_temperature": 4200,
    "volume": 0.8,
    "muted": false,
    "scene_id": null,
    "audio_available": true,
    "video_available": true,
    "audio_link_enabled": true,
    "video_link_enabled": true,
    "devices": [
      {
        "device_id": "node_1",
        "device_type": "wled_board",
        "status": "online",
        "last_output_ms": 1720000000123,
        "last_seen_ms": 1720000000120,
        "connection_confirmed": true,
        "error_code": null
      }
    ]
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `system_state` | 是 | string | 系统状态。 |
| `playback_state` | 是 | string | 播放状态。 |
| `show_id` | 是 | string 或 null | 当前节目 ID。 |
| `position_ms` | 是 | number | 当前播放位置，单位毫秒。 |
| `duration_ms` | 是 | number | 当前节目总时长，单位毫秒。 |
| `brightness` | 是 | number | 当前亮度，范围 `0.0~1.0`。 |
| `color_temperature` | 是 | number | 当前色温，范围 `2700~6500`。 |
| `volume` | 是 | number | 当前音量，范围 `0.0~1.0`。 |
| `muted` | 是 | boolean | 当前是否静音。 |
| `scene_id` | 是 | string 或 null | 最近一次应用的场景 ID；手动调光/调效或播放节目后重置为 `null`。 |
| `audio_available` | 是 | boolean | 音频输入是否可用。 |
| `video_available` | 是 | boolean | 视频输入是否可用。 |
| `audio_link_enabled` | 是 | boolean | 音频联动是否启用。 |
| `video_link_enabled` | 是 | boolean | 视频联动是否启用。 |
| `devices` | 是 | object[] | 设备状态列表。 |

可能的 `error.code`：

- `UNAUTHORIZED`
- `TOKEN_EXPIRED`
- `INTERNAL_ERROR`

### GET /api/v1/shows

用途：获取可播放节目列表。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/shows` |
| Method | `GET` |
| Header | `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：无请求体。

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| 无 | 否 | - | - | GET 请求不提交 JSON body。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-shows-001",
  "data": {
    "shows": [
      {
        "show_id": "teacher-demo-v1",
        "name": "Teacher Demo",
        "duration_ms": 300000,
        "description": "Main demonstration show"
      }
    ]
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `shows` | 是 | object[] | 可播放节目列表。 |
| `shows[].show_id` | 是 | string | 节目 ID。 |
| `shows[].name` | 是 | string | 节目显示名称。 |
| `shows[].duration_ms` | 是 | number | 节目时长，单位毫秒。 |
| `shows[].description` | 否 | string | 节目说明。 |

可能的 `error.code`：

- `UNAUTHORIZED`
- `TOKEN_EXPIRED`
- `INTERNAL_ERROR`

### GET /api/v1/capabilities

用途：获取 Host Service 暴露给 APP 的目标、灯效、WebSocket 消息类型和功能能力，用于动态生成页面和能力检查。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/capabilities` |
| Method | `GET` |
| Header | `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：无请求体。

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| 无 | 否 | - | - | GET 请求不提交 JSON body。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-capabilities-001",
  "data": {
    "targets": [
      {
        "target_id": "all",
        "name": "全部灯带"
      },
      {
        "target_id": "strip_11",
        "name": "屏幕上方"
      },
      {
        "target_id": "starry_sky",
        "name": "星空灯",
        "supported_effects": ["twinkle"]
      }
    ],
    "effects": [
      {
        "effect_type": "static",
        "name": "Static",
        "params": [
          "color",
          "intensity"
        ],
        "effect_params": []
      },
      {
        "effect_type": "chase",
        "name": "Chase",
        "params": [
          "speed",
          "intensity"
        ],
        "effect_params": [
          "width",
          "gap",
          "direction"
        ]
      }
    ],
    "websocket": {
      "message_types": [
        "session.connected",
        "runtime.state",
        "playback.progress",
        "device.status",
        "error.event",
        "heartbeat"
      ]
    },
    "supports": {
      "playback": true,
      "resume": true,
      "seek": true,
      "lights": true,
      "effects": true,
      "color_temperature": true,
      "transitions": true,
      "websocket": true
    }
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `targets` | 是 | object[] | APP 可见逻辑目标列表。 |
| `targets[].target_id` | 是 | string | APP 调用时使用的目标 ID。`target_id` 为动态词表，具体值由本接口的 `targets` 字段返回；当前部署参考值：`all`、`strip_11`、`strip_12`、`strip_21`、`strip_22`、`strip_31`、`strip_32`、`strip_41`、`strip_43`、`strip_44`、`starry_sky`。 |
| `targets[].name` | 是 | string | APP 展示名称。 |
| `effects` | 是 | object[] | 可用灯效列表。 |
| `effects[].effect_type` | 是 | string | APP 调用时使用的灯效类型。 |
| `effects[].name` | 是 | string | APP 展示名称。 |
| `effects[].params` | 是 | string[] | 通用参数名列表。 |
| `effects[].effect_params` | 是 | string[] | 灯效专用参数名列表。 |
| `websocket.message_types` | 是 | string[] | 可订阅 WebSocket 消息类型。 |
| `supports` | 是 | object | Host Service 功能能力。 |

可能的 `error.code`：

- `UNAUTHORIZED`
- `TOKEN_EXPIRED`
- `INTERNAL_ERROR`

### POST /api/v1/playback/play

用途：播放指定节目，或从指定位置开始播放。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/playback/play` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：

```json
{
  "show_id": "teacher-demo-v1",
  "start_position_ms": 0
}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| `show_id` | 是 | string | 非空字符串 | 要播放的节目 ID。 |
| `start_position_ms` | 否 | number | `>= 0` | 起播位置，单位毫秒；省略时从当前位置或开头播放。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-play-001",
  "data": {
    "playback_state": "playing",
    "show_id": "teacher-demo-v1",
    "position_ms": 0,
    "duration_ms": 300000
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `playback_state` | 是 | string | 当前播放状态。 |
| `show_id` | 是 | string | 当前节目 ID。 |
| `position_ms` | 是 | number | 当前播放位置，单位毫秒。 |
| `duration_ms` | 是 | number | 当前节目时长，单位毫秒。 |

可能的 `error.code`：

- `INVALID_ARGUMENT`
- `UNAUTHORIZED`
- `FORBIDDEN`
- `TOKEN_EXPIRED`
- `NOT_FOUND`
- `CONFLICT`
- `PLAYBACK_NOT_READY`
- `INTERNAL_ERROR`

### POST /api/v1/playback/pause

用途：暂停当前播放。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/playback/pause` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：

```json
{}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| 无 | 否 | - | - | 请求体可传 `{}`。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-pause-001",
  "data": {
    "playback_state": "paused",
    "show_id": "teacher-demo-v1",
    "position_ms": 126000,
    "duration_ms": 300000
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `playback_state` | 是 | string | 当前播放状态。 |
| `show_id` | 是 | string 或 null | 当前节目 ID。 |
| `position_ms` | 是 | number | 当前播放位置，单位毫秒。 |
| `duration_ms` | 是 | number | 当前节目时长，单位毫秒。 |

可能的 `error.code`：

- `UNAUTHORIZED`
- `FORBIDDEN`
- `TOKEN_EXPIRED`
- `PLAYBACK_NOT_READY`
- `INTERNAL_ERROR`

### POST /api/v1/playback/resume

用途：继续播放当前已暂停的节目。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/playback/resume` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：

```json
{}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| 无 | 否 | - | - | 请求体可传 `{}`。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-resume-001",
  "data": {
    "playback_state": "playing",
    "show_id": "teacher-demo-v1",
    "position_ms": 126000,
    "duration_ms": 300000
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `playback_state` | 是 | string | 当前播放状态。 |
| `show_id` | 是 | string 或 null | 当前节目 ID。 |
| `position_ms` | 是 | number | 当前播放位置，单位毫秒。 |
| `duration_ms` | 是 | number | 当前节目时长，单位毫秒。 |

可能的 `error.code`：

- `UNAUTHORIZED`
- `FORBIDDEN`
- `TOKEN_EXPIRED`
- `SHOW_NOT_LOADED`
- `PLAYBACK_NOT_READY`
- `INTERNAL_ERROR`

### POST /api/v1/playback/stop

用途：停止当前播放。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/playback/stop` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：

```json
{}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| 无 | 否 | - | - | 请求体可传 `{}`。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-stop-001",
  "data": {
    "playback_state": "stopped",
    "show_id": null,
    "position_ms": 0,
    "duration_ms": 0
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `playback_state` | 是 | string | 当前播放状态。 |
| `show_id` | 是 | string 或 null | 当前节目 ID。 |
| `position_ms` | 是 | number | 当前播放位置，单位毫秒。 |
| `duration_ms` | 是 | number | 当前节目时长，单位毫秒。 |

可能的 `error.code`：

- `UNAUTHORIZED`
- `FORBIDDEN`
- `TOKEN_EXPIRED`
- `INTERNAL_ERROR`

### POST /api/v1/playback/seek

用途：跳转到当前节目指定位置。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/playback/seek` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：

```json
{
  "position_ms": 90000
}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| `position_ms` | 是 | number | `>= 0` | 目标位置，单位毫秒。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-seek-001",
  "data": {
    "playback_state": "playing",
    "show_id": "teacher-demo-v1",
    "position_ms": 90000,
    "duration_ms": 300000
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `playback_state` | 是 | string | 当前播放状态。 |
| `show_id` | 是 | string | 当前节目 ID。 |
| `position_ms` | 是 | number | 当前播放位置，单位毫秒。 |
| `duration_ms` | 是 | number | 当前节目时长，单位毫秒。 |

可能的 `error.code`：

- `INVALID_ARGUMENT`
- `UNAUTHORIZED`
- `FORBIDDEN`
- `TOKEN_EXPIRED`
- `SHOW_NOT_LOADED`
- `PLAYBACK_NOT_READY`
- `INTERNAL_ERROR`

### POST /api/v1/lights/set

用途：设置目标灯光的亮度、色温和过渡时间。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/lights/set` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：

```json
{
  "target_id": "screen_surround",
  "brightness": 0.72,
  "color_temperature": 4200,
  "transition_ms": 800
}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| `target_id` | 是 | string | target_id 枚举 | 目标区域。 |
| `brightness` | 条件必填 | number | `0.0~1.0` | 目标亮度；与 `color_temperature` 至少提交一个。 |
| `color_temperature` | 条件必填 | number | `2700~6500` | 目标色温；与 `brightness` 至少提交一个。 |
| `transition_ms` | 否 | number | `>= 0` | 过渡时间，单位毫秒；省略时为 `0`。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-lights-001",
  "data": {
    "target_id": "screen_surround",
    "brightness": 0.72,
    "color_temperature": 4200,
    "transition_ms": 800,
    "accepted": true
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `target_id` | 是 | string | 已接受的目标区域。 |
| `brightness` | 否 | number | 已接受的亮度。 |
| `color_temperature` | 否 | number | 已接受的色温。 |
| `transition_ms` | 是 | number | 已接受的过渡时间，单位毫秒。 |
| `accepted` | 是 | boolean | 命令是否已接受。 |

可能的 `error.code`：

- `INVALID_ARGUMENT`
- `UNAUTHORIZED`
- `FORBIDDEN`
- `TOKEN_EXPIRED`
- `NOT_FOUND`
- `DEVICE_OFFLINE`
- `INTERNAL_ERROR`

### POST /api/v1/effects/set

用途：为目标区域设置灯效。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/effects/set` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例一：为连续路径设置追逐灯效。

```json
{
  "target_id": "virtual_path.screen_to_wall",
  "effect_type": "chase",
  "params": {
    "speed": 0.65,
    "intensity": 0.8
  },
  "effect_params": {
    "width": 6,
    "gap": 12,
    "direction": "forward"
  },
  "transition_ms": 500
}
```

Request JSON 示例二：为屏幕环绕区域设置静态颜色。

```json
{
  "target_id": "screen_surround",
  "effect_type": "static",
  "params": {
    "color": {
      "r": 255,
      "g": 180,
      "b": 80
    },
    "intensity": 0.8
  },
  "transition_ms": 500
}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| `target_id` | 是 | string | target_id 枚举 | 目标区域。 |
| `effect_type` | 是 | string | effect_type 枚举 | 灯效类型。 |
| `params` | 否 | object | - | 通用灯效参数。 |
| `params.color.r` | 否 | number | `0~255` | 红色通道。 |
| `params.color.g` | 否 | number | `0~255` | 绿色通道。 |
| `params.color.b` | 否 | number | `0~255` | 蓝色通道。 |
| `params.speed` | 否 | number | `0.0~1.0` | 速度。 |
| `params.intensity` | 否 | number | `0.0~1.0` | 强度。 |
| `effect_params` | 否 | object | - | 灯效专用参数。 |
| `transition_ms` | 否 | number | `>= 0` | 切换过渡时间，单位毫秒。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-effects-001",
  "data": {
    "target_id": "virtual_path.screen_to_wall",
    "effect_type": "chase",
    "transition_ms": 500,
    "accepted": true
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `target_id` | 是 | string | 已接受的目标区域。 |
| `effect_type` | 是 | string | 已接受的灯效类型。 |
| `transition_ms` | 是 | number | 已接受的过渡时间，单位毫秒。 |
| `accepted` | 是 | boolean | 命令是否已接受。 |

可能的 `error.code`：

- `INVALID_ARGUMENT`
- `UNAUTHORIZED`
- `FORBIDDEN`
- `TOKEN_EXPIRED`
- `NOT_FOUND`
- `DEVICE_OFFLINE`
- `INTERNAL_ERROR`

### GET /api/v1/audio

用途：获取当前音量和静音状态。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/audio` |
| Method | `GET` |
| Header | `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：无请求体。

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| 无 | 否 | - | - | GET 请求不提交 JSON body。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-audio-001",
  "data": {
    "volume": 0.8,
    "muted": false,
    "audio_output_available": true
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `volume` | 是 | number | 当前音量，范围 `0.0~1.0`。 |
| `muted` | 是 | boolean | 当前是否静音。 |
| `audio_output_available` | 是 | boolean | 音频输出是否可用。 |

可能的 `error.code`：

- `UNAUTHORIZED`
- `TOKEN_EXPIRED`
- `INTERNAL_ERROR`

### POST /api/v1/audio/set

用途：设置音量或静音状态。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/audio/set` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：

```json
{
  "volume": 0.6,
  "muted": false,
  "transition_ms": 0
}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| `volume` | 条件 | number | `0.0~1.0` | 目标音量。`volume` 与 `muted` 至少提交一个。 |
| `muted` | 条件 | boolean | - | 是否静音。`volume` 与 `muted` 至少提交一个。 |
| `transition_ms` | 否 | number | `>= 0` | 过渡时间，单位毫秒。当前版本无实际效果，等同于 0。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-audio-set-001",
  "data": {
    "volume": 0.6,
    "muted": false,
    "transition_ms": 0,
    "accepted": true
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `volume` | 是 | number | 已接受的音量。 |
| `muted` | 是 | boolean | 已接受的静音状态。 |
| `transition_ms` | 是 | number | 已接受的过渡时间，单位毫秒。 |
| `accepted` | 是 | boolean | 命令是否已接受。 |

可能的 `error.code`：

- `INVALID_ARGUMENT`（`volume` 与 `muted` 均未提交时返回）
- `UNAUTHORIZED`
- `TOKEN_EXPIRED`
- `INTERNAL_ERROR`

### GET /api/v1/scenes

用途：获取已保存场景列表。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/scenes` |
| Method | `GET` |
| Header | `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：无请求体。

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| 无 | 否 | - | - | GET 请求不提交 JSON body。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-scenes-001",
  "data": {
    "scenes": [
      {
        "scene_id": "reading-mode",
        "name": "阅读模式",
        "created_ms": 1720000000000,
        "updated_ms": 1720000001000
      }
    ]
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `scenes` | 是 | object[] | 已保存场景列表（最多 32 条）。 |
| `scenes[].scene_id` | 是 | string | 场景 ID。 |
| `scenes[].name` | 是 | string | 场景展示名称。 |
| `scenes[].created_ms` | 是 | number | 创建时间，Unix epoch 毫秒。 |
| `scenes[].updated_ms` | 是 | number | 最近更新时间，Unix epoch 毫秒。 |

可能的 `error.code`：

- `UNAUTHORIZED`
- `TOKEN_EXPIRED`
- `INTERNAL_ERROR`

### POST /api/v1/scenes/save

用途：保存当前灯光状态为场景，或更新已有场景。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/scenes/save` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：

```json
{
  "scene_id": "reading-mode",
  "name": "阅读模式",
  "audio": {
    "volume": 0.6,
    "muted": false
  },
  "entries": [
    {
      "target_id": "strip_11",
      "brightness": 0.8,
      "color_temperature": 4200,
      "transition_ms": 500
    }
  ]
}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| `scene_id` | 否 | string | `^[a-z0-9-]{1,64}$` | 场景 ID；省略时自动生成。 |
| `name` | 是 | string | 非空 | 场景展示名称。 |
| `audio` | 条件 | object | - | 音频设置。`audio` 与 `entries` 至少提交一个。 |
| `audio.volume` | 否 | number | `0.0~1.0` | 场景音量。 |
| `audio.muted` | 否 | boolean | - | 场景静音状态。 |
| `entries` | 条件 | object[] | 至少 1 条 | 灯光目标设置列表。`audio` 与 `entries` 至少提交一个。 |
| `entries[].target_id` | 是 | string | target_id 枚举 | 目标区域。 |
| `entries[].brightness` | 否 | number | `0.0~1.0` | 亮度。 |
| `entries[].color_temperature` | 否 | number | `2700~6500` | 色温。 |
| `entries[].effect_type` | 否 | string | effect_type 枚举 | 灯效类型。 |
| `entries[].transition_ms` | 否 | number | `>= 0` | 过渡时间，单位毫秒。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-scenes-save-001",
  "data": {
    "scene_id": "reading-mode",
    "saved": true
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `scene_id` | 是 | string | 已保存的场景 ID。 |
| `saved` | 是 | boolean | 是否保存成功。 |

可能的 `error.code`：

- `INVALID_ARGUMENT`（`name` 为空，或 `audio` 与 `entries` 均未提交时返回）
- `CONFLICT`（已达 32 条场景上限时返回 `SCENE_LIMIT_EXCEEDED`）
- `UNAUTHORIZED`
- `TOKEN_EXPIRED`
- `INTERNAL_ERROR`

### POST /api/v1/scenes/apply

用途：应用已保存场景。自动停止当前播放节目。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/scenes/apply` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：

```json
{
  "scene_id": "reading-mode",
  "transition_ms": 500
}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| `scene_id` | 是 | string | 非空 | 要应用的场景 ID。 |
| `transition_ms` | 否 | number | `>= 0` | 过渡时间，单位毫秒。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-scenes-apply-001",
  "data": {
    "scene_id": "reading-mode",
    "accepted": true,
    "partial": false,
    "failed_targets": []
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `scene_id` | 是 | string | 已应用的场景 ID。 |
| `accepted` | 是 | boolean | 命令是否已接受。 |
| `partial` | 是 | boolean | 是否部分目标应用失败。 |
| `failed_targets` | 是 | string[] | 应用失败的 `target_id` 列表。 |

可能的 `error.code`：

- `NOT_FOUND`（场景 ID 不存在）
- `UNAUTHORIZED`
- `TOKEN_EXPIRED`
- `INTERNAL_ERROR`

### POST /api/v1/scenes/delete

用途：删除已保存场景。

| 项目 | 值 |
|---|---|
| URL | `https://192.168.31.236:8443/api/v1/scenes/delete` |
| Method | `POST` |
| Header | `Content-Type: application/json`, `Authorization: Bearer <access_token>`, `X-Request-Id` 可选 |

Request JSON 示例：

```json
{
  "scene_id": "reading-mode"
}
```

Request 字段解释：

| 字段 | 必填 | 类型 | 枚举/范围 | 说明 |
|---|---:|---|---|---|
| `scene_id` | 是 | string | 非空 | 要删除的场景 ID。 |

Response JSON 示例：

```json
{
  "ok": true,
  "request_id": "req-scenes-delete-001",
  "data": {
    "scene_id": "reading-mode",
    "deleted": true
  }
}
```

Response 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `scene_id` | 是 | string | 已删除的场景 ID。 |
| `deleted` | 是 | boolean | 是否删除成功。 |

可能的 `error.code`：

- `NOT_FOUND`（场景 ID 不存在）
- `UNAUTHORIZED`
- `TOKEN_EXPIRED`
- `INTERNAL_ERROR`

## 6. WebSocket 说明

连接地址：

```text
wss://192.168.31.236:8443/ws?ticket=<ws_ticket>
```

消息格式：

```json
{
  "type": "runtime.state",
  "timestamp": 1720000000000,
  "sequence": 1024,
  "data": {}
}
```

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `type` | 是 | string | 消息类型。 |
| `timestamp` | 是 | number | 服务端发送时间，Unix epoch 毫秒。 |
| `sequence` | 是 | number | 服务端递增消息序号。 |
| `data` | 是 | object | 消息数据。 |

WebSocket 连接建立后，服务端会发送 `session.connected`。APP 可根据 `sequence` 做消息排序和去重。

## 7. WebSocket 消息类型

### session.connected

触发时机：WebSocket 连接认证成功后发送一次。

JSON 示例：

```json
{
  "type": "session.connected",
  "timestamp": 1720000000000,
  "sequence": 1,
  "data": {
    "session_id": "sess_20260709_0001",
    "subscribe": [
      "runtime.state",
      "playback.progress",
      "device.status",
      "error.event",
      "heartbeat"
    ]
  }
}
```

data 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `session_id` | 是 | string | 当前 WebSocket 会话 ID。 |
| `subscribe` | 是 | string[] | 当前会话已订阅消息类型。 |

### runtime.state

触发时机：系统状态、播放状态、亮度、色温、输入可用性或设备概览发生变化时发送。

JSON 示例：

```json
{
  "type": "runtime.state",
  "timestamp": 1720000000100,
  "sequence": 2,
  "data": {
    "system_state": "running",
    "playback_state": "playing",
    "show_id": "teacher-demo-v1",
    "brightness": 0.8,
    "color_temperature": 4200,
    "audio_available": true,
    "video_available": true,
    "audio_link_enabled": true,
    "video_link_enabled": true
  }
}
```

data 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `system_state` | 是 | string | 系统状态。 |
| `playback_state` | 是 | string | 播放状态。 |
| `show_id` | 是 | string 或 null | 当前节目 ID。 |
| `brightness` | 是 | number | 当前亮度。 |
| `color_temperature` | 是 | number | 当前色温。 |
| `audio_available` | 是 | boolean | 音频输入是否可用。 |
| `video_available` | 是 | boolean | 视频输入是否可用。 |
| `audio_link_enabled` | 是 | boolean | 音频联动是否启用。 |
| `video_link_enabled` | 是 | boolean | 视频联动是否启用。 |

### playback.progress

触发时机：播放位置变化、播放状态变化或节目切换时发送。

JSON 示例：

```json
{
  "type": "playback.progress",
  "timestamp": 1720000000200,
  "sequence": 3,
  "data": {
    "playback_state": "playing",
    "show_id": "teacher-demo-v1",
    "position_ms": 126000,
    "duration_ms": 300000
  }
}
```

data 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `playback_state` | 是 | string | 播放状态。 |
| `show_id` | 是 | string 或 null | 当前节目 ID。 |
| `position_ms` | 是 | number | 当前播放位置，单位毫秒。 |
| `duration_ms` | 是 | number | 当前节目时长，单位毫秒。 |

### device.status

触发时机：设备在线状态、输出时间或错误码变化时发送。

JSON 示例：

```json
{
  "type": "device.status",
  "timestamp": 1720000000300,
  "sequence": 4,
  "data": {
    "devices": [
      {
        "device_id": "analog.ceiling_left",
        "device_type": "light_zone",
        "status": "online",
        "last_output_ms": 1720000000290,
        "last_seen_ms": 1720000000288,
        "connection_confirmed": true,
        "error_code": null,
        "debug": {
          "node_id": 1,
          "node_type": "analog_rgbcct"
        }
      }
    ]
  }
}
```

data 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `devices` | 是 | object[] | 设备状态列表。 |
| `devices[].device_id` | 是 | string | APP 可理解的逻辑设备 ID。 |
| `devices[].device_type` | 是 | string | 对外设备类型。 |
| `devices[].status` | 是 | string | 设备状态。 |
| `devices[].last_output_ms` | 是 | number | 最近一次输出时间，Unix epoch 毫秒。 |
| `devices[].last_seen_ms` | 否 | number | 最近一次收到设备状态时间，Unix epoch 毫秒。 |
| `devices[].connection_confirmed` | 是 | boolean | Host Service 当前是否确认该逻辑设备连接状态。 |
| `devices[].error_code` | 是 | string 或 null | 当前设备错误码。 |
| `devices[].debug.node_id` | 否 | number | 调试信息。 |
| `devices[].debug.node_type` | 否 | string | 调试信息。 |

### error.event

触发时机：请求失败、播放失败、设备错误或服务端运行错误时发送。

JSON 示例：

```json
{
  "type": "error.event",
  "timestamp": 1720000000400,
  "sequence": 5,
  "data": {
    "error_code": "DEVICE_OFFLINE",
    "message": "Device digital.screen_to_wall is offline",
    "details": {
      "device_id": "digital.screen_to_wall"
    }
  }
}
```

data 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `error_code` | 是 | string | 错误码。 |
| `message` | 是 | string | 错误说明。 |
| `details` | 否 | object | 错误详情。 |

### heartbeat

触发时机：WebSocket 保活周期到达时发送。

JSON 示例：

```json
{
  "type": "heartbeat",
  "timestamp": 1720000000500,
  "sequence": 6,
  "data": {
    "session_id": "sess_20260709_0001"
  }
}
```

data 字段解释：

| 字段 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `session_id` | 是 | string | 当前 WebSocket 会话 ID。 |

## 8. 字段字典

| 字段 | 类型 | 必填位置 | 说明 |
|---|---|---|---|
| `pairing_code` | string | `/auth/pair` request | 当前配对码。 |
| `service` | string | `/status` response | 服务名称。 |
| `host_id` | string | `/status` response | 主机 ID。 |
| `api_version` | string | `/status` response | Host API 版本。 |
| `version` | string | `/status` response | Host Service 版本。 |
| `time_ms` | number | `/status` response | 服务端当前时间，Unix epoch 毫秒。 |
| `client_id` | string | `/auth/pair` request | APP 生成并长期保存的客户端 ID。 |
| `client_name` | string | `/auth/pair` request | 设备展示名称。 |
| `client_type` | string | `/auth/pair` request | 客户端类型。 |
| `app_version` | string | `/auth/pair` request | APP 版本号。 |
| `access_token` | string | auth response | REST 访问令牌。 |
| `refresh_token` | string | auth response, `/auth/refresh` request | 刷新令牌。 |
| `token_type` | string | auth response | 固定为 `Bearer`。 |
| `expires_in` | number | auth/session response | 有效秒数。 |
| `scope` | string[] | auth response | 权限列表。 |
| `ws_ticket` | string | `/session/ws-ticket` response | WebSocket 连接票据。 |
| `session_id` | string | session response, WebSocket data | 会话 ID。 |
| `subscribe` | string[] | `/session/ws-ticket` request, `session.connected` data | WebSocket 订阅消息类型。 |
| `system_state` | string | state/runtime response | 系统状态。 |
| `playback_state` | string | state/playback response | 播放状态。 |
| `show_id` | string 或 null | state/playback response | 节目 ID。 |
| `position_ms` | number | state/playback response | 播放位置，单位毫秒。 |
| `duration_ms` | number | state/playback response | 总时长，单位毫秒。 |
| `brightness` | number | state/lights | 亮度，范围 `0.0~1.0`。 |
| `color_temperature` | number | state/lights | 色温，范围 `2700~6500`。 |
| `audio_available` | boolean | state/runtime response | 音频输入是否可用。 |
| `video_available` | boolean | state/runtime response | 视频输入是否可用。 |
| `audio_link_enabled` | boolean | state/runtime response | 音频联动是否启用。 |
| `video_link_enabled` | boolean | state/runtime response | 视频联动是否启用。 |
| `targets` | object[] | `/capabilities` response | APP 可见逻辑目标列表。 |
| `target_id` | string | capabilities/lights/effects | Host Service 暴露给 APP 的逻辑目标。 |
| `effects` | object[] | `/capabilities` response | 可用灯效列表。 |
| `effect_type` | string | effects request/response | 灯效类型。 |
| `params` | object | effects request | 通用灯效参数。 |
| `effect_params` | object | effects request | 灯效专用参数。 |
| `supports` | object | `/capabilities` response | Host Service 功能能力。 |
| `transition_ms` | number | lights/effects request/response | 过渡时间，单位毫秒。 |
| `device_id` | string | device state | APP 可理解的逻辑设备 ID。 |
| `device_type` | string | device state | 对外设备类型。 |
| `status` | string | device state | 设备状态。 |
| `last_output_ms` | number | device state | 最近一次输出时间，Unix epoch 毫秒。 |
| `last_seen_ms` | number | device state | 最近一次收到设备状态时间，Unix epoch 毫秒。 |
| `connection_confirmed` | boolean | device state | Host Service 当前是否确认该逻辑设备连接状态。 |
| `debug.node_id` | number | device state | 可选调试信息。 |
| `debug.node_type` | string | device state | 可选调试信息。 |
| `error_code` | string 或 null | device/error state | 错误码。 |

## 9. 枚举值表

### client_type

| 值 | 说明 |
|---|---|
| `tablet` | 平板客户端。 |
| `phone` | 手机客户端。 |
| `debug` | 调试客户端。 |

### system_state

| 值 | 说明 |
|---|---|
| `idle` | 空闲。 |
| `ready` | 已准备。 |
| `running` | 运行中。 |
| `error` | 错误。 |

### playback_state

| 值 | 说明 |
|---|---|
| `idle` | 空闲。 |
| `playing` | 播放中。 |
| `paused` | 已暂停。 |
| `stopped` | 已停止。 |
| `error` | 错误。 |

### target_id

这些值是 Host Service 暴露给 APP 的逻辑目标，不是文件路径，也不是硬件节点地址。
**实际可用的 `target_id` 列表由引擎配置文件（`ENGINE_PROFILE_PATH`）中的布局在启动时动态生成，
通过 `GET /capabilities` 的 `targets` 数组获取。** 固定项如下：

| 值 | 说明 |
|---|---|
| `all` | 全部数字灯带（广播目标）。 |
| `strip_<label>` | 单条数字灯带，label 为物理标签，例如 `strip_11`、`strip_22`。具体列表从布局文件派生。 |
| `starry_sky` | 星空灯（UDP 拨动设备，192.168.31.205:3333）。独立目标，不属于数字灯带。 |

`starry_sky` 支持的 `effect_type`：

| `effect_type` | 说明 |
|---|---|
| `twinkle` | 开启星空灯（闪烁效果）。 |
| 其他值 | 关闭星空灯。 |

`starry_sky` 的 `GET /capabilities` 响应格式：

```json
{
  "target_id": "starry_sky",
  "name": "星空灯",
  "supported_effects": ["twinkle"]
}
```

### effect_type

| 值 | 说明 |
|---|---|
| `static` | 静态颜色。 |
| `breath` | 呼吸。 |
| `color_wave` | 色彩波动。 |
| `chase` | 追逐。 |
| `comet` | 彗星拖尾。 |
| `audio_pulse` | 音频脉冲。 |
| `bass_pulse` | 低频脉冲。 |
| `spectrum` | 频谱。 |
| `video_ambient` | 视频环境色。 |
| `video_audio_fusion` | 视频音频融合。 |
| `calm` | 平静氛围。 |
| `demo` | 演示循环。 |
| `twinkle` | 星空灯闪烁（仅对 `starry_sky` 有效）。 |

### device_type

| 值 | 说明 |
|---|---|
| `wled_board` | WLED ESP32 控制板（每块对应一条 WS2811 灯带）。 |

### device status

| 值 | 说明 |
|---|---|
| `online` | 在线。 |
| `offline` | 离线。 |
| `error` | 错误。 |

### WebSocket type

| 值 | 说明 |
|---|---|
| `session.connected` | 会话已连接。 |
| `runtime.state` | 运行状态。 |
| `playback.progress` | 播放进度。 |
| `device.status` | 设备状态。 |
| `error.event` | 错误事件。 |
| `heartbeat` | 心跳。 |

## 10. 错误码表

| error.code | 含义 | APP 建议处理方式 |
|---|---|---|
| `INVALID_ARGUMENT` | 请求字段缺失、类型错误或超出范围。 | 检查请求参数，修正后重试。 |
| `UNAUTHORIZED` | 缺少 token 或 token 无效。 | 跳转认证流程或使用 refresh token。 |
| `FORBIDDEN` | token 权限不足。 | 提示权限不足，重新配对或联系管理员。 |
| `NOT_FOUND` | 请求的资源不存在。 | 刷新列表或检查 `show_id` / `target_id`。 |
| `CONFLICT` | 当前状态与请求冲突。 | 先同步 `/state`，再按最新状态发起请求。 |
| `TOKEN_EXPIRED` | access token 已过期。 | 调用 `/auth/refresh` 后重试原请求。 |
| `PAIRING_CODE_INVALID` | 配对码无效。 | 提示用户重新输入配对码。 |
| `WS_TICKET_INVALID` | WebSocket ticket 无效或过期。 | 重新调用 `/session/ws-ticket` 后重连。 |
| `DEVICE_OFFLINE` | 目标设备离线。 | 在设备页提示离线，并等待 `device.status` 更新。 |
| `SHOW_NOT_LOADED` | 当前没有已加载节目。 | 先调用 `/playback/play` 指定 `show_id`。 |
| `PLAYBACK_NOT_READY` | 播放控制暂不可执行。 | 读取 `/state`，在状态变为 `ready` 或 `running` 后重试。 |
| `MPV_UNAVAILABLE` | mpv 播放器不可用（进程启动失败或 socket 目录不存在）。 | 检查设备上 mpv 是否已安装及 `/run/light-belt` 目录是否存在（systemd `RuntimeDirectory=light-belt`）。 |
| `SCENE_LIMIT_EXCEEDED` | 已达场景上限（32 条）。 | 先删除不需要的场景，再重试保存。 |
| `INTERNAL_ERROR` | 服务端内部错误。 | 记录 `request_id` 和错误信息，稍后重试。 |
