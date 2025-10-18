#!/usr/bin/env bash
#
# TelSuit Installer
# https://github.com/Nima786/telsuit
#
# One-click setup for Python + Telethon environment
# Creates systemd service automatically
# Auto-launches safely if interactive

set -e  # stop on error

REPO_URL="https://github.com/Nima786/telsuit.git"
INSTALL_DIR="$HOME/telsuit"
VENV_DIR="$INSTALL_DIR/venv"
SERVICE_FILE="/etc/systemd/system/telsuit.service"
BASHRC_FILE="$HOME/.bashrc"
ZSHRC_FILE="$HOME/.zshrc"

echo ""
echo "🧠 Installing TelSuit..."
echo "===================================="
sleep 1

# --- 1️⃣ Check dependencies ---
echo "🔍 Checking system requirements..."

if ! command -v python3 >/dev/null 2>&1; then
    echo "📦 Installing Python3..."
    sudo apt update && sudo apt install -y python3 python3-pip
fi

echo "🔧 Ensuring Python venv support..."
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
    echo "📦 Installing python3-full (includes venv + ensurepip)..."
    sudo apt update
    sudo apt install -y python3-full || sudo apt install -y python3-venv
fi

if ! command -v git >/dev/null 2>&1; then
    echo "📦 Installing Git..."
    sudo apt install -y git
fi

# --- 2️⃣ Clone or update repo ---
if [ ! -d "$INSTALL_DIR" ]; then
    echo "⬇️ Cloning TelSuit into $INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR"
else
    echo "📁 Repo already exists — updating..."
    cd "$INSTALL_DIR"
    git pull
fi

cd "$INSTALL_DIR"

# --- 3️⃣ Create or repair venv ---
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "⚙️ Creating new virtual environment..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR" || {
        echo "❌ venv creation failed — installing python3-full..."
        sudo apt install -y python3-full
        python3 -m venv "$VENV_DIR"
    }
else
    echo "✅ Virtual environment found."
fi

# --- 4️⃣ Install dependencies ---
echo "📦 Installing Python dependencies..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    pip install telethon
fi
deactivate

# --- 5️⃣ Auto-generate launcher ---
echo "⚙️ Generating TelSuit launcher..."
cat > "$INSTALL_DIR/telsuit.sh" <<'EOF'
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
    echo "🧠 Launching TelSuit core..."
    source "$VENV_DIR/bin/activate"
    python3 "$INSTALL_DIR/main.py"
    deactivate
    ;;
  update)
    echo "⬆️ Updating TelSuit..."
    git pull
    ;;
  stop)
    echo "🛑 Stopping TelSuit service..."
    sudo systemctl stop "$SERVICE_NAME"
    echo "✅ Service stopped."
    ;;
  restart)
    echo "🔁 Restarting TelSuit service..."
    sudo systemctl restart "$SERVICE_NAME"
    echo "✅ TelSuit restarted."
    ;;
  uninstall)
    echo "⚠️ Uninstalling TelSuit..."
    read -rp "Are you sure you want to remove TelSuit completely? (y/N): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        sudo systemctl stop "$SERVICE_NAME" || true
        sudo systemctl disable "$SERVICE_NAME" || true
        sudo rm -f "/etc/systemd/system/$SERVICE_NAME"
        sudo systemctl daemon-reload
        rm -rf "$INSTALL_DIR"
        sudo rm -f /usr/local/bin/telsuit
        echo "✅ TelSuit uninstalled successfully."
    else
        echo "Uninstall cancelled."
    fi
    ;;
  status)
    echo "📊 Checking TelSuit service status..."
    sudo systemctl status "$SERVICE_NAME" --no-pager -l
    ;;
  *)
    echo "📘 Usage:"
    echo "  telsuit start      → Start TelSuit manually"
    echo "  telsuit stop       → Stop TelSuit service"
    echo "  telsuit restart    → Restart TelSuit service"
    echo "  telsuit update     → Update from GitHub"
    echo "  telsuit uninstall  → Remove TelSuit completely"
    echo "  telsuit status     → Check service status"
    ;;
esac
EOF

chmod +x "$INSTALL_DIR/telsuit.sh"

# --- 6️⃣ Create alias ---
create_alias() {
    local shell_rc="$1"
    if ! grep -q "telsuit=" "$shell_rc" 2>/dev/null; then
        echo "📎 Adding alias to $shell_rc"
        {
            echo ""
            echo "# TelSuit launcher"
            echo "alias telsuit='$INSTALL_DIR/telsuit.sh'"
        } >> "$shell_rc"
    fi
    alias telsuit="$INSTALL_DIR/telsuit.sh"
}

if [[ "$SHELL" == *"bash"* ]]; then
    create_alias "$BASHRC_FILE"
elif [[ "$SHELL" == *"zsh"* ]]; then
    create_alias "$ZSHRC_FILE"
else
    create_alias "$BASHRC_FILE"
fi

# Make command globally available
if [ ! -f "/usr/local/bin/telsuit" ]; then
    echo "⚙️ Linking telsuit command globally..."
    sudo ln -sf "$INSTALL_DIR/telsuit.sh" /usr/local/bin/telsuit
    sudo chmod +x /usr/local/bin/telsuit
fi

# --- 7️⃣ Create systemd service ---
echo "⚙️ Creating systemd service..."
sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=TelSuit Background Service (Enhancer + Cleaner)
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/python3 $INSTALL_DIR/main.py --headless
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable telsuit.service
sudo systemctl restart telsuit.service

# --- 8️⃣ Done ---
echo ""
echo "✅ Installation completed successfully!"
echo ""
echo "📘 You can now use:"
echo "  telsuit start      → Run interactively"
echo "  telsuit restart    → Restart background service"
echo "  telsuit status     → View service logs"
echo "  telsuit uninstall  → Remove completely"
echo ""
echo "🎉 Enjoy your Telegram automation suite!"
echo ""
