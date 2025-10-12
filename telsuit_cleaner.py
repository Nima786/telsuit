from telethon import TelegramClient, events
from telsuit_core import (
    get_config, save_config, logger,
    print_section, print_warning, print_success
)


# --- 🧹 Telegram Cleaner Main Logic ---
async def start_cleaner(auto=False):
    """Main cleaner module for TelSuit."""
    config = get_config()

    if not config["admins"]:
        print_warning("No admins configured.")
        return

    if not config["channels"]:
        print_warning("No channels configured.")
        return

    admins = list(config["admins"].keys())
    if auto:
        selected_admin = admins[0]
        print(f"🤖 Auto-selected admin: {selected_admin}")
    else:
        print_section("Available Admins")
        for i, phone in enumerate(admins, start=1):
            print(f"{i}. {phone}")
        sel = input("Select which admin to use: ").strip()
        if not sel.isdigit() or int(sel) < 1 or int(sel) > len(admins):
            print("Invalid selection.")
            return
        selected_admin = admins[int(sel) - 1]

    creds = config["admins"][selected_admin]
    api_id, api_hash, phone = creds["api_id"], creds["api_hash"], selected_admin
    client = TelegramClient(f"cleaner_{phone}.session", int(api_id), api_hash)

    # --- 🧠 Cleaning Logic ---
    async def handle_new_post(event):
        """Triggered when a new post is published in the channel."""
        message = event.message
        text = message.text or ""

        # Skip empty posts
        if not text.strip():
            return

        # --- Duplicate detection (by keyword/SKU) ---
        duplicate_detected = False
        for keyword in config["cleaner"].get("keywords", []):
            if keyword in text:
                duplicate_detected = True
                break

        if duplicate_detected:
            logger.info(f"🧹 Duplicate detected, deleting message {message.id}")
            try:
                await client.delete_messages(event.chat_id, message.id)
                print_success(f"Deleted duplicate message {message.id}")
            except Exception as e:
                logger.error(f"Failed to delete message {message.id}: {e}")
            return

        # --- Auto forwarding ---
        for target_channel in config["cleaner"].get("forward_channels", []):
            try:
                await client.forward_messages(target_channel, message)
                logger.info(
                    f"📤 Forwarded message {message.id} "
                    f"to {target_channel}"
                )
            except Exception as e:
                logger.error(f"Failed to forward to {target_channel}: {e}")

    # --- Event Registration ---
    for ch in config["channels"]:
        client.add_event_handler(handle_new_post, events.NewMessage(chats=ch))
        logger.info(f"Cleaner monitoring new posts in: {ch}")

    await client.start(phone=phone)
    logger.info(f"Cleaner client started under admin {phone}")
    await client.run_until_disconnected()


# --- ⚙️ Interactive Menu ---
def configure_cleaner():
    """Interactive configuration for cleaner settings."""
    config = get_config()
    cleaner_cfg = config.get(
        "cleaner",
        {"keywords": [], "forward_channels": [], "delete_rules": {}}
    )

    while True:
        print_section("Cleaner Configuration")
        print("1️⃣  Manage Keywords")
        print("2️⃣  Manage Forward Channels")
        print("3️⃣  Manage Delete Rules")
        print("4️⃣  Back to Main Menu")

        choice = input("Select option: ").strip()

        if choice == '1':
            print_section("Current Keywords")
            if not cleaner_cfg["keywords"]:
                print_warning("No keywords defined.")
            else:
                for i, kw in enumerate(cleaner_cfg["keywords"], start=1):
                    print(f"{i}. {kw}")
            new_kw = input(
                "Enter new keyword (or leave empty to go back): "
            ).strip()
            if new_kw:
                cleaner_cfg["keywords"].append(new_kw)
                print_success(f"Added keyword '{new_kw}'")

        elif choice == '2':
            print_section("Forward Channels")
            if not cleaner_cfg["forward_channels"]:
                print_warning("No forward channels defined.")
            else:
                for i, ch in enumerate(
                    cleaner_cfg["forward_channels"], start=1
                ):
                    print(f"{i}. {ch}")
            new_ch = input(
                "Enter new forward channel (e.g. @channelname): "
            ).strip()
            if new_ch:
                cleaner_cfg["forward_channels"].append(new_ch)
                print_success(f"Added forward channel {new_ch}")

        elif choice == '3':
            print_section("Delete Rules")
            print(
                "Example: delete posts older than 7 days "
                "or containing 'out of stock'"
            )
            rule_name = input("Enter rule name: ").strip()
            rule_value = input("Enter rule details: ").strip()
            if rule_name and rule_value:
                cleaner_cfg["delete_rules"][rule_name] = rule_value
                print_success(f"Added delete rule '{rule_name}'")

        elif choice == '4':
            break
        else:
            print("Invalid selection.")

    config["cleaner"] = cleaner_cfg
    save_config(config)
    print_success("Cleaner configuration updated.")


# --- ▶️ CLI Entrypoint ---
async def run_cleaner(auto=False):
    """Wrapper for async run (used by main.py)."""
    await start_cleaner(auto=auto)
