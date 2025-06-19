import aiohttp
import asyncio
import logging
from database.db import get_user

logger = logging.getLogger(__name__)

async def get_shortlink(link_to_shorten, user_id):
    """
    Shortens the provided link using the user's settings.
    Now includes a retry mechanism for better reliability.
    """
    user = await get_user(user_id)
    if not user or not user.get('shortener_enabled') or not user.get('shortener_url'):
        return link_to_shorten

    URL = user['shortener_url'].strip()
    API = user['shortener_api'].strip()

    # Retry logic: Attempt the API call up to 3 times
    for attempt in range(3):
        try:
            url = f'https://{URL}/api'
            params = {'api': API, 'url': link_to_shorten}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, raise_for_status=True, ssl=False, timeout=10) as response:
                    data = await response.json(content_type=None)
                    if data.get("status") == "success" and data.get("shortenedUrl"):
                        return data["shortenedUrl"]  # Success, return the link and exit the loop
                    else:
                        logger.error(f"Shortener API error (Attempt {attempt + 1}/3): {data.get('message', 'Unknown error')}")
        except Exception as e:
            logger.error(f"HTTP Error during shortening (Attempt {attempt + 1}/3): {e}")
        
        # If not the last attempt, wait for 1 second before retrying
        if attempt < 2:
            await asyncio.sleep(1)

    # If all attempts fail, log it and return the original link as a fallback
    logger.error(f"All shortener attempts failed for user {user_id}. Returning original link.")
    return link_to_shorten
