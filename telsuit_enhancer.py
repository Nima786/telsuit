import re
import asyncio
from asyncio import Queue
from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityCustomEmoji
from telethon.tl.custom import Button
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

    # --- Actual emoji enhancement logic (REVISED) ---
    async def process_single_message(event):
        """Enhance emojis, add button, and trigger cleaner when done."""
        # Use event.message to get the original message object for comparison
        original_msg = event.message
        text = original_msg.text or original_msg.message
        if not text:
            return

        # 1. Parse text and find custom emojis
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

        emoji_update_needed = bool(matches)
        
        if emoji_update_needed:
            matches.sort(key=lambda x: x[0])
            new_entities = []
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
            entities_to_use = final_entities
        else:
            entities_to_use = getattr(original_msg, 'entities', None)
        
        # 2. Check for button logic
        buttons_for_send = None
        button_update_needed = False
        product_id = None
        
        # Check if it's a product post AND it currently has NO inline buttons
        if "شناسه محصول" in parsed_text and not getattr(original_msg, "reply_markup", None):
            match = re.search(r"شناسه\s*محصول[:：]?\s*(\d+)", parsed_text)
            if match:
                product_id = match.group(1)
                order_url = f"https://t.me/homplast_salebot?start=product_{product_id}"
                buttons_for_send = [[Button.url("🛒 Order", order_url)]]
                button_update_needed = True

        # 3. Perform Update Logic (Edit OR Delete/Send)
        if not emoji_update_needed and not button_update_needed:
            return # No action needed

        # Prepare to use the new message object for the cleaner call
        current_msg = original_msg 

        try:
            # === FIX: Use Delete and Send if a button is required ===
            if button_update_needed:
                # 3a. Delete the original message
                await client.delete_messages(original_msg.peer_id, [original_msg.id])
                logger.debug(f"🗑️ Deleted original message {original_msg.id} for button insertion.")
                
                # 3b. Send a new message with the formatted data
                new_msg = await client.send_message(
                    entity=original_msg.peer_id,
                    message=parsed_text,
                    formatting_entities=entities_to_use,
                    buttons=buttons_for_send
                )
                
                # Update current_msg object for cleaner
                current_msg = new_msg
                
                # 4. Log successful actions (moved inside try block)
                logger.info(f"✅ Enhanced and sent new message {current_msg.id} in {event.chat.username}")
                logger.info(f"🛒 Added Order button to message {current_msg.id} (Product ID: {product_id})")

            # === Fallback: Use standard Edit if ONLY emojis are required ===
            elif emoji_update_needed:
                edit_kwargs = {
                    'text': parsed_text,
                    'formatting_entities': entities_to_use
                }
                # Since we are only editing emojis, we let the original message buttons/reply_markup remain
                await event.edit(**edit_kwargs)
                logger.info(f"✅ Enhanced message {current_msg.id} in {event.chat.username}")

        except Exception as e:
            logger.error(f"❌ Failed processing message {original_msg.id}: {e}")
            
        finally:
            # 5. Run Cleaner 
            try:
                # Cleaner is only triggered for the initial NEW message, not for edits.
                # We check the original event message state.
                if not button_update_needed and getattr(original_msg, "edit_date", None):
                    logger.debug(f"✏️ Edit detected for message {original_msg.id} — cleaner not triggered")
                    return
                
                if not getattr(event, "is_channel", False):
                    logger.debug(f"💬 Non-channel message ({current_msg.id}) — cleaner not triggered")
                    return

                # Run cleaner on the event, which will use the current_msg's details
                await run_duplicate_check_for_event(client, config, event)
                logger.info(
                    f"🧹 Cleaner triggered after NEW message {current_msg.id} in {event.chat.username}"
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
                await asyncio.sleep(2) # Delay between processing messages

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
