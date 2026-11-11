#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
channel="${2:-en}"
case "$channel" in en|nl) ;; *) echo 'Channel must be en or nl' >&2; exit 2 ;; esac
unit="youtube-autopilot@$channel.service"
case "${1:-status}" in
    start|stop|restart) sudo systemctl "$1" "$unit" ;;
    status) systemctl status "$unit" --no-pager ;;
    logs) sudo journalctl -u "$unit" -n 50 -f ;;
    check) exec "$REPO_DIR/.venv/bin/python" "$REPO_DIR/linux/preflight.py" --channel "$channel" ;;
    *) echo 'usage: ./manage.sh {start|stop|restart|status|logs|check} [en|nl]' >&2; exit 2 ;;
esac
