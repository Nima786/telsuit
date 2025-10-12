from datetime import datetime, timedelta
import asyncio
import re
import os
import tempfile
from typing import Iterable, Optional, List, Tuple
from logging.handlers import RotatingFileHandler
from telethon import TelegramClient, events
from telethon.tl.types import Message
from telsuit_core import (
    get_config,
    save_config,
    logger,
    print_section,
    print_warning,
    print_success,
    Colors,
)

# --- Logging setup ---
def _ensure_rotating_logs() -> None:
    """Prevent log files from growing indefinitely."""
    for h in list(logger.handlers):
        if isinstance(h, RotatingFileHandler):
            return
    rotating = RotatingFileHandler(
        filename="telsuit.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    rotating.setFormatter(
        logger.handlers[0].formatter if logger.handlers else None
    )
    logger.addHandler(rotating)


_ensure_rotating_logs()


# -------------------------------
# Helper functions
# -------------------------------
async def _delete_messages(client, chat_id, msg_ids, batch=50):
    deleted = 0
    batch_list = []
    for mid in msg_ids:
        batch_list.append(mid)
        if len(batch_list) >= batch:
            await client.delete_messages(chat_id, batch_list)
            deleted += len(batch_list)
            batch_list.clear()
            await asyncio.sleep(0.5)
    if batch_list:
        await client.delete_messages(chat_id, batch_list)
        deleted += len(batch_list)
    return deleted


def _extract_sku(text: str, keyword: str) -> Optional[str]:
    """Extract SKU number following keyword."""
    pattern = rf"{re.escape(keyword)}\s*[:：\-_=]\s*([A-Za-z0-9_\-]+)"
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return None


def _pick_channel(config):
    channels = config.get("channels", [])
    if not channels:
        print_warning("No channels configured.")
        return None
    print(f"\n{Colors.CYAN}--- Configured Channels ---{Colors.RESET}")
    for i, ch in enumerate(channels, start=1):
        print(f"{Colors.YELLOW}{i}.{Colors.RESET} {ch}")
    sel = input("Select channel: ").strip()
    if not sel.isdigit() or not (1 <= int(sel) <= len(channels)):
        print("Invalid selection.")
        return None
    return channels[int(sel) - 1]


# -------------------------------
# Auto trigger by enhancer
# -------------------------------
async def run_duplicate_check_for_event(client, config, event):
    """Triggered automatically after enhancer edits a post."""
    keywords = config.get("cleaner", {}).get("keywords", [])
    if not keywords:
        return
    msg = event.message
    text = (msg.raw_text or "").strip()
    if not text:
        return

    for kw in keywords:
        if kw.lower() in text.lower():
            sku = _extract_sku(text, kw)
            if not sku:
                continue
            ids = []
            async for m in client.iter_messages(event.chat_id, search=sku, limit=400):
                if isinstance(m, Message) and m.id != msg.id:
                    if kw in (m.raw_text or "") and sku in (m.raw_text or ""):
                        ids.append(m.id)
            if ids:
                deleted = await _delete_messages(client, event.chat_id, ids)
                logger.info(
                    "Cleaner(auto): removed %d duplicates (keyword '%s', SKU '%s')",
                    deleted,
                    kw,
                    sku,
                )
            return


