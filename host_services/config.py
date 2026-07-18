"""
集中配置，相当于 Spring 的 application.yml。
本地测试时不需要改任何值；部署 RK3588 时按注释调整。
"""

import os

# ── 网络 ──
HOST = "0.0.0.0"
PORT = 8443

# ── 认证 ──
JWT_SECRET = "light-belt-dev-secret-change-in-production"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 3600      # 1 小时
REFRESH_TOKEN_EXPIRE_SECONDS = 86400    # 24 小时
PAIRING_CODE = "123456"                 # 本地测试用固定配对码

# ── WebSocket ──
WS_TICKET_EXPIRE_SECONDS = 60
HEARTBEAT_INTERVAL_SECONDS = 5

# ── 场景 ──
SCENE_MAX_COUNT = 32
SCENE_FILE_PATH = "data/scenes.json"    # 运行时数据，不进 git

# ── 节目单 ──
SHOWS_MANIFEST_PATH = "data/shows_manifest.json"  # 运行时数据，不进 git

# ── TLS（生产部署用，本地默认关闭） ──
ENABLE_TLS = False
TLS_CERTFILE = "/etc/light-belt/cert.pem"
TLS_KEYFILE = "/etc/light-belt/key.pem"

# ── mpv IPC（生产环境用；可用环境变量覆盖，本地调试可设 /tmp/mpv.sock） ──
MPV_SOCKET_PATH = os.environ.get("MPV_SOCKET_PATH", "/run/light-belt/mpv.sock")
# mpv 视频输出的 DISPLAY；仅当进程环境未设置 DISPLAY 时生效
MPV_DISPLAY = os.environ.get("MPV_DISPLAY", ":0")

# ── 版本信息 ──
SERVICE_NAME = "light-belt-host"
HOST_ID = "rk3588-main"
API_VERSION = "1.0"
SERVICE_VERSION = "1.0.0"
