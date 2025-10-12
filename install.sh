#!/usr/bin/env bash
#
# TelSuit Installer
# https://github.com/Nima786/telsuit
#
# One-click setup for Python + Telethon environment
# Auto-launches safely if interactive

set -e  # stop on error

REPO_URL="https://github.com/Nima786/telsuit.git"
INSTALL_DIR="$HOME/telsuit"
VENV_DIR="$INSTALL_DIR/venv"
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
# shellcheck disable=SC1091
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
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    python3 "$INSTALL_DIR/main.py"
    deactivate
    ;;
  update)
    echo "⬆️ Updating TelSuit..."
    git pull
    ;;
  stop)
    echo "🛑 TelSuit stopped (if running)."
    ;;
  *)
    echo "📘 Usage:"
    echo "  telsuit start   → Start TelSuit main service"
    echo "  telsuit update  → Update from GitHub"
    echo "  telsuit stop    → Stop (if running)"
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

# --- 7️⃣ Done (safe auto-launch if interactive) ---
echo ""
echo "✅ Installation completed successfully!"
echo ""

if [ -t 0 ]; then
    echo "🎉 Launching TelSuit now..."
    echo ""
    bash "$INSTALL_DIR/telsuit.sh" start
else
    echo "💡 Non-interactive shell detected."
    echo "To start TelSuit, run:"
    echo "  telsuit start"
    echo ""
fi

echo "🎉 Enjoy your Telegram automation suite!"
echo ""
