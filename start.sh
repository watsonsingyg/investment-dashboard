#!/bin/bash
# 投资 Pipeline 管理系统 — 统一启动入口
# 用法：
#   bash start.sh                    # 前台启动，日志同步写入 logs/server.log
#   bash start.sh --background --open # 后台启动并打开浏览器
#   bash start.sh --status           # 查看当前 8766 上的服务状态
#   bash start.sh --restart          # 停止并重启已确认的服务

set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8766}"
export PORT
HOST="127.0.0.1"
BASE_URL="http://${HOST}:${PORT}"
PID_FILE=".server.pid"
LOG_DIR="logs"
LOG_FILE="${LOG_DIR}/server.log"
BACKGROUND=0
OPEN_BROWSER=0
RESTART=0
STATUS_ONLY=0

mkdir -p "$LOG_DIR"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --background) BACKGROUND=1 ;;
    --open) OPEN_BROWSER=1 ;;
    --restart) RESTART=1 ;;
    --status) STATUS_ONLY=1 ;;
    *)
      echo "未知参数：$1"
      exit 2
      ;;
  esac
  shift
done

port_pids() {
  lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true
}

health_json() {
  curl -fsS --max-time 2 "${BASE_URL}/api/health" 2>/dev/null || true
}

service_started_epoch() {
  health_json | python3 -c 'import datetime,json,sys
try:
    raw=sys.stdin.read().strip()
    if not raw:
        raise ValueError()
    value=json.loads(raw).get("started_at","")
    dt=datetime.datetime.strptime(value,"%Y-%m-%d %H:%M:%S")
    print(int(dt.timestamp()))
except Exception:
    print("")'
}

newest_code_epoch() {
  python3 - <<'PY'
from pathlib import Path
roots = [
    Path('start.sh'),
    Path('generate_dashboard.py'),
    Path('reporter'),
]
suffixes = {'.py', '.html', '.js', '.css'}
latest = 0
for root in roots:
    if root.is_file():
        latest = max(latest, int(root.stat().st_mtime))
    elif root.is_dir():
        for path in root.rglob('*'):
            if path.is_file() and path.suffix in suffixes and '__pycache__' not in path.parts:
                latest = max(latest, int(path.stat().st_mtime))
print(latest)
PY
}

service_is_stale() {
  local started newest
  started="$(service_started_epoch)"
  newest="$(newest_code_epoch)"
  [ -n "$started" ] && [ -n "$newest" ] && [ "$newest" -gt "$started" ]
}

has_health_service() {
  local health
  health="$(health_json)"
  echo "$health" | grep -q '"app"[[:space:]]*:[[:space:]]*"zhangtou-workbench"'
}

has_workbench_login() {
  curl -fsS --max-time 2 "${BASE_URL}/login" 2>/dev/null | grep -q '战投工作台'
}

is_workbench_service() {
  has_health_service || has_workbench_login
}

open_workbench() {
  if [ "$OPEN_BROWSER" -eq 1 ]; then
    open -a "Google Chrome" "$BASE_URL" >/dev/null 2>&1 || open "$BASE_URL" >/dev/null 2>&1 || true
  fi
}

wait_ready() {
  for _ in $(seq 1 60); do
    if is_workbench_service; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

clear_stale_pid_file() {
  if [ ! -f "$PID_FILE" ]; then
    return
  fi
  local old_pid
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -z "$old_pid" ] || ! kill -0 "$old_pid" 2>/dev/null; then
    rm -f "$PID_FILE"
  fi
}

