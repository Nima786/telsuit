<h1>🧩 TelSuit</h1>
<p><strong>A complete Telegram automation suite for channel management</strong><br>
Enhance messages with Premium emojis, auto-clean your posts, and manage channels effortlessly — all from one place.</p>

<hr>

<h2>🚀 Quick Install (One Command)</h2>

<pre>
curl -sSL https://raw.githubusercontent.com/Nima786/telsuit/main/install.sh | bash
</pre>

<p>After installation, run:</p>

<pre>
telsuit start
</pre>

<p>This launches the <strong>TelSuit dashboard</strong> — a unified interface for both the <em>Emoji Enhancer</em> and <em>Cleaner</em> modules.</p>

<hr>

<h2>✨ Key Features</h2>
<ul>
  <li><strong>🎨 Emoji Enhancer:</strong> Automatically upgrades regular emojis to Telegram <em>Premium Custom Emojis</em>. Fully Markdown-safe and works across multiple channels.</li>
  <li><strong>🧹 Smart Cleaner:</strong> Detects and removes duplicate posts (using product codes or SKUs), deletes old or keyword-based posts, and can forward or copy messages between channels.</li>
  <li><strong>🕹️ Interactive Menu:</strong> Add admins, channels, emoji mappings, and cleaner keywords — all via an intuitive console interface.</li>
  <li><strong>🧑‍💼 Multi-Admin Support:</strong> Manage multiple Telegram admin accounts from one shared configuration.</li>
  <li><strong>📢 Multi-Channel Management:</strong> Handle multiple Telegram channels simultaneously.</li>
  <li><strong>🧠 Shared Config System:</strong> All settings (admins, emoji map, cleaner keywords, etc.) are stored in one JSON file (<code>telsuit-config.json</code>).</li>
  <li><strong>⏳ Queue System:</strong> Automatically queues messages for processing, ensuring emojis and cleaners never overlap — perfect for bulk or simultaneous posts.</li>
  <li><strong>⚙️ Auto Systemd Setup:</strong> The installer automatically creates and enables a systemd service for continuous background operation.</li>
  <li><strong>🧽 Uninstall Command:</strong> Easily remove all TelSuit files, venv, config, and services using <code>telsuit uninstall</code>.</li>
  <li><strong>🔁 Restart & Reload:</strong> Apply configuration changes instantly via <code>telsuit restart</code> or <code>telsuit reload</code>.</li>
  <li><strong>⚡ Fully Async:</strong> Powered by <a href="https://github.com/LonamiWebs/Telethon">Telethon</a> for high performance and reliability.</li>
</ul>

<hr>

<h2>🧠 Module Overview</h2>

<h3>🎨 Emoji Enhancer</h3>
<p>
Automatically converts emojis in new channel posts to Premium Telegram custom emojis.
If a post fails to edit (e.g. already contains Premium emojis), TelSuit still triggers the cleaner afterward to maintain consistency.
</p>

<h3>🧹 Channel Cleaner</h3>
<p>
Automatically detects and removes duplicate messages using defined <strong>keywords</strong> (like <code>شناسه محصول</code> or <code>کد کالا</code>).
It can also:
</p>
<ul>
  <li>🗑️ Delete posts by keyword</li>
  <li>🕰️ Delete posts older than N days</li>
  <li>📤 Forward or copy posts between channels</li>
  <li>🔑 Manage cleaner keywords interactively</li>
</ul>
<p>Cleaner is triggered automatically after new posts or can be used manually via the menu.</p>

<hr>

<h2>⚙️ Commands</h2>
<pre>
telsuit start      # Launch the interactive dashboard
telsuit update     # Update from GitHub
telsuit stop       # Stop the background service
telsuit restart    # Restart TelSuit and reload configuration
telsuit uninstall  # Fully remove TelSuit, its files, and services
</pre>

<p>Once running, the interactive menu allows you to:</p>
<ul>
  <li>🧑‍💻 Add or delete admins</li>
  <li>📢 Add or delete channels</li>
  <li>😀 Manage emoji-to-ID mappings</li>
  <li>🧹 Configure and manage cleaner keywords</li>
  <li>▶️ Trigger real-time monitoring manually (if desired)</li>
</ul>

<hr>

<h2>🖥️ Background Service (Auto Setup)</h2>
<p>
TelSuit installs with a systemd service automatically.
It keeps running 24/7 in the background, restarting if it crashes or the server reboots.
</p>

<pre>
sudo systemctl status telsuit --no-pager -l
sudo systemctl restart telsuit
sudo systemctl enable telsuit
</pre>

<p>The default service file is:</p>
<pre>
[Unit]
Description=TelSuit Background Service (Enhancer + Cleaner)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/telsuit
ExecStart=/root/telsuit/venv/bin/python3 /root/telsuit/telsuit_enhancer.py --headless
Restart=always
RestartSec=10
Environment="PYTHONUNBUFFERED=1"
StandardOutput=append:/root/telsuit/telsuit.log
StandardError=append:/root/telsuit/telsuit.log

[Install]
WantedBy=multi-user.target
</pre>

<hr>

<h2>🧩 Configuration File (Example)</h2>
<pre>
{
  "admins": {
    "+989332343968": {
      "api_id": "88848988",
      "api_hash": "54df2471hg6d10du20b06d34c079561d"
    }
  },
  "channels": [
    "@mychannel1",
    "@mychannel2"
  ],
  "emoji_map": {
    "🛒": "5431499171045581032",
    "📦": "6023639019290630537",
    "📣": "5229064374403998351"
  },
  "cleaner": {
    "keywords": ["شناسه محصول", "کد کالا", "شناسه کالا"],
    "forward_channels": [],
    "delete_rules": {}
  },
  "queue_delay": 3
}
</pre>

<hr>

<h2>📁 Project Structure</h2>
<pre>
telsuit/
├── telsuit_core.py        # Shared logic and config handling
├── telsuit_enhancer.py    # Emoji enhancer module
├── telsuit_cleaner.py     # Channel cleaner module
├── main.py                # Unified menu and entry point
├── install.sh             # One-click installer with systemd setup
├── telsuit.sh             # CLI launcher wrapper
├── requirements.txt       # Python dependencies
├── telsuit.log            # Rotating log file (auto-managed)
└── telsuit-config.json    # Auto-created configuration file
</pre>

<hr>

<h2>🧰 Requirements</h2>
<ul>
  <li>Python 3.9+</li>
  <li>Telethon</li>
  <li>colorama</li>
  <li>python-dotenv</li>
</ul>

<hr>

<h2>📜 License</h2>
<p>
MIT License © 2025 <strong>Nima Norouzi</strong><br>
You are free to use, modify, and distribute this software, provided that proper credit is given.
</p>

<hr>

<h2>💬 Support</h2>
<p>
For questions, feedback, or feature requests, please open an issue on the
<a href="https://github.com/Nima786/telsuit/issues">GitHub Issues page</a>.
</p>

<p align="center">Made with ❤️ using <strong>Telethon</strong> and <strong>Python</strong></p>
