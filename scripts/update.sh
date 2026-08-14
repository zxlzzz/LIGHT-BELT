#!/usr/bin/env bash
# LIGHT-BELT 自更新 + 自动回滚
# 由 systemd timer 调用，以 topeet 身份运行（sudo 免密可重启服务）。
# 板子部署分支为 deploy：只跟 origin/deploy，不跟 main。
# 设计前提：板子出站能访问 github；只依赖出站，不需要任何入站/穿透。
#
# 流程：记录当前 commit → fetch → 有新版本则 ff-only 合并 → 依赖变更则重装 →
#       重启服务 → 健康检查(带重试，校验 commit 已更新) →
#       失败则 git reset --hard 回滚 + 重装依赖 + 重启 + 记日志 →
#       拉不到网则静默跳过，不改变现状。

set -uo pipefail

REPO="/home/topeet/LIGHT-BELT"
BRANCH="deploy"
VENV_PIP="$REPO/.venv/bin/pip"
SERVICE="light-belt-host.service"
HEALTH_URL="http://127.0.0.1:8443/api/v1/status"
LOG="/home/topeet/lb-update.log"
HEALTH_RETRIES=10
HEALTH_INTERVAL=3

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

cd "$REPO" || { log "FATAL: 无法进入 $REPO"; exit 1; }

health_ok() {
    local want="$1" i body got
    for ((i=1; i<=HEALTH_RETRIES; i++)); do
        body="$(curl -s -m 5 "$HEALTH_URL" 2>/dev/null)"
        if [ -n "$body" ]; then
            got="$(echo "$body" | grep -o '"commit"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -o '[0-9a-f]\{7,\}')"
            if [ "$got" = "$want" ]; then
                log "  健康检查通过（第 $i 次，commit=$got）"
                return 0
            fi
            log "  第 $i 次：服务在线但 commit=$got 期望=$want，重试..."
        else
            log "  第 $i 次：status 无响应，重试..."
        fi
        sleep "$HEALTH_INTERVAL"
    done
    return 1
}

restart_service() { sudo systemctl restart "$SERVICE" 2>>"$LOG"; }
pyproject_hash() { sha256sum "$REPO/pyproject.toml" 2>/dev/null | cut -d' ' -f1; }
install_deps() {
    log "  安装依赖 pip install -e .[host] ..."
    "$VENV_PIP" install -e "$REPO[host]" >>"$LOG" 2>&1
}

log "==== update 开始 ===="

OLD_COMMIT="$(git rev-parse HEAD 2>/dev/null | cut -c1-12)"
[ -z "$OLD_COMMIT" ] && { log "FATAL: 读不到当前 commit，退出"; exit 1; }
log "当前 commit=$OLD_COMMIT (branch=$BRANCH)"

OLD_PYHASH="$(pyproject_hash)"

if ! git fetch origin "$BRANCH" >>"$LOG" 2>&1; then
    log "拉不到网（fetch 失败），静默跳过，现状不变。"
    log "==== update 结束（无网）===="
    exit 0
fi

REMOTE_COMMIT="$(git rev-parse "origin/$BRANCH" 2>/dev/null | cut -c1-12)"
if [ "$REMOTE_COMMIT" = "$OLD_COMMIT" ]; then
    log "已是最新（$OLD_COMMIT），无需更新。"
    log "==== update 结束（无更新）===="
    exit 0
fi

log "发现新版本：$OLD_COMMIT -> $REMOTE_COMMIT，开始更新。"

if ! git merge --ff-only "origin/$BRANCH" >>"$LOG" 2>&1; then
    log "ERROR: ff-only 合并失败（工作区可能有本地改动/分叉）。不动现状，退出。"
    log "==== update 结束（合并失败）===="
    exit 1
fi

NEW_COMMIT="$(git rev-parse HEAD | cut -c1-12)"
log "已合并到 $NEW_COMMIT"

NEW_PYHASH="$(pyproject_hash)"
DEPS_CHANGED=0
if [ "$OLD_PYHASH" != "$NEW_PYHASH" ]; then
    log "pyproject.toml 有变更，需重装依赖。"
    DEPS_CHANGED=1
    install_deps
fi

log "重启服务..."
restart_service

if health_ok "$NEW_COMMIT"; then
    log "更新成功：现运行 $NEW_COMMIT"
    log "==== update 结束（成功）===="
    exit 0
fi

log "!! 健康检查失败，回滚到 $OLD_COMMIT"
git reset --hard "$OLD_COMMIT" >>"$LOG" 2>&1
if [ "$DEPS_CHANGED" = "1" ]; then
    log "  回滚依赖..."
    install_deps
fi
log "  回滚后重启..."
restart_service

if health_ok "$OLD_COMMIT"; then
    log "回滚成功：已恢复到 $OLD_COMMIT。请查日志排查新版本为何失败。"
    log "==== update 结束（已回滚）===="
    exit 1
else
    log "!!!! 严重：回滚后健康检查仍失败。服务可能已宕，需人工介入。"
    log "==== update 结束（回滚后仍失败）===="
    exit 2
fi