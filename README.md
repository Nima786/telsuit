🧩 TelSuit
==========

**A unified Telegram automation suite for channel management**  
_Enhance messages with custom emojis and automatically clean up your channels — all in one tool._

* * *

### 🚀 Quick Install (One Command)

    curl -sSL https://raw.githubusercontent.com/Nima786/telsuit/main/install.sh | bash

After installation, simply run:

    telsuit start

This launches the main interactive TelSuit dashboard. You can manage both **Emoji Enhancer** and **Cleaner** modules from one place.

* * *

✨ Features
----------

*   **Emoji Enhancer:** Automatically converts normal emojis into Premium Telegram custom emojis (supports Markdown-safe text).
*   **Message Cleaner:** Detects and removes duplicate posts, deletes old or keyword-based messages, and forwards content to other channels.
*   **Multi-Admin Support:** Add multiple Telegram admin accounts and select which one to use.
*   **Multi-Channel Monitoring:** Handle multiple Telegram channels at once.
*   **Shared Configuration:** Unified config file (`telsuit-config.json`) stores admins, channels, emoji mappings, and cleaner rules.
*   **Systemd Integration:** Optional background service for 24/7 operation — starts automatically after reboot.
*   **Fully Async:** Built on `Telethon` for speed and reliability.

* * *

🧠 Modules Overview
-------------------

### 🎨 Emoji Enhancer

This module enhances posts in your Telegram channel by replacing standard emojis with Premium custom emojis. It supports Markdown-safe formatting, multiple channels, and automatic handling of edited messages.

### 🧹 Cleaner

The cleaner keeps your channels tidy by detecting duplicate posts based on keywords (such as SKUs or product codes), deleting unwanted messages, or forwarding them to specified channels. It also supports custom deletion rules.

* * *

⚙️ Usage
--------

    
    telsuit start      # Launch the interactive main menu
    telsuit update     # Update from GitHub
    telsuit stop       # Stop the background service
    telsuit status     # Check current status
    telsuit reload     # Reload configuration and restart service
    

The interactive menu allows you to:

*   🧑‍💻 Configure admins
*   📢 Add or remove channels
*   😀 Manage emoji-to-ID mappings
*   🧹 Configure cleaner rules and keywords
*   ▶️ Start monitoring in real-time

* * *

🖥️ Background Service (Optional)
---------------------------------

If you want TelSuit to run continuously in the background, you can set up a systemd service:

    
    sudo nano /etc/systemd/system/telsuit.service
    

Paste the following:

    
    [Unit]
    Description=TelSuit Background Service
    After=network.target
    
    [Service]
    WorkingDirectory=/root/telsuit
    ExecStart=/root/telsuit/venv/bin/python3 /root/telsuit/main.py --headless
    Restart=always
    
    [Install]
    WantedBy=multi-user.target
    

Then enable it:

    
    sudo systemctl daemon-reload
    sudo systemctl enable telsuit
    sudo systemctl start telsuit
    

You can monitor it with:

    
    sudo systemctl status telsuit --no-pager -l
    

* * *

📁 Repository Structure
-----------------------

    
    telsuit/
    ├── telsuit_core.py        # Shared logic and configuration
    ├── telsuit_enhancer.py    # Emoji enhancer module
    ├── telsuit_cleaner.py     # Channel cleaner module
    ├── main.py                # Unified entry point
    ├── install.sh             # One-click installer
    ├── requirements.txt       # Dependencies
    ├── telsuit.sh             # CLI launcher
    ├── .gitignore             # Git exclusions
    └── telsuit-config.json    # Auto-created configuration file
    

* * *

🧰 Requirements
---------------

*   Python 3.9+
*   Telethon
*   colorama
*   python-dotenv

* * *

📜 License
----------

MIT License © 2025 **Nima Norouzi**  
You are free to use, modify, and distribute this software, provided that proper credit is given.

* * *

💬 Support
----------

For feedback or feature requests, please open an issue on the [GitHub Issues page](https://github.com/Nima786/telsuit/issues).

* * *

Made with ❤️ using **Telethon** and **Python**