# -------------------------------
# Interactive functions
# -------------------------------
async def _menu_manage_keywords(config):
    """Add/Delete/View keywords in shared cleaner section."""
    cleaner_cfg = config.setdefault("cleaner", {})
    keywords = cleaner_cfg.setdefault("keywords", [])
    while True:
        print(f"\n{Colors.CYAN}--- Manage Keywords ---{Colors.RESET}")
        print(f"{Colors.YELLOW}1.{Colors.RESET} Add keyword")
        print(f"{Colors.YELLOW}2.{Colors.RESET} Delete keyword")
        print(f"{Colors.YELLOW}3.{Colors.RESET} View keywords")
        print(f"{Colors.YELLOW}4.{Colors.RESET} Return")
        choice = input("> ").strip()
        if choice == "1":
            kw = input("Enter keyword (e.g. شناسه محصول): ").strip()
            if kw and kw not in keywords:
                keywords.append(kw)
                save_config(config)
                print_success(f"Added keyword: {kw}")
            else:
                print("Invalid or duplicate keyword.")
        elif choice == "2":
            if not keywords:
                print_warning("No keywords to delete.")
                continue
            for i, kw in enumerate(keywords, start=1):
                print(f"{i}. {kw}")
            sel = input("Select number: ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(keywords):
                removed = keywords.pop(int(sel) - 1)
                save_config(config)
                print_success(f"Deleted keyword '{removed}'.")
        elif choice == "3":
            if not keywords:
                print("No keywords configured.")
            else:
                print("Current keywords:")
                for i, kw in enumerate(keywords, start=1):
                    print(f"{i}. {kw}")
        elif choice == "4":
            break
        else:
            print("Invalid selection.")


async def _menu_remove_duplicates(client, chat_id, keywords):
    if not keywords:
        print_warning("No keywords defined. Add one first.")
        return
    print(f"\n{Colors.CYAN}--- Available Keywords ---{Colors.RESET}")
    for i, kw in enumerate(keywords, start=1):
        print(f"{Colors.YELLOW}{i}.{Colors.RESET} {kw}")
    sel = input("Select keyword number: ").strip()
    if not sel.isdigit() or not (1 <= int(sel) <= len(keywords)):
        print("Invalid selection.")
        return
    keyword = keywords[int(sel) - 1]

    print("Scanning posts...")
    groups = {}
    async for msg in client.iter_messages(chat_id, limit=600):
        text = msg.raw_text or ""
        sku = _extract_sku(text, keyword)
        if sku:
            groups.setdefault(sku, []).append(msg.id)

    plan = []
    for sku, ids in groups.items():
        if len(ids) > 1:
            ids_sorted = sorted(ids)
            plan.append((sku, ids_sorted[:-1], ids_sorted[-1]))

    if not plan:
        print_success("No duplicates found.")
        return

    print_section("Duplicate Summary")
    total_delete = 0
    for sku, dels, keep in plan:
        total_delete += len(dels)
        print(f"{sku}: delete {len(dels)}, keep {keep}")

    confirm = input(f"Delete {total_delete} messages? (y/N): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    deleted_total = 0
    for _, dels, _ in plan:
        deleted_total += await _delete_messages(client, chat_id, dels)
    print_success(f"Deleted {deleted_total} duplicates.")


async def _menu_delete_by_keyword(client, chat_id):
    kw = input("Enter keyword: ").strip()
    if not kw:
        print("No keyword entered.")
        return
    ids = []
    async for msg in client.iter_messages(chat_id, limit=300):
        if kw.lower() in (msg.raw_text or "").lower():
            ids.append(msg.id)
    if not ids:
        print_warning("No matches.")
        return
    confirm = input(f"Delete {len(ids)} messages? (y/N): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return
    deleted = await _delete_messages(client, chat_id, ids)
    print_success(f"Deleted {deleted} messages.")


async def _menu_forward_copy(client, chat_id):
    target = input("Target channel (e.g. @backup): ").strip()
    if not target:
        print("No target provided.")
        return
    count = input("How many messages? [10]: ").strip()
    try:
        count = int(count) if count else 10
    except ValueError:
        count = 10
    print(f"\n{Colors.CYAN}--- Mode ---{Colors.RESET}")
    print(f"{Colors.YELLOW}1.{Colors.RESET} Forward (show sender)")
    print(f"{Colors.YELLOW}2.{Colors.RESET} Copy text only (hide sender)")
    print(f"{Colors.YELLOW}3.{Colors.RESET} Reupload media (hide sender)")
    mode = input("> ").strip()

    msgs = []
    async for m in client.iter_messages(chat_id, limit=count):
        msgs.append(m)
    msgs.reverse()

    sent = 0
    for msg in msgs:
        try:
            if mode == "1":
                await client.forward_messages(target, msg)
            elif mode == "2":
                await client.send_message(target, msg.raw_text or "")
            elif mode == "3":
                if msg.media:
                    path = await client.download_media(msg)
                    await client.send_file(target, path, caption=msg.raw_text or "")
                    os.remove(path)
            sent += 1
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.error("Forward error: %s", e)
    print_success(f"Sent {sent} messages to {target}.")


# -------------------------------
# Live monitor
# -------------------------------
async def _start_live_monitor(client, config):
    async def on_new_message(event):
        await run_duplicate_check_for_event(client, config, event)

    for ch in config.get("channels", []):
        client.add_event_handler(on_new_message, events.NewMessage(chats=ch))
        logger.info("Cleaner live-monitoring %s", ch)
    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        print("\nStopped live monitor.")


# -------------------------------
# Entry points
# -------------------------------
async def _interactive_menu(client, config):
    while True:
        print_section("Channel Cleaner Menu")
        print(f"{Colors.YELLOW}1.{Colors.RESET} Remove duplicate posts")
        print(f"{Colors.YELLOW}2.{Colors.RESET} Delete by keyword")
        print(f"{Colors.YELLOW}3.{Colors.RESET} Manage keywords")
        print(f"{Colors.YELLOW}4.{Colors.RESET} Forward / Copy posts")
        print(f"{Colors.YELLOW}5.{Colors.RESET} View cleaner settings")
        print(f"{Colors.YELLOW}6.{Colors.RESET} Start monitoring (new posts)")
        print(f"{Colors.YELLOW}7.{Colors.RESET} Return")

        choice = input("> ").strip()
        if choice == "1":
            ch = _pick_channel(config)
            if ch:
                kws = config.get("cleaner", {}).get("keywords", [])
                await _menu_remove_duplicates(client, ch, kws)
        elif choice == "2":
            ch = _pick_channel(config)
            if ch:
                await _menu_delete_by_keyword(client, ch)
        elif choice == "3":
            await _menu_manage_keywords(config)
        elif choice == "4":
            ch = _pick_channel(config)
            if ch:
                await _menu_forward_copy(client, ch)
        elif choice == "5":
            print(config.get("cleaner", {}))
        elif choice == "6":
            print("Listening for new posts...")
            await _start_live_monitor(client, config)
        elif choice == "7":
            break
        else:
            print("Invalid choice.")


async def start_cleaner(auto=False):
    config = get_config()
    admins = list(config.get("admins", {}).keys())
    if not admins:
        print_warning("No admins configured.")
        return
    phone = admins[0]
    creds = config["admins"][phone]
    client = TelegramClient(f"cleaner_{phone}.session", int(creds["api_id"]),
                            creds["api_hash"])
    await client.start(phone=phone)
    if auto:
        await _start_live_monitor(client, config)
    else:
        await _interactive_menu(client, config)


async def run_cleaner(config=None, auto=False):
    await start_cleaner(auto=auto)
