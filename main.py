import asyncio
import sys
from telsuit_core import Colors, get_config as load_config, save_config
from telsuit_enhancer import run_enhancer
from telsuit_cleaner import run_cleaner


async def run_config_editor(config):
    """Advanced shared configuration editor."""
    while True:
        print(f"\n{Colors.CYAN}--- Shared Configuration Menu ---{Colors.RESET}")
        print(f"{Colors.YELLOW}1.{Colors.RESET} Add / Delete Admins")
        print(f"{Colors.YELLOW}2.{Colors.RESET} Add / Delete Channels")
        print(f"{Colors.YELLOW}3.{Colors.RESET} Reset Configuration")
        print(f"{Colors.YELLOW}4.{Colors.RESET} View Current Configuration")
        print(f"{Colors.YELLOW}5.{Colors.RESET} Return to Main Menu")
        choice = input("> ").strip()

        # --- Admin management ---
        if choice == "1":
            while True:
                print(f"\n{Colors.CYAN}--- Manage Admin Accounts ---{Colors.RESET}")
                print(f"{Colors.YELLOW}1.{Colors.RESET} Add Admin")
                print(f"{Colors.YELLOW}2.{Colors.RESET} Delete Admin")
                print(f"{Colors.YELLOW}3.{Colors.RESET} Return")
                sub_choice = input("> ").strip()

                if sub_choice == "1":
                    phone = input("Enter admin phone number (e.g. +1234567890): ").strip()
                    api_id = input("Enter API ID: ").strip()
                    api_hash = input("Enter API Hash: ").strip()
                    config.setdefault("admins", {})
                    config["admins"][phone] = {"api_id": api_id, "api_hash": api_hash}
                    save_config(config)
                    print(f"{Colors.GREEN}✅ Admin {phone} added/updated.{Colors.RESET}")

                elif sub_choice == "2":
                    admins = config.get("admins", {})
                    if not admins:
                        print("No admins configured.")
                        continue
                    print("\n--- Configured Admins ---")
                    for i, phone in enumerate(admins.keys(), start=1):
                        print(f"{i}. {phone}")
                    idx = input("Select number to delete: ").strip()
                    if idx.isdigit() and 1 <= int(idx) <= len(admins):
                        phone = list(admins.keys())[int(idx) - 1]
                        del admins[phone]
                        save_config(config)
                        print(f"❌ Admin {phone} deleted.")
                    else:
                        print("Invalid selection.")
                elif sub_choice == "3":
                    break
                else:
                    print("Invalid choice.")

        # --- Channel management ---
        elif choice == "2":
            while True:
                print(f"\n{Colors.CYAN}--- Manage Channels ---{Colors.RESET}")
                print(f"{Colors.YELLOW}1.{Colors.RESET} Add Channel")
                print(f"{Colors.YELLOW}2.{Colors.RESET} Delete Channel")
                print(f"{Colors.YELLOW}3.{Colors.RESET} Return")
                sub_choice = input("> ").strip()

                if sub_choice == "1":
                    ch = input("Enter channel username (e.g. @MyChannel): ").strip()
                    config.setdefault("channels", [])
                    if ch and ch not in config["channels"]:
                        config["channels"].append(ch)
                        save_config(config)
                        print(f"{Colors.GREEN}✅ Channel {ch} added.{Colors.RESET}")
                    else:
                        print("Channel already exists or invalid.")

                elif sub_choice == "2":
                    channels = config.get("channels", [])
                    if not channels:
                        print("No channels configured.")
                        continue
                    print("\n--- Configured Channels ---")
                    for i, ch in enumerate(channels, start=1):
                        print(f"{i}. {ch}")
                    idx = input("Select number to delete: ").strip()
                    if idx.isdigit() and 1 <= int(idx) <= len(channels):
                        removed = channels.pop(int(idx) - 1)
                        save_config(config)
                        print(f"❌ Channel {removed} deleted.")
                    else:
                        print("Invalid selection.")
                elif sub_choice == "3":
                    break
                else:
                    print("Invalid choice.")

        # --- Reset configuration ---
        elif choice == "3":
            confirm = input("Are you sure you want to reset everything? (y/N): ").strip()
            if confirm.lower() == "y":
                config.clear()
                config.update({"admins": {}, "channels": [], "emoji_map": {}})
                save_config(config)
                print(f"{Colors.GREEN}✅ Configuration reset.{Colors.RESET}")
            else:
                print("Reset cancelled.")

        # --- View configuration ---
        elif choice == "4":
            print(f"\n{Colors.CYAN}--- Current Configuration ---{Colors.RESET}")
            admins = config.get("admins", {})
            channels = config.get("channels", [])
            emoji_map = config.get("emoji_map", {})

            if not admins and not channels and not emoji_map:
                print("⚠️ No configuration found.")
            else:
                if admins:
                    print(f"\n{Colors.YELLOW}Admins:{Colors.RESET}")
                    for i, (phone, creds) in enumerate(admins.items(), start=1):
                        print(f"{i}. {phone} → ID:{creds['api_id']}, HASH:{creds['api_hash'][:6]}****")
                else:
                    print("No admins configured.")

                if channels:
                    print(f"\n{Colors.YELLOW}Channels:{Colors.RESET}")
                    for i, ch in enumerate(channels, start=1):
                        print(f"{i}. {ch}")
                else:
                    print("No channels configured.")

                if emoji_map:
                    print(f"\n{Colors.YELLOW}Emoji Map:{Colors.RESET}")
                    for i, (emoji, cid) in enumerate(emoji_map.items(), start=1):
                        print(f"{i}. {emoji} → ID: {cid}")
                else:
                    print("No emoji mappings configured.")

        elif choice == "5":
            print("Returning to main menu...")
            break
        else:
            print("Invalid option. Try again.")


async def main():
    """Main TelSuit control hub."""
    config = load_config()

    while True:
        print(f"\n{Colors.BOLD}{Colors.GREEN}==============================")
        print("        TelSuit Main Menu")
        print("==============================")
        print(f"{Colors.YELLOW}1.{Colors.RESET} Emoji Enhancer Module")
        print(f"{Colors.YELLOW}2.{Colors.RESET} Channel Cleaner Module")
        print(f"{Colors.YELLOW}3.{Colors.RESET} Settings / Config")
        print(f"{Colors.YELLOW}4.{Colors.RESET} Exit")
        print("------------------------------")
        choice = input("Select an option: ").strip()

        if choice == "1":
            print(f"{Colors.CYAN}Launching Emoji Enhancer...{Colors.RESET}")
            await run_enhancer(config)
        elif choice == "2":
            print(f"{Colors.CYAN}Launching Channel Cleaner...{Colors.RESET}")
            await run_cleaner(config)
        elif choice == "3":
            await run_config_editor(config)
        elif choice == "4":
            print(f"{Colors.YELLOW}Exiting TelSuit. Goodbye!{Colors.RESET}")
            sys.exit(0)
        else:
            print("Invalid option. Try again.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Exited by user.{Colors.RESET}")
