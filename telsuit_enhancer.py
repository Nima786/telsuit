import re
import asyncio
from asyncio import Queue
from telethon import TelegramClient, events, Button
from telethon.tl.types import MessageEntityCustomEmoji
from telsuit_core import get_config, logger
from telsuit_cleaner import run_duplicate_check_for_event


# --- 🎨 Emoji Enhancer Logic with Sequential Queue ---
async def start_enhancer(auto=False):
    """Main entry point for emoji enhancement."""
    config = get_config()

    if not config["admins"]:
        print("⚠️ No admins configured.")
        return

    if not config["channels"]:
        print("⚠️ No channels configured.")
        return

    admins = list(config["admins"].keys())

    # Auto-select admin for background/headless mode
    if auto:
        selected_admin = admins[0]
        print(f"🤖 Auto-selected admin: {selected_admin}")
    else:
        print("\n--- Available Admins ---")
        for i, phone in enumerate(admins, start=1):
            print(f"{i}. {phone}")
        sel = input("Select which admin to use: ").strip()
        if not sel.isdigit() or int(sel) < 1 or int(sel) > len(admins):
            print("Invalid selection.")
            return
        selected_admin = admins[int(sel) - 1]

    creds = config["admins"][selected_admin]
    api_id, api_hash, phone = creds["api_id"], creds["api_hash"], selected_admin

    client = TelegramClient(f"enhancer_{phone}.session", int(api_id), api_hash)

    # --- Shared async queue to serialize message processing ---
    message_queue = Queue()
    processing = False

    # --- Actual emoji enhancement logic ---
    async def process_single_message(event):
        """Enhance emojis, add Order button, and trigger cleaner when done."""
        text = event.message.text
        if not text:
            return

        try:
            parsed_text, parsed_entities = await client._parse_message_text(text, "md")
        except TypeError:
            parsed_text, parsed_entities = await client._parse_message_text(
                text=text, parse_mode="md"
            )

        matches = []
        for emoji, doc_id in config["emoji_map"].items():
            for m in re.finditer(re.escape(emoji), parsed_text):
                matches.append((m.start(), m.end(), emoji, int(doc_id)))

        # Build entities for custom emojis
        new_entities = []
        if matches:
            matches.sort(key=lambda x: x[0])
            for start, end, emoji, doc_id in matches:
                prefix = parsed_text[:start]
                offset = len(prefix.encode("utf-16-le")) // 2
                length = len(emoji.encode("utf-16-le")) // 2
                new_entities.append(
                    MessageEntityCustomEmoji(
                        offset=offset, length=length, document_id=doc_id
                    )
                )

        final_entities = (parsed_entities or []) + new_entities
        final_entities.sort(key=lambda e: e.offset)

        # Create inline "Order" button
        # Customize the URL or use Button.inline() with callback_data for bot handling
        order_button = [[Button.url("🛒 Order", url="https://t.me/YourBotUsername")]]
        
        # Alternative: Use inline button with callback (requires bot to handle)
        # order_button = [[Button.inline("🛒 Order", data=b"order_clicked")]]

        msg = event.message

        try:
            await event.edit(
                parsed_text, 
                formatting_entities=final_entities,
                buttons=order_button
            )
            logger.info(f"✅ Enhanced message {msg.id} in {event.chat.username}")
        except Exception as e:
            logger.error(f"❌ Failed editing message {msg.id}: {e}")
        finally:
            try:
                # ✅ Only trigger cleaner for NEW messages (not edits)
                if getattr(msg, "edit_date", None):
                    logger.debug(
                        f"✏️ Edit detected for message {msg.id} — cleaner not triggered"
                    )
                    return

                if not getattr(event, "is_channel", False):
                    logger.debug(
                        f"💬 Non-channel message ({msg.id}) — cleaner not triggered"
                    )
                    return

                await run_duplicate_check_for_event(client, config, event)
                logger.info(
                    f"🧹 Cleaner triggered after NEW message {msg.id} in {event.chat.username}"
                )
            except Exception as clean_err:
                logger.error(f"Cleaner trigger failed: {clean_err}")

    # --- Event Handler: queue incoming messages ---
    async def handle_message(event):
        """Push each new message or edit into queue to process sequentially."""
        await message_queue.put(event)

    # --- Queue worker to process messages one-by-one ---
    async def process_queue():
        nonlocal processing
        if processing:
            return
        processing = True

        while True:
            event = await message_queue.get()
            try:
                await process_single_message(event)
            except Exception as e:
                logger.error(f"Queue error: {e}")
            finally:
                message_queue.task_done()
                await asyncio.sleep(2)  # Delay between processing messages

    # --- Register event handlers ---
    for ch in config["channels"]:
        client.add_event_handler(handle_message, events.NewMessage(chats=ch))
        client.add_event_handler(handle_message, events.MessageEdited(chats=ch))
        logger.info(f"Monitoring channel: {ch}")

    # Start queue worker
    client.loop.create_task(process_queue())

    # Start client
    await client.start(phone=phone)
    logger.info(f"Client started under admin {phone}")
    await client.run_until_disconnected()


# --- ▶️ CLI Entrypoint ---
async def run_enhancer(auto=False):
    """Wrapper for async run (used by main.py)."""
    await start_enhancer(auto=auto)


if __name__ == "__main__":
    import sys

    auto_mode = "--headless" in sys.argv
    try:
        asyncio.run(start_enhancer(auto=auto_mode))
    except KeyboardInterrupt:
        print("🛑 TelSuit stopped by user.")
