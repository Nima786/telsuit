from datetime import datetime, timedelta
import asyncio
import re
import os
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

# ============================================================
# Logging setup
# ============================================================


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
    rotating.setFormatter(logger.handlers[0].formatter if logger.handlers else None)
    logger.addHandler(rotating)


_ensure_rotating_logs()


# ============================================================
# Helpers
# ============================================================

async def _delete_messages(client, chat_id, msg_ids, batch=50):
    """
    Delete messages in small batches — now also detects and removes
    entire media groups (albums) by grouped_id.
    """
    deleted = 0
    all_to_delete = set(msg_ids)

    # Collect all grouped media siblings
    async for msg in client.iter_messages(chat_id, ids=msg_ids):
        if getattr(msg, "grouped_id", None):
            async for sibling in client.iter_messages(chat_id, reverse=True, limit=50):
                if getattr(sibling, "grouped_id", None) == msg.grouped_id:
                    all_to_delete.add(sibling.id)

    all_to_delete = sorted(all_to_delete)
    buffer = []
    for mid in all_to_delete:
        buffer.append(mid)
        if len(buffer) >= batch:
            await client.delete_messages(chat_id, buffer)
            deleted += len(buffer)
            buffer.clear()
            await asyncio.sleep(0.4)
    if buffer:
        await client.delete_messages(chat_id, buffer)
        deleted += len(buffer)
    return deleted


def _extract_sku(text: str, keyword: str):
    """Extract SKU number following keyword."""
    pattern = rf"{re.escape(keyword)}\s*[:：\-_=]\s*([A-Za-z0-9_\-]+)"
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def _pick_channel(config, label="channel"):
    """Unified channel selector with a label."""
    channels = config.get("channels", [])
    if not channels:
        print_warning("No channels configured.")
        return None
    print(f"\n{Colors.CYAN}--- Select {label} ---{Colors.RESET}")
    for i, ch in enumerate(channels, start=1):
        print(f"{Colors.YELLOW}{i}.{Colors.RESET} {ch}")
    sel = input("> ").strip()
    if not sel.isdigit() or not (1 <= int(sel) <= len(channels)):
        print("Invalid selection.")
        return None
    return channels[int(sel) - 1]


# ============================================================
# Auto trigger by enhancer
# ============================================================

async def run_duplicate_check_for_event(client, config, event):
    """Triggered automatically by enhancer after emoji conversion."""
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


# ============================================================
# Keyword Management
# ============================================================

async def _menu_manage_keywords(config):
    """Add/Delete/View keywords."""
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


# ============================================================
# Duplicate & Delete Functions
# ============================================================