stop_tracked_workbench() {
  local pids="$1"
  if [ -z "$pids" ]; then
    return 0
  fi
  echo "正在停止已有工作台服务：$pids"
  for pid in $pids; do
    kill -TERM "$pid" 2>/dev/null || true
  done
  for _ in $(seq 1 20); do
    if [ -z "$(port_pids)" ]; then
      rm -f "$PID_FILE"
      return 0
    fi
    sleep 0.5
  done

  if is_workbench_service; then
    local still_running
    still_running="$(port_pids)"
    echo "温和停止超时，确认端口上仍是战投工作台，将强制结束：${still_running}"
    for pid in $still_running; do
      kill -KILL "$pid" 2>/dev/null || true
    done
    for _ in $(seq 1 20); do
      if [ -z "$(port_pids)" ]; then
        rm -f "$PID_FILE"
        return 0
      fi
      sleep 0.25
    done
  fi

  echo "已有工作台服务未能退出，可能是当前终端没有结束该进程的权限。"
  echo "请在 Terminal 里手动执行："
  echo "  kill $(port_pids)"
  echo "  cd ${PWD} && bash start.sh --background --open"
  exit 1
}

clear_stale_pid_file
CURRENT_PIDS="$(port_pids)"

if [ "$STATUS_ONLY" -eq 1 ]; then
  if [ -n "$CURRENT_PIDS" ] && has_health_service; then
    echo "工作台正在运行：${BASE_URL}"
    echo "PID：${CURRENT_PIDS}"
    health_json
    echo
    if service_is_stale; then
      echo "提示：本地代码晚于当前服务启动时间，建议运行 bash start.sh --restart --background --open 以加载新版。"
    fi
    exit 0
  fi
  if [ -n "$CURRENT_PIDS" ] && has_workbench_login; then
    echo "旧版工作台正在运行：${BASE_URL}"
    echo "PID：${CURRENT_PIDS}"
    echo "提示：下次通过桌面 app 或 bash start.sh --background --open 启动时会温和重启到新版。"
    exit 0
  fi
  if [ -n "$CURRENT_PIDS" ]; then
    echo "端口 ${PORT} 已被非工作台服务占用。"
    echo "占用 PID：${CURRENT_PIDS}"
    exit 1
  fi
  echo "工作台未运行。"
  exit 0
fi

if [ -n "$CURRENT_PIDS" ]; then
  if has_health_service; then
    if [ "$RESTART" -eq 1 ]; then
      stop_tracked_workbench "$CURRENT_PIDS"
    elif service_is_stale; then
      echo "检测到本地代码已更新，正在重启工作台以加载新版页面。"
      stop_tracked_workbench "$CURRENT_PIDS"
    else
      echo "工作台已在运行：${BASE_URL}"
      echo "$CURRENT_PIDS" | head -n 1 > "$PID_FILE"
      open_workbench
      exit 0
    fi
  elif has_workbench_login; then
    echo "检测到旧版工作台服务，正在温和重启以加载新版启动逻辑。"
    stop_tracked_workbench "$CURRENT_PIDS"
  else
    echo "端口 ${PORT} 已被其他服务占用，未做任何结束进程操作。"
    echo "占用 PID：${CURRENT_PIDS}"
    echo "查看命令：lsof -nP -iTCP:${PORT} -sTCP:LISTEN"
    exit 1
  fi
fi

echo "启动投资 Pipeline 管理系统：${BASE_URL}"
echo "日志文件：${PWD}/${LOG_FILE}"
echo "---- $(date '+%Y-%m-%d %H:%M:%S') start ----" >> "$LOG_FILE"

python3 -u server.py >> "$LOG_FILE" 2>&1 &
APP_PID=$!
echo "$APP_PID" > "$PID_FILE"

if ! wait_ready; then
  echo "工作台启动超时，请查看日志：${PWD}/${LOG_FILE}"
  exit 1
fi

echo "工作台已就绪：${BASE_URL}"
open_workbench

if [ "$BACKGROUND" -eq 1 ]; then
  exit 0
fi

echo "按 Ctrl+C 可结束本次前台守护。"
tail -n 40 -f "$LOG_FILE" &
TAIL_PID=$!
trap 'kill "$APP_PID" "$TAIL_PID" 2>/dev/null || true; rm -f "$PID_FILE"' INT TERM EXIT
wait "$APP_PID"
