#!/usr/bin/env python3
"""
TelSuit — Telegram Automation Suite
-----------------------------------
A unified toolkit for managing Telegram channels:
• Emoji Enhancer — converts standard emojis to custom ones
• Channel Cleaner — removes duplicate or unwanted posts
• Designed for automation and stability
"""

import os
import sys
import asyncio
import logging
from colorama import Fore, Style

# --- 🧩 Modules (to be added later) ---
# from enhancer import start_enhancer
# from cleaner import start_cleaner


# --- 🎨 UI Colors ---
class Colors:
    GREEN = Fore.GREEN
    YELLOW = Fore.YELLOW
    CYAN = Fore.CYAN
    RED = Fore.RED
    BOLD = Style.BRIGHT
    RESET = Style.RESET_ALL


# --- ⚙️ Logging setup ---
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("TelSuit")


# --- 🧠 Main menu ---
async def main_menu():
    while True:
        print(f"\n{Colors.BOLD}{Colors.CYAN}==============================")
        print("         TelSuit Main Menu")
        print("==============================")
        print(f"{Colors.YELLOW}1.{Colors.RESET} Emoji Enhancer Module")
        print(f"{Colors.YELLOW}2.{Colors.RESET} Channel Cleaner Module")
        print(f"{Colors.YELLOW}3.{Colors.RESET} Settings / Config")
        print(f"{Colors.YELLOW}4.{Colors.RESET} Exit")
        print("------------------------------")

        choice = input("Select an option: ").strip()

        if choice == "1":
            print(f"{Colors.GREEN}Launching Emoji Enhancer...{Colors.RESET}")
            # await start_enhancer()  ← to be added later
        elif choice == "2":
            print(f"{Colors.GREEN}Launching Channel Cleaner...{Colors.RESET}")
            # await start_cleaner()  ← to be added later
        elif choice == "3":
            print(f"{Colors.YELLOW}Config editor coming soon...{Colors.RESET}")
        elif choice == "4":
            print(f"{Colors.RED}Exiting TelSuit. Goodbye!{Colors.RESET}")
            break
        else:
            print(f"{Colors.RED}Invalid selection, please try again.{Colors.RESET}")


# --- 🚀 Headless (background) mode ---
async def run_headless():
    """Used by systemd to run automatically without menus."""
    logger.info("Running TelSuit in headless mode.")
    # await start_enhancer(auto=True)  ← will default to Enhancer


# --- 🏁 Entry point ---
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--headless":
        asyncio.run(run_headless())
    else:
        asyncio.run(main_menu())