async def _menu_remove_duplicates(client, chat_id, keywords):
    """Remove duplicates based on SKU extracted from configured keywords."""
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

    print("Scanning posts for duplicates...")
    groups = {}
    async for msg in client.iter_messages(chat_id, limit=1000):
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
    """Delete all messages containing a given keyword."""
    kw = input("Enter keyword: ").strip()
    if not kw:
        print("No keyword entered.")
        return
    ids = []
    async for msg in client.iter_messages(chat_id, limit=400):
        if kw.lower() in (msg.raw_text or "").lower():
            ids.append(msg.id)
    if not ids:
        print_warning("No matches.")
        return
    confirm = input(f"Delete {len(ids)} messages containing '{kw}'? (y/N): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return
    deleted = await _delete_messages(client, chat_id, ids)
    print_success(f"Deleted {deleted} messages.")


async def _menu_delete_by_date(client, chat_id):
    """Delete messages using multiple date-based modes."""
    print(f"\n{Colors.CYAN}--- Delete by Date Options ---{Colors.RESET}")
    print(f"{Colors.YELLOW}1.{Colors.RESET} Older than N days")
    print(f"{Colors.YELLOW}2.{Colors.RESET} Between two dates")
    print(f"{Colors.YELLOW}3.{Colors.RESET} Before specific date")
    print(f"{Colors.YELLOW}4.{Colors.RESET} Last N messages (quick)")
    print(f"{Colors.YELLOW}5.{Colors.RESET} Return")
    choice = input("> ").strip()
    now = datetime.utcnow()
    ids = []

    if choice == "1":
        days = int(input("Delete messages older than how many days?: ").strip())
        cutoff = now - timedelta(days=days)
        async for msg in client.iter_messages(chat_id, limit=1500):
            if msg.date and msg.date.replace(tzinfo=None) < cutoff:
                ids.append(msg.id)
        note = f"older than {days} days"

    elif choice == "2":
        s = input("Start date (YYYY-MM-DD): ").strip()
        e = input("End date (YYYY-MM-DD): ").strip()
        start = datetime.strptime(s, "%Y-%m-%d")
        end = datetime.strptime(e, "%Y-%m-%d")
        async for msg in client.iter_messages(chat_id, limit=2000):
            if msg.date and start <= msg.date.replace(tzinfo=None) <= end:
                ids.append(msg.id)
        note = f"between {s} and {e}"

    elif choice == "3":
        cutoff = datetime.strptime(input("Delete before (YYYY-MM-DD): ").strip(), "%Y-%m-%d")
        async for msg in client.iter_messages(chat_id, limit=2000):
            if msg.date and msg.date.replace(tzinfo=None) < cutoff:
                ids.append(msg.id)
        note = f"before {cutoff.date()}"

    elif choice == "4":
        n = int(input("How many recent messages to delete?: ").strip())
        async for msg in client.iter_messages(chat_id, limit=n):
            ids.append(msg.id)
        note = f"last {n} messages"

    elif choice == "5":
        return
    else:
        print("Invalid option.")
        return

    if not ids:
        print_warning("No matching messages found.")
        return
    confirm = input(f"Delete {len(ids)} messages {note}? (y/N): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return
    deleted = await _delete_messages(client, chat_id, ids)
    print_success(f"Deleted {deleted} messages {note}.")


# ============================================================
# Improved Forward / Copy
# ============================================================

async def _menu_forward_copy(client, config):
    """Forward, copy, or reupload messages between channels."""
    src = _pick_channel(config, "source channel (copy from)")
    if not src:
        return
    target = _pick_channel(config, "target channel (send to)")
    if not target:
        return

    print(f"\n{Colors.CYAN}--- Message Range ---{Colors.RESET}")
    start_from = input("Start from message offset [0 = newest]: ").strip()
    count = input("How many messages to transfer? [10]: ").strip()
    try:
        start_from = int(start_from) if start_from else 0
        count = int(count) if count else 10
    except ValueError:
        print("Invalid input.")
        return

    print(f"\n{Colors.CYAN}--- Sort Order ---{Colors.RESET}")
    print(f"{Colors.YELLOW}1.{Colors.RESET} Oldest to newest")
    print(f"{Colors.YELLOW}2.{Colors.RESET} Newest to oldest")
    order = input("> ").strip()
    reverse = order == "2"

    print(f"\n{Colors.CYAN}--- Mode ---{Colors.RESET}")
    print(f"{Colors.YELLOW}1.{Colors.RESET} Forward (show sender)")
    print(f"{Colors.YELLOW}2.{Colors.RESET} Copy text only (hide sender)")
    print(f"{Colors.YELLOW}3.{Colors.RESET} Reupload media (hide sender)")
    mode = input("> ").strip()

    print(
        f"\nSource: {src}\nTarget: {target}\nCount: {count} (offset {start_from})\nMode: {mode}"
    )
    confirm = input("Proceed? (y/N): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    msgs = []
    async for m in client.iter_messages(src, limit=start_from + count):
        msgs.append(m)
    msgs = msgs[start_from: start_from + count]
    if reverse:
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
            logger.error("Forward/copy failed: %s", e)
    print_success(f"Transferred {sent} messages from {src} → {target}.")


# ============================================================
# Interactive Menu
# ============================================================

async def _interactive_menu(client, config):
    while True:
        print_section("Channel Cleaner Menu")
        print(f"{Colors.YELLOW}1.{Colors.RESET} Remove duplicate posts")
        print(f"{Colors.YELLOW}2.{Colors.RESET} Delete by keyword")
        print(f"{Colors.YELLOW}3.{Colors.RESET} Delete by date")
        print(f"{Colors.YELLOW}4.{Colors.RESET} Manage keywords")
        print(f"{Colors.YELLOW}5.{Colors.RESET} Forward / Copy posts")
        print(f"{Colors.YELLOW}6.{Colors.RESET} View cleaner settings")
        print(f"{Colors.YELLOW}7.{Colors.RESET} Return to TelSuit")

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
            ch = _pick_channel(config)
            if ch:
                await _menu_delete_by_date(client, ch)
        elif choice == "4":
            await _menu_manage_keywords(config)
        elif choice == "5":
            await _menu_forward_copy(client, config)
        elif choice == "6":
            print(config.get("cleaner", {}))
        elif choice == "7":
            break
        else:
            print("Invalid option.")


# ============================================================
# Entrypoint
# ============================================================

async def start_cleaner(auto=False):
    config = get_config()
    admins = list(config.get("admins", {}).keys())
    if not admins:
        print_warning("No admins configured.")
        return
    phone = admins[0]
    creds = config["admins"][phone]
    client = TelegramClient(
        f"cleaner_{phone}.session", int(creds["api_id"]), creds["api_hash"]
    )
    await client.start(phone=phone)
    if auto:
        pass
    else:
        await _interactive_menu(client, config)


async def run_cleaner(config=None, auto=False):
    await start_cleaner(auto=auto)
