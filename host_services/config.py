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

# ── 引擎 ──
import pathlib as _pl
_DEFAULT_PROFILE = str(
    _pl.Path(__file__).resolve().parent.parent
    / "config" / "profiles" / "rk3588-host-service.yaml"
)
ENGINE_PROFILE_PATH: str = os.environ.get("ENGINE_PROFILE_PATH", _DEFAULT_PROFILE)
# "mock" (default, in-memory) or "real" (subprocess light_engine)
ENGINE_ADAPTER: str = os.environ.get("ENGINE_ADAPTER", "mock")

# ── TLS（生产部署用，本地默认关闭） ──
ENABLE_TLS = False
TLS_CERTFILE = "/etc/light-belt/cert.pem"
TLS_KEYFILE = "/etc/light-belt/key.pem"

# ── mpv IPC（生产环境用；可用环境变量覆盖，本地调试可设 /tmp/mpv.sock） ──
MPV_SOCKET_PATH = os.environ.get("MPV_SOCKET_PATH", "/run/light-belt/mpv.sock")
# mpv 视频输出的 DISPLAY；仅当进程环境未设置 DISPLAY 时生效
MPV_DISPLAY = os.environ.get("MPV_DISPLAY", ":0")
# X11 认证文件路径；仅当进程环境未设置 XAUTHORITY 时生效
MPV_XAUTHORITY = os.environ.get("MPV_XAUTHORITY", "/home/topeet/.Xauthority")
# mpv 窗口几何（配合 --no-border 铺满屏幕，而不用 --fullscreen；
# --fullscreen 曾在现场导致 LED 灯光同步异常，改用显式几何尺寸绕开 WM 全屏路径）
MPV_GEOMETRY = os.environ.get("MPV_GEOMETRY", "1920x1080+0+0")

# 是否启用 xrandr 视频输出检测（mock 模式默认关闭以免测试环境报错）
VIDEO_DETECT_ENABLED: bool = ENGINE_ADAPTER == "real"

# ── 亮度乘数 ──
BRIGHTNESS_SCALE_DEFAULT: float = 0.5
WLED_HTTP_TIMEOUT_S: float = 1.0

# ── 版本信息 ──
SERVICE_NAME = "light-belt-host"
HOST_ID = "rk3588-main"
API_VERSION = "1.0"
SERVICE_VERSION = "1.0.0"


# ── Git commit（远程运维用：现场板子当前 checkout 的 commit）──
def _read_git_commit() -> str:
    """读取当前 checkout 的 git commit 短哈希。

    直接读 .git 文件而非 fork `git`，因此不依赖 git 二进制在 PATH、
    也不会在每次 /status 请求时创建子进程。任何失败都降级为 "unknown"，
    绝不让版本探测异常炸掉 status 端点。
    """
    try:
        repo_root = _pl.Path(__file__).resolve().parent.parent
        git_dir = repo_root / ".git"
        if not git_dir.exists():
            return "unknown"
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            ref_path = git_dir / ref
            if ref_path.exists():
                sha = ref_path.read_text(encoding="utf-8").strip()
            else:
                packed = git_dir / "packed-refs"
                sha = "unknown"
                if packed.exists():
                    for line in packed.read_text(encoding="utf-8").splitlines():
                        if line.endswith(" " + ref):
                            sha = line.split(" ", 1)[0].strip()
                            break
        else:
            sha = head
        if sha and sha != "unknown" and len(sha) >= 7:
            return sha[:12]
        return "unknown"
    except Exception:
        return "unknown"


# 启动时计算一次并缓存（进程生命周期内不变；git pull 后需重启服务才更新）
GIT_COMMIT: str = _read_git_commit()
