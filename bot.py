import asyncio
import logging
from typing import Dict, List
from pyrogram import Client
from config import Config
from database.db import get_owner_db_channel, set_owner_db_channel, set_stream_channel, get_user
from utils.helpers import clean_filename, create_post, get_file_raw_link
from features.shortener import get_shortlink

logger = logging.getLogger(__name__)

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="storage_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins={"root": "handlers"},
        )
        self.owner_db_channel_id: int = None
        self.stream_channel_id: int = None
        self.vps_ip: str = Config.VPS_IP
        self.vps_port: int = Config.VPS_PORT
        self.batch_queue: Dict[str, List] = {}
        self.batch_timeout = 10

    async def start(self):
        await super().start()
        me = await self.get_me()
        self.username = f"@{me.username}"
        logger.info(f"Updated bot username to {self.username}")

        owner_db_id = await get_owner_db_channel()
        if owner_db_id:
            self.owner_db_channel_id = owner_db_id
            logger.info(f"Loaded Owner DB ID [{owner_db_id}]")
        
        stream_ch_id = await get_stream_channel()
        if stream_ch_id:
            self.stream_channel_id = stream_ch_id
            logger.info(f"Loaded Stream Channel ID [{stream_ch_id}]")

        asyncio.create_task(self._process_file_queue())
        logger.info("File Processor Worker started.")
        logger.info(f"Web server started at http://{self.vps_ip}:{self.vps_port}")
        logger.info(f"Bot {self.username} started successfully.")

    async def stop(self, *args):
        await super().stop()
        logger.info("Bot stopped.")

    async def _process_file_queue(self):
        while True:
            for batch_key in list(self.batch_queue.keys()):
                messages = self.batch_queue[batch_key]
                first_filename = getattr(messages[0], messages[0].media.value).file_name
                try:
                    batch_display_title, _, _, _ = clean_filename(first_filename)
                    logger.info(f"Created new batch with key '{batch_key}'")
                    await self._finalize_batch(messages, batch_key, batch_display_title)
                except Exception as e:
                    logger.error(f"Error finalizing batch {batch_key}: {e}", exc_info=True)
                finally:
                    self.batch_queue.pop(batch_key, None)
            await asyncio.sleep(1)

    async def _finalize_batch(self, messages: List, batch_key: str, batch_display_title: str):
        user_id = messages[0].forward_from.id if messages[0].forward_from else messages[0].from_user.id
        user = await get_user(user_id)
        if not user or not user.get('db_channels') or not user.get('post_channels'):
            return

        db_channel = user['db_channels'][0]
        copied_messages = []
        for msg in messages:
            media = getattr(msg, msg.media.value)
            raw_link = await get_file_raw_link(msg)
            copied_msg = await msg.copy(db_channel)
            stream_msg = await msg.copy(self.stream_channel_id) if self.stream_channel_id else copied_msg
            await save_file_data(user_id, msg, copied_msg, stream_msg)
            copied_messages.append(copied_msg)

        shortener_enabled = user.get('shortener_enabled', True)
        shortener_mode = user.get('shortener_mode', 'each_time')
        posts = await create_post(self, user_id, copied_messages)
        
        for poster, caption, keyboard in posts:
            for post_channel in user['post_channels']:
                sent_message = await self.send_photo(
                    chat_id=post_channel,
                    photo=poster,
                    caption=caption,
                    reply_markup=keyboard
                ) if poster else await self.send_message(
                    chat_id=post_channel,
                    text=caption,
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )

                if shortener_enabled:
                    for link in re.findall(r'\[➤ Click Here\]\((.*?)\)', caption):
                        shortened = await get_shortlink(link, user_id)
                        caption = caption.replace(link, shortened)
                    await sent_message.edit_caption(caption=caption, reply_markup=keyboard)

app = Bot()

if __name__ == "__main__":
    app.run()
