#!/usr/bin/env bash
# TelSuit Launcher

INSTALL_DIR="$HOME/telsuit"
VENV_DIR="$INSTALL_DIR/venv"
SERVICE_NAME="telsuit.service"

echo "🚀 Starting TelSuit..."
echo "================================"

if [ ! -d "$INSTALL_DIR" ]; then
    echo "❌ TelSuit not installed at $INSTALL_DIR"
    exit 1
fi

cd "$INSTALL_DIR" || exit 1

case "$1" in
  start|"")
    echo "🧠 Launching TelSuit interactive mode..."
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    python3 "$INSTALL_DIR/main.py"
    deactivate
    ;;
  update)
    echo "⬆️ Updating TelSuit from GitHub..."
    git pull
    ;;
  stop)
    echo "🛑 Stopping TelSuit background service..."
    sudo systemctl stop "$SERVICE_NAME"
    echo "✅ Service stopped."
    ;;
  status)
    echo "📊 Checking TelSuit service status..."
    sudo systemctl status "$SERVICE_NAME" --no-pager -l
    ;;
  reload)
    echo "🔁 Reloading TelSuit configuration and restarting service..."
    sudo systemctl stop "$SERVICE_NAME"
    git pull
    sudo systemctl daemon-reload
    sudo systemctl start "$SERVICE_NAME"
    echo "✅ TelSuit reloaded successfully."
    ;;
  *)
    echo "📘 Usage:"
    echo "  telsuit start    → Start TelSuit interactively"
    echo "  telsuit update   → Update from GitHub"
    echo "  telsuit stop     → Stop TelSuit background service"
    echo "  telsuit status   → Check service status"
    echo "  telsuit reload   → Reload config & restart service"
    ;;
esac
