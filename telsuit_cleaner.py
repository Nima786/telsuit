# telsuit_cleaner.py
# TelSuit — Channel Cleaner module
# --------------------------------
# - Duplicate sweep (manual + auto on new posts via enhancer hook)
# - Delete by keyword / age
# - Forward / copy messages
# - Persistent "cleaner" settings (keywords) in shared config
# - Rotating logs to avoid growth
# - Flake8-compliant

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from typing import Iterable, List, Optional

from telethon import TelegramClient, events
from telethon.tl.types import Message

from telsuit_core import (
    get_config,
    save_config,
    logger,
    print_section,
    print_warning,
    print_success,
)

# -----------------------------------------------------------------------------
# Logging: ensure rotating file handler (1 MB x 3 files) to avoid log bloat
# -----------------------------------------------------------------------------

def _ensure_rotating_logs() -> None:
    """Swap any plain FileHandler with RotatingFileHandler (1MB x 3 files)."""
    need_add = True
    for h in list(logger.handlers):
        if isinstance(h, RotatingFileHandler):
            need_add = False
        if getattr(h, "baseFilename", None) and not isinstance(
            h, RotatingFileHandler
        ):
            logger.removeHandler(h)
    if need_add:
        rotating = RotatingFileHandler(
            filename="telsuit.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        if logger.handlers:
            rotating.setFormatter(logger.handlers[0].formatter)
        logger.addHandler(rotating)


_ensure_rotating_logs()


# -----------------------------------------------------------------------------
# Config helpers
# -----------------------------------------------------------------------------

def _ensure_cleaner_config(config: dict) -> dict:
    """Make sure 'cleaner' key exists with expected structure."""
    cleaner = config.get("cleaner")
    if not isinstance(cleaner, dict):
        cleaner = {}
        config["cleaner"] = cleaner

    cleaner.setdefault("keywords", [])           # list[str]
    cleaner.setdefault("forward_channels", [])   # reserved for future
    cleaner.setdefault("delete_rules", {})       # reserved for future
    return cleaner


def _persist_keywords(config: dict, keywords: Iterable[str]) -> None:
    cleaner = _ensure_cleaner_config(config)
    # Normalize: trim, dedupe, keep non-empty
    normalized = []
    seen = set()
    for kw in (kw.strip() for kw in keywords):
        if kw and kw.lower() not in seen:
            normalized.append(kw)
            seen.add(kw.lower())
    cleaner["keywords"] = normalized
    save_config(config)


# -----------------------------------------------------------------------------
# Telegram utilities
# -----------------------------------------------------------------------------

async def _delete_messages(
    client: TelegramClient, chat_id: str, msg_ids: Iterable[int]
) -> int:
    """Delete messages in small batches to respect Telegram limits."""
    deleted = 0
    batch: List[int] = []
    for mid in msg_ids:
        batch.append(mid)
        if len(batch) >= 50:
            await client.delete_messages(chat_id, batch)
            deleted += len(batch)
            batch.clear()
            await asyncio.sleep(0.4)
    if batch:
        await client.delete_messages(chat_id, batch)
        deleted += len(batch)
    return deleted


async def _search_duplicates(
    client: TelegramClient,
    chat_id: str,
    keyword: str,
    keep_latest_id: Optional[int],
    scan_limit: int = 300,
) -> List[int]:
    """
    Find messages containing `keyword`. Return IDs to delete.
    If keep_latest_id is provided, exclude it from results.
    """
    to_delete: List[int] = []
    async for msg in client.iter_messages(chat_id, search=keyword, limit=scan_limit):
        if isinstance(msg, Message):
            text = (msg.raw_text or "")
            if keyword.lower() in text.lower():
                if keep_latest_id is None or msg.id != keep_latest_id:
                    to_delete.append(msg.id)
    return to_delete


# -----------------------------------------------------------------------------
# Enhancer hook (called right after successful emoji enhancement)
# -----------------------------------------------------------------------------

async def run_duplicate_check_for_event(
    client: TelegramClient,
    config: dict,
    event,
) -> None:
    """
    Lightweight duplicate sweep triggered by the enhancer AFTER edit.
    - Look for the first configured keyword present in the edited message
    - Delete older duplicates, keep the just-edited message
    """
    cleaner = _ensure_cleaner_config(config)
    keywords: List[str] = cleaner.get("keywords", [])
    if not keywords:
        return

    msg: Message = event.message
    text = (msg.raw_text or "").strip()
    if not text:
        return

    matched = None
    for kw in keywords:
        if kw and kw.lower() in text.lower():
            matched = kw
            break
    if not matched:
        return

    chat_id = event.chat_id
    try:
        dup_ids = await _search_duplicates(
            client=client,
            chat_id=chat_id,
            keyword=matched,
            keep_latest_id=msg.id,
            scan_limit=300,
        )
        if not dup_ids:
            return

        deleted = await _delete_messages(client, chat_id, dup_ids)
        if deleted:
            logger.info(
                "Cleaner(auto): removed %d duplicates for '%s' in %s (kept %s)",
                deleted,
                matched,
                chat_id,
                msg.id,
            )
    except Exception as exc:
        logger.error("Cleaner(auto) failed: %s", exc)


# -----------------------------------------------------------------------------
# Interactive ops (menu actions)
# -----------------------------------------------------------------------------

def _pick_channel(config: dict) -> Optional[str]:
    channels = config.get("channels", [])
    if not channels:
        print_warning("No channels configured.")
        return None

    print("\n--- Configured Channels ---")
    for i, ch in enumerate(channels, start=1):
        print(f"{i}. {ch}")
    sel = input("Select channel: ").strip()
    if not sel.isdigit() or not (1 <= int(sel) <= len(channels)):
        print("Invalid selection.")
        return None
    return channels[int(sel) - 1]


async def _menu_remove_duplicates(client: TelegramClient, chat_id: str) -> None:
    kw = input("Keyword / SKU to deduplicate by: ").strip()
    if not kw:
        print("No keyword entered.")
        return

    print("Searching duplicates...")
    dup_ids = await _search_duplicates(client, chat_id, kw, keep_latest_id=None)
    if not dup_ids:
        print_success("No duplicates found.")
        return

    keep_id = max(dup_ids)
    to_delete = [mid for mid in dup_ids if mid != keep_id]

    print(f"Found {len(dup_ids)} matching posts. "
          f"Will keep newest (id {keep_id}) and delete {len(to_delete)}.")
    confirm = input("Proceed with deletion? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    deleted = await _delete_messages(client, chat_id, to_delete)
    print_success(f"Deleted {deleted} messages. Kept {keep_id}.")


async def _menu_delete_by_keyword(client: TelegramClient, chat_id: str) -> None:
    kw = input("Keyword to delete: ").strip()
    if not kw:
        print("No keyword entered.")
        return
    limit_str = input("How many recent messages to scan? [200]: ").strip()
    try:
        limit = int(limit_str) if limit_str else 200
    except ValueError:
        limit = 200

    ids: List[int] = []
    async for msg in client.iter_messages(chat_id, limit=limit):
        text = (msg.raw_text or "")
        if kw.lower() in text.lower():
            ids.append(msg.id)

    if not ids:
        print_warning("Nothing matched.")
        return

    print(f"Matched {len(ids)} messages containing '{kw}'.")
    confirm = input("Delete them? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    deleted = await _delete_messages(client, chat_id, ids)
    print_success(f"Deleted {deleted} messages containing '{kw}'.")


async def _menu_delete_by_age(client: TelegramClient, chat_id: str) -> None:
    days_str = input("Delete messages older than N days: ").strip()
    try:
        days = int(days_str)
    except ValueError:
        print("Invalid number.")
        return

    cutoff = datetime.utcnow() - timedelta(days=days)
    ids: List[int] = []

    async for msg in client.iter_messages(chat_id, limit=500):
        if msg.date and msg.date.replace(tzinfo=None) < cutoff:
            ids.append(msg.id)

    if not ids:
        print_warning("No messages older than that.")
        return

    print(f"{len(ids)} messages older than {days} days will be removed.")
    confirm = input("Proceed? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    deleted = await _delete_messages(client, chat_id, ids)
    print_success(f"Deleted {deleted} messages older than {days} days.")


async def _menu_forward_copy(client: TelegramClient, chat_id: str) -> None:
    target = input("Target channel (e.g. @mytarget): ").strip()
    if not target:
        print("No target provided.")
        return
    count_str = input("How many recent messages to send? [10]: ").strip()
    try:
        count = int(count_str) if count_str else 10
    except ValueError:
        count = 10

    mode = input("Mode: (F)orward or (C)opy text only? [F/C]: ").strip().lower()
    sent = 0

    async for msg in client.iter_messages(chat_id, limit=count):
        try:
            if mode == "c":
                text = msg.raw_text or ""
                if text:
                    await client.send_message(target, text)
                    sent += 1
            else:
                await client.forward_messages(target, msg)
                sent += 1
            await asyncio.sleep(0.3)
        except Exception as exc:
            logger.error("Forward/copy failed for %s: %s", msg.id, exc)

    print_success(f"Sent {sent} messages to {target}.")


def _menu_cleaner_settings(config: dict) -> None:
    """Manage persistent cleaner settings (currently just keywords)."""
    while True:
        print("\n==============================")
        print("      Cleaner Settings")
        print("==============================")
        print("1. Add keyword")
        print("2. Delete keyword")
        print("3. View keywords")
        print("4. Return")
        choice = input("Select option: ").strip()

        cleaner = _ensure_cleaner_config(config)
        keywords: List[str] = list(cleaner.get("keywords", []))

        if choice == "1":
            raw = input("Enter keywords (comma-separated): ").strip()
            items = [x.strip() for x in raw.split(",") if x.strip()]
            keywords.extend(items)
            _persist_keywords(config, keywords)
            print_success("Keywords updated.")

        elif choice == "2":
            if not keywords:
                print_warning("No keywords stored.")
                continue
            print("\n--- Current Keywords ---")
            for i, kw in enumerate(keywords, start=1):
                print(f"{i}. {kw}")
            idx = input("Select number to delete: ").strip()
            if idx.isdigit() and 1 <= int(idx) <= len(keywords):
                removed = keywords.pop(int(idx) - 1)
                _persist_keywords(config, keywords)
                print_success(f"Deleted keyword '{removed}'.")
            else:
                print("Invalid selection.")

        elif choice == "3":
            if not keywords:
                print("No keywords stored.")
            else:
                print("\n--- Current Keywords ---")
                for i, kw in enumerate(keywords, start=1):
                    print(f"{i}. {kw}")

        elif choice == "4":
            break
        else:
            print("Invalid option.")


# -----------------------------------------------------------------------------
# Live monitor: NEW posts only (for interactive and service modes)
# -----------------------------------------------------------------------------

async def _start_live_monitor(client: TelegramClient, config: dict) -> None:
    async def on_new_message(event):
        msg = event.message
        if not msg or not (msg.raw_text or "").strip():
            return
        await run_duplicate_check_for_event(client, config, event)

    for ch in config.get("channels", []):
        client.add_event_handler(on_new_message, events.NewMessage(chats=ch))
        logger.info("Cleaner live-monitoring new posts in: %s", ch)

    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        print("\nStopped live monitor.")


# -----------------------------------------------------------------------------
# Interactive menu shell
# -----------------------------------------------------------------------------

async def _interactive_menu(client: TelegramClient, config: dict) -> None:
    while True:
        print_section("Channel Cleaner Menu")
        print("1. Remove duplicate posts")
        print("2. Delete by keyword")
        print("3. Delete by date (older than N days)")
        print("4. Forward / Copy recent posts")
        print("5. Cleaner settings")
        print("6. Start automatic monitoring (new posts)")
        print("7. Return to TelSuit menu")

        choice = input("Select option: ").strip()

        if choice == "1":
            ch = _pick_channel(config)
            if ch:
                await _menu_remove_duplicates(client, ch)

        elif choice == "2":
            ch = _pick_channel(config)
            if ch:
                await _menu_delete_by_keyword(client, ch)

        elif choice == "3":
            ch = _pick_channel(config)
            if ch:
                await _menu_delete_by_age(client, ch)

        elif choice == "4":
            ch = _pick_channel(config)
            if ch:
                await _menu_forward_copy(client, ch)

        elif choice == "5":
            _menu_cleaner_settings(config)

        elif choice == "6":
            print("Starting live monitor for NEW posts only. Ctrl+C to stop.")
            await _start_live_monitor(client, config)

        elif choice == "7":
            print("Returning to TelSuit...")
            break

        else:
            print("Invalid option.")


# -----------------------------------------------------------------------------
# Public entrypoints
# -----------------------------------------------------------------------------

async def start_cleaner(auto: bool = False) -> None:
    """
    Main cleaner entry point.
      * auto=False → open interactive menu
      * auto=True  → headless: live monitor for new posts (service usage)
    """
    config = get_config()
    admins = list(config.get("admins", {}).keys())
    if not admins:
        print_warning("No admins configured.")
        return

    selected_admin = admins[0]
    print(f"🤖 Auto-selected admin: {selected_admin}")

    creds = config["admins"][selected_admin]
    api_id, api_hash = int(creds["api_id"]), creds["api_hash"]

    client = TelegramClient(f"cleaner_{selected_admin}.session", api_id, api_hash)
    await client.start(phone=selected_admin)
    logger.info("Cleaner client started under admin %s", selected_admin)

    if auto:
        await _start_live_monitor(client, config)
    else:
        await _interactive_menu(client, config)


async def run_cleaner(config: Optional[dict] = None, auto: bool = False) -> None:
    """
    Wrapper used by TelSuit main menu.
    The config param is accepted for symmetry but the cleaner re-reads config
    internally to ensure fresh state when called headless.
    """
    await start_cleaner(auto=auto)
