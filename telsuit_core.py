import json
import logging
import os


# --- 🎨 Colors ---
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


# --- ⚙️ Config Setup ---
CONFIG_FILE = 'telsuit-config.json'


def get_config():
    """Load configuration from disk."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                cfg = json.load(f)
            except json.JSONDecodeError:
                cfg = {}
    else:
        cfg = {}

    # Default schema (auto-fill missing keys)
    cfg.setdefault("admins", {})
    cfg.setdefault("channels", [])
    cfg.setdefault("emoji_map", {})
    cfg.setdefault("cleaner", {
        "keywords": [],
        "forward_channels": [],
        "delete_rules": {}
    })
    return cfg


def save_config(config):
    """Save configuration to disk."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    logger.info(f"Configuration saved to {CONFIG_FILE}")


# --- 🧠 Logging Setup ---
LOG_FILE = os.path.join(os.getcwd(), "telsuit.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("TelSuit")


# --- 🧩 Helper Utilities ---
def print_section(title):
    """Prints a colored section header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}--- {title} ---{Colors.RESET}")


def print_success(message):
    """Prints a success message."""
    print(f"{Colors.GREEN}✔ {message}{Colors.RESET}")


def print_warning(message):
    """Prints a warning message."""
    print(f"{Colors.YELLOW}⚠ {message}{Colors.RESET}")


def print_error(message):
    """Prints an error message."""
    print(f"{Colors.RED}✖ {message}{Colors.RESET}")
