import asyncio
import sys
from telsuit_core import Colors, get_config as load_config, save_config
from telsuit_enhancer import run_enhancer
from telsuit_cleaner import run_cleaner


async def run_config_editor(config):
    """Temporary shared config editor (basic stub)."""
    print(f"\n{Colors.CYAN}--- Shared Config Editor ---{Colors.RESET}")
    print(f"{Colors.YELLOW}1.{Colors.RESET} View Config")
    print(f"{Colors.YELLOW}2.{Colors.RESET} Reset Config")
    print(f"{Colors.YELLOW}3.{Colors.RESET} Return to Main Menu")
    choice = input("> ")

    if choice == "1":
        print("\n--- Current Configuration ---")
        print(config)
    elif choice == "2":
        confirm = input("Are you sure you want to reset all configs? (y/N): ")
        if confirm.lower() == "y":
            config.clear()
            config.update({"admins": {}, "channels": [], "emoji_map": {}})
            save_config(config)
            print(f"{Colors.GREEN}✅ Configuration reset.{Colors.RESET}")
    else:
        print("Returning to main menu...")


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
