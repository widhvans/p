import asyncio
from pyrogram import Client, filters

# --- !! FILL THESE IN !! ---
# Manually enter your details here
API_ID = 12345678  # YOUR API ID HERE
API_HASH = "your_api_hash_here"  # YOUR API HASH HERE
BOT_TOKEN = "your_bot_token_here"  # YOUR BOT TOKEN HERE
# -------------------------

# We create the client app directly here
app = Client(
    "my_test_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# This is the only command handler.
# It has no database calls, no extra logic.
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    print("[TEST SCRIPT] /start command received! Trying to reply...")
    try:
        await message.reply_text("Hello! If you see this, the test was successful.")
        print("[TEST SCRIPT] Reply sent successfully!")
    except Exception as e:
        print(f"[TEST SCRIPT] FAILED TO SEND REPLY. Error: {e}")

async def main():
    print("--- Starting Single File Test Bot ---")
    await app.start()
    print("--- Test Bot Started. Send /start command now. ---")
    await asyncio.Event().wait() # This will keep the bot running

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("--- Test Bot Shutting Down ---")
