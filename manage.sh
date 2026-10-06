#!/bin/zsh
# Start/stop/inspect the autopilot daemon (and the nightly cleanup agent).
#
#   ./manage.sh start     # load + launch the daemon (and cleanup agent)
#   ./manage.sh stop      # unload both agents
#   ./manage.sh restart   # stop then start
#   ./manage.sh status     # show whether they're running
#   ./manage.sh logs       # tail the daemon log

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
LA="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
# The English autopilot and the Dutch daemon publish to DIFFERENT channels, so
# they are managed separately — starting both by accident is a real cost.
#   ./manage.sh start          -> English autopilot + cleanup
#   ./manage.sh start nl       -> Dutch channel daemon
AGENTS=(com.youtube.autopilot com.youtube.cleanup)
NL_AGENTS=(com.youtube.brainrot)

if [ "${2:-}" = "nl" ]; then
    AGENTS=("${NL_AGENTS[@]}")
fi

_load() {
    local label="$1"
    local plist="$LA/$label.plist"
    [ -f "$plist" ] || { echo "  missing $plist — run ./setup.sh first"; return 1; }
    launchctl bootstrap "gui/$UID_NUM" "$plist" 2>/dev/null \
        || launchctl load -w "$plist"
    echo "  started $label"
}

_unload() {
    local label="$1"
    launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null \
        || launchctl unload "$LA/$label.plist" 2>/dev/null
    echo "  stopped $label"
}

case "${1:-status}" in
    start)
        for a in "${AGENTS[@]}"; do _load "$a"; done
        ;;
    stop)
        for a in "${AGENTS[@]}"; do _unload "$a"; done
        ;;
    restart)
        for a in "${AGENTS[@]}"; do _unload "$a"; done
        for a in "${AGENTS[@]}"; do _load "$a"; done
        ;;
    status)
        for a in "${AGENTS[@]}"; do
            if launchctl list | grep -q "$a"; then
                echo "  $a: RUNNING"
            else
                echo "  $a: stopped"
            fi
        done
        ;;
    logs)
        if [ "${2:-}" = "nl" ]; then
            tail -n 40 -f "$REPO_DIR/output/logs/brainrot.log"
        else
            tail -n 40 -f "$REPO_DIR/output/logs/autopilot.log"
        fi
        ;;
    *)
        echo "usage: ./manage.sh {start|stop|restart|status|logs} [nl]"
        exit 1
        ;;
esac
