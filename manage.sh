#!/usr/bin/env bash
# manage.sh — start / stop / restart the Streamlit app
#
# Usage:
#   ./manage.sh start    [port]   # default port 8501
#   ./manage.sh stop
#   ./manage.sh restart  [port]
#   ./manage.sh status
#   ./manage.sh logs     [lines]  # tail the log file (default 50 lines)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/streamlit_app"
PID_FILE="$SCRIPT_DIR/.streamlit_app.pid"
LOG_FILE="$APP_DIR/logs/app.log"
NOHUP_LOG="$SCRIPT_DIR/logs/nohup.out"
PORT="${2:-8501}"

mkdir -p "$SCRIPT_DIR/logs"

_is_running() {
    [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

cmd_start() {
    if _is_running; then
        echo "Already running (PID $(cat "$PID_FILE")). Use restart to bounce."
        exit 1
    fi
    echo "Starting Streamlit on port $PORT …"
    cd "$APP_DIR"
    nohup streamlit run app.py \
        --server.port "$PORT" \
        --server.headless true \
        --server.fileWatcherType none \
        >> "$NOHUP_LOG" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Started  PID=$(cat "$PID_FILE")  port=$PORT"
    echo "Logs:  tail -f $NOHUP_LOG"
}

cmd_stop() {
    if ! _is_running; then
        echo "Not running."
        [[ -f "$PID_FILE" ]] && rm "$PID_FILE"
        exit 0
    fi
    PID=$(cat "$PID_FILE")
    echo "Stopping PID $PID …"
    kill "$PID"
    # Wait up to 10 s for graceful exit
    for i in $(seq 1 10); do
        kill -0 "$PID" 2>/dev/null || break
        sleep 1
    done
    if kill -0 "$PID" 2>/dev/null; then
        echo "Process did not exit cleanly; sending SIGKILL."
        kill -9 "$PID"
    fi
    rm -f "$PID_FILE"
    echo "Stopped."
}

cmd_restart() {
    cmd_stop || true
    sleep 1
    cmd_start
}

cmd_status() {
    if _is_running; then
        echo "Running  PID=$(cat "$PID_FILE")  port=$PORT"
    else
        echo "Not running."
    fi
}

cmd_logs() {
    LINES="${2:-50}"
    if [[ -f "$LOG_FILE" ]]; then
        echo "=== app log (last $LINES lines) ==="
        tail -n "$LINES" "$LOG_FILE"
    else
        echo "No app log found at $LOG_FILE"
    fi
    if [[ -f "$NOHUP_LOG" ]]; then
        echo ""
        echo "=== nohup log (last $LINES lines) ==="
        tail -n "$LINES" "$NOHUP_LOG"
    fi
}

case "${1:-}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    logs)    cmd_logs "$@" ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs} [port|lines]"
        exit 1
        ;;
esac
