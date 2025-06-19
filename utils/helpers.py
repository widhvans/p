# helpers.py

import re
import base64
import logging
import PTN
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, ChannelInvalid, PeerIdInvalid, ChannelPrivate
from config import Config
from database.db import get_user, remove_from_list
from features.poster import get_poster
from thefuzz import fuzz

logger = logging.getLogger(__name__)

FILES_PER_POST = 20


def clean_filename(name: str):
    """
    The definitive 'champion pro' filename cleaner.
    """
    if not name:
        return "Untitled", "Untitled", None

    try:
        processed_name = name.replace('.', ' ').replace('_', ' ')
        
        parsed_info = PTN.parse(processed_name)
        base_title = parsed_info.get('title')
        year = str(parsed_info.get('year')) if parsed_info.get('year') else None

        if not base_title:
            raise ValueError("PTN did not find a title, triggering fallback.")

        if 'season' in parsed_info and 'episode' in parsed_info:
            season = parsed_info.get('season')
            episode = parsed_info.get('episode')
            full_title = f"{base_title} S{str(season).zfill(2)}E{str(episode).zfill(2)}"
            episode_name = parsed_info.get('episodeName')
            if episode_name:
                full_title = f"{full_title} - {episode_name}"
            return base_title.strip(), full_title.strip(), year

        return base_title.strip(), base_title.strip(), year

    except Exception:
        logger.warning(f"PTN failed for '{name}'. Using the robust regex fallback.")
        
        fallback_name = re.sub(r'\.[^.]*$', '', name)
        fallback_name = fallback_name.replace('.', ' ').replace('_', ' ').strip()
        fallback_name = re.sub(r'\s*\(\d{4}\)\s*', '', fallback_name).strip()
        fallback_name = re.sub(r'\s*\[.*?\]\s*', '', fallback_name).strip()

        match = re.split(r'\b(19|20)\d{2}\b|720p|1080p|4k|webrip|web-dl|bluray|hdrip', fallback_name, maxsplit=1, flags=re.I)
        final_title = match[0].strip()
        
        if not final_title:
            final_title = fallback_name

        return final_title, final_title, None


async def create_post(client, user_id, messages):
    """
    Creates a professionally designed post with wrapped title and footer line.
    """
    user = await get_user(user_id)
    if not user: return []
    first_media_obj = getattr(messages[0], messages[0].media.value, None)
    if not first_media_obj: return []

    primary_base_title, _, year = clean_filename(first_media_obj.file_name)
    
    cleaned_primary_title = re.sub(r'@\S+', '', primary_base_title)
    cleaned_primary_title = re.sub(r'Join Us On Telegram', '', cleaned_primary_title, flags=re.IGNORECASE)
    cleaned_primary_title = cleaned_primary_title.strip()

    def similarity_sorter(msg):
        media_obj = getattr(msg, msg.media.value, None)
        if not media_obj: return (1.0, "")
        base, _, _ = clean_filename(media_obj.file_name)
        similarity_score = 1.0 - calculate_title_similarity(cleaned_primary_title, base)
        natural_key = natural_sort_key(media_obj.file_name)
        return (similarity_score, natural_key)
    messages.sort(key=similarity_sorter)
    
    base_caption_header = f"🎬 **{cleaned_primary_title} {f'({year})' if year else ''}**"
    
    post_poster = await get_poster(cleaned_primary_title, year) if user.get('show_poster', True) else None
    
    footer_buttons = user.get('footer_buttons', [])
    footer_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(btn['name'], url=btn['url'])] for btn in footer_buttons]) if footer_buttons else None
    
    header_line = "▰▱▰▱▰▱▰▱▰▱▰▱▰▱▰▱"
    footer_line = "•·•·•·•·•·•·•·•·•·••·•·•·•·•·•·•·•"

    posts, total = [], len(messages)
    num_posts = (total + FILES_PER_POST - 1) // FILES_PER_POST
    for i in range(num_posts):
        chunk = messages[i*FILES_PER_POST:(i+1)*FILES_PER_POST]
        header = f"{base_caption_header} (Part {i+1}/{num_posts})" if num_posts > 1 else base_caption_header
        links = []
        for m in chunk:
            media = getattr(m, m.media.value, None)
            if not media: continue
            
            _, full_cleaned_label, _ = clean_filename(media.file_name)
            
            label_no_mentions = re.sub(r'@\S+', '', full_cleaned_label)
            label_no_mentions = re.sub(r'Join Us On Telegram', '', label_no_mentions, flags=re.IGNORECASE)
            label_no_mentions = label_no_mentions.strip()

            parsed_info = PTN.parse(media.file_name)
            extra_tags = [
                parsed_info.get('resolution'),
                parsed_info.get('quality'),
                parsed_info.get('audio'),
                parsed_info.get('codec'),
                parsed_info.get('group')
            ]
            filtered_text = " | ".join(tag for tag in extra_tags if tag)

            link = f"http://{Config.VPS_IP}:{Config.VPS_PORT}/get/{media.file_unique_id}"
            
            file_entry = f"📁 `{label_no_mentions or media.file_name}`"
            
            if filtered_text:
                file_entry += f"\n    `{filtered_text}`"
            
            file_entry += f"\n    [➤ Click Here]({link})"
            
            links.append(file_entry)

        final_caption = f"{header_line}\n{header}\n{header_line}\n\n" + "\n\n".join(links)
        final_caption += f"\n\n{footer_line}"

        posts.append((post_poster, final_caption, footer_keyboard))
        
    return posts


def get_title_key(filename: str) -> str:
    base_title, _, _ = clean_filename(filename)
    cleaned_base_title = re.sub(r'@\S+', '', base_title)
    cleaned_base_title = re.sub(r'Join Us On Telegram', '', cleaned_base_title, flags=re.IGNORECASE)
    return cleaned_base_title.lower().strip()

async def get_main_menu(user_id):
    user_settings = await get_user(user_id)
    if not user_settings:
        return "Could not find your settings.", InlineKeyboardMarkup([])
    
    db_channels = user_settings.get('db_channels', [])
    post_channels = user_settings.get('post_channels', [])

    if db_channels and post_channels:
        menu_text = (
            "✅ **Setup Complete!**\n\n"
            "You can now forward files to your Database Channel. "
            "I will automatically create posts in your Post Channel."
        )
    else:
        menu_text = "⚙️ **Bot Settings**\n\nChoose an option below to configure the bot."
    
    shortener_text = "⚙️ Shortener Settings" if user_settings.get('shortener_url') else "🔗 Set Shortener"
    fsub_text = "⚙️ Manage FSub" if user_settings.get('fsub_channel') else "📢 Set FSub"
    
    buttons = [
        [InlineKeyboardButton("🗂️ Manage Channels", callback_data="manage_channels_menu")],
        [InlineKeyboardButton(shortener_text, callback_data="shortener_menu"), InlineKeyboardButton("🔄 Backup Links", callback_data="backup_links")],
        [InlineKeyboardButton("✍️ Filename Link", callback_data="filename_link_menu"), InlineKeyboardButton("👣 Footer Buttons", callback_data="manage_footer")],
        [InlineKeyboardButton("🖼️ IMDb Poster", callback_data="poster_menu"), InlineKeyboardButton("📂 My Files", callback_data="my_files_1")],
        [InlineKeyboardButton(fsub_text, callback_data="fsub_menu"), InlineKeyboardButton("❓ How to Download", callback_data="how_to_download_menu")]
    ]
    
    if user_id == Config.ADMIN_ID:
        admin_buttons = [
            InlineKeyboardButton("🔑 Set Owner DB", callback_data="set_owner_db"),
            InlineKeyboardButton("🌊 Set Stream Channel", callback_data="set_stream_ch")
        ]
        buttons.append(admin_buttons)
        buttons.append([InlineKeyboardButton("⚠️ Reset Files DB", callback_data="reset_db_prompt")])
        
    keyboard = InlineKeyboardMarkup(buttons)
    return menu_text, keyboard

# ================================================================= #
# VVVVVV BUG FIX: Ab yeh function sabhi tarah ke invalid channels ko remove karega VVVVVV #
# ================================================================= #
async def notify_and_remove_invalid_channel(client, user_id, channel_id, channel_type):
    """
    Checks if a channel is accessible. If not, notifies the user and removes the invalid
    channel ID from the database to prevent errors.
    """
    db_key = f"{channel_type.lower()}_channels"
    try:
        # Try a lightweight check first
        await client.get_chat_member(channel_id, "me")
        return True
    except (UserNotParticipant, ChatAdminRequired, ChannelInvalid, PeerIdInvalid, ChannelPrivate) as e:
        # These are expected errors when bot loses access.
        logger.warning(f"Channel {channel_id} is inaccessible due to '{type(e).__name__}'. Removing from DB for user {user_id}.")
        
        error_text = (
            f"⚠️ **Channel Inaccessible**\n\n"
            f"Your {channel_type.title()} Channel (ID: `{channel_id}`) is no longer accessible. "
            f"This can happen if I was removed or the channel was deleted.\n\n"
            f"It has been automatically removed from your settings."
        )
        try:
            # Notify the user and remove the faulty ID from the database
            await client.send_message(user_id, error_text)
            await remove_from_list(user_id, db_key, channel_id)
        except Exception as notify_error:
            logger.error(f"Failed to notify or remove channel for user {user_id}. Error: {notify_error}")
        return False
    except Exception as e:
        # This catches any other unexpected error (like the one in the logs).
        # We assume the channel is invalid and remove it to prevent future bugs.
        logger.error(f"An unexpected error occurred while checking channel {channel_id}: {e}. Assuming invalid and removing.")
        
        error_text = (
            f"🗑️ **Auto-Clean**\n\n"
            f"An unexpected error occurred with one of your saved {channel_type.title()} Channels (ID: `{channel_id}`). "
            f"To prevent issues, this invalid entry has been removed from your settings."
        )
        try:
            # Notify the user and remove the faulty ID
            await client.send_message(user_id, error_text)
            await remove_from_list(user_id, db_key, channel_id)
        except Exception as notify_error:
            logger.error(f"Failed to notify/remove faulty channel ID after unexpected error for user {user_id}. Error: {notify_error}")
        return False

def calculate_title_similarity(title1: str, title2: str) -> float:
    return fuzz.token_sort_ratio(title1, title2) / 100.0

def go_back_button(user_id):
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Go Back", callback_data=f"go_back_{user_id}")]])

def format_bytes(size):
    if not isinstance(size, (int, float)): return "N/A"
    power = 1024; n = 0; power_labels = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power and n < len(power_labels) - 1:
        size /= power; n += 1
    return f"{size:.2f} {power_labels[n]}"

async def get_file_raw_link(message):
    return f"https://t.me/c/{str(message.chat.id).replace('-100', '')}/{message.id}"

def encode_link(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().strip("=")

def decode_link(encoded_text: str) -> str:
    padding = 4 - (len(encoded_text) % 4)
    encoded_text += "=" * padding
    return base64.urlsafe_b64decode(encoded_text).decode()

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'([0-9]+)', s)]
