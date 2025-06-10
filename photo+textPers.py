import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import telegram
from telegram.constants import ParseMode
import asyncio
import logging
import os
from PIL import Image, ImageDraw, ImageFont
import textwrap
import random
import json # Import json for handling AI response
import telebot # Import telebot for the AI integration, though we'll use requests directly

# --- Configure logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Telegram Settings ---
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN") # Your Dev.to bot token
TELEGRAM_CHANNEL_ID = os.getenv("CHANNEL_ID")

# --- AI Translation Bot Settings ---
AI_API_URL = "https://text.pollinations.ai/"
AI_API_KEY = "YOUR_API_KEY"  # **IMPORTANT: Replace with your actual Pollinations API Key**
SYSTEM_PROMPT = """
شما یک مترجم هستید که متن های یک پست را ترجمه می‌کنید. شما نباید اسمی از خودتان در ترجمه داشته باشید و در انتهای متن ترجمه شده بنویسید:
Powerd By @HidroPv
"""

# Directory to store background images
BACKGROUND_IMAGES_DIR = 'background_images'
os.makedirs(BACKGROUND_IMAGES_DIR, exist_ok=True)

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

async def get_full_post_content(url):
    """Fetch full content of a post including images"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Get main content
        main_content = soup.find('div', class_='crayons-article__main')
        if not main_content:
            return None, None

        # Extract text content (using .get_text() on common paragraph tags)
        # We'll refine this to get more readable text for translation
        paragraphs = main_content.find_all(['p', 'h1', 'h2', 'h3', 'ul', 'ol', 'li'])
        text_content_parts = [tag.get_text(strip=True) for tag in paragraphs if tag.get_text(strip=True)]
        text_content = "\n\n".join(text_content_parts)

        # Extract images (first image only for simplicity)
        image = main_content.find('img')
        image_url = image['src'] if image else None

        return text_content, image_url

    except Exception as e:
        logger.error(f"Error fetching full post content: {e}")
        return None, None

async def translate_text_with_ai(text_to_translate):
    """
    Sends text to the AI API for translation.
    This function mimics the 'get_ai_response' logic from your second script.
    """
    conversation = [{"role": "system", "content": SYSTEM_PROMPT}]
    conversation.append({"role": "user", "content": text_to_translate})

    payload = {
        "messages": conversation
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AI_API_KEY}"
    }

    try:
        logger.info("Sending text for translation to AI API...")
        response = requests.post(AI_API_URL, json=payload, headers=headers, timeout=60) # Increased timeout for AI response
        response.raise_for_status()

        if response.headers.get('Content-Type', '').startswith('application/json'):
            response_json = response.json()
            ai_message = response_json.get("choices")[0].get("message").get("content")
        else:
            ai_message = response.text

        logger.info("Received translation from AI API.")
        return ai_message
    except requests.exceptions.RequestException as e:
        logger.error(f"Error communicating with AI API: {e}")
        return "خطا در ارتباط با سرور ترجمه. لطفاً بعداً تلاش کنید."
    except (KeyError, IndexError, ValueError) as e:
        logger.error(f"Error processing AI API response: {e}")
        return "خطا در پردازش پاسخ سرور ترجمه."
    except Exception as e:
        logger.error(f"An unexpected error occurred during AI translation: {e}")
        return "خطای ناشناخته در ترجمه."


async def send_post_with_media_and_translation(title, url, original_text_content, image_url=None):
    """
    Sends the original image as a photo with title and link,
    then sends the translated text in a separate message.
    """
    try:
        # --- 1. Send the original image with title and link ---
        if image_url:
            try:
                # Download the image
                image_response = requests.get(image_url, stream=True, timeout=10)
                image_response.raise_for_status()
                original_image_path = "temp_original_post_image.jpg"
                with open(original_image_path, 'wb') as out_file:
                    for chunk in image_response.iter_content(chunk_size=8192):
                        out_file.write(chunk)
                logger.info(f"Downloaded original image to {original_image_path}")

                caption_for_image = f"**{title}**\n\n[مطالعه بیشتر]({url})"
                with open(original_image_path, 'rb') as photo:
                    await bot.send_photo(
                        chat_id=TELEGRAM_CHANNEL_ID,
                        photo=photo,
                        caption=caption_for_image,
                        parse_mode=ParseMode.MARKDOWN
                    )
                os.remove(original_image_path) # Clean up downloaded image
                logger.info(f"Successfully sent original image for '{title}'")

            except requests.exceptions.RequestException as e:
                logger.warning(f"Could not download or send original image from {image_url}: {e}")
                # If image fails, send just the caption text
                await bot.send_message(
                    chat_id=TELEGRAM_CHANNEL_ID,
                    text=f"**{title}**\n\n[مطالعه بیشتر]({url})",
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True # Prevent automatic preview if no image
                )
            except Exception as e:
                logger.error(f"Error sending original image or initial caption: {e}")
                # Fallback to just text if any image-related error occurs
                await bot.send_message(
                    chat_id=TELEGRAM_CHANNEL_ID,
                    text=f"**{title}**\n\n[مطالعه بیشتر]({url})",
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
        else:
            # If no image URL, send just the caption text initially
            logger.info(f"No image URL found for '{title}', sending text-only caption.")
            await bot.send_message(
                chat_id=TELEGRAM_CHANNEL_ID,
                text=f"**{title}**\n\n[مطالعه بیشتر]({url})",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )

        await asyncio.sleep(2) # Small delay between messages

        # --- 2. Translate the text content ---
        logger.info(f"Translating text content for '{title}'...")
        translated_text = await translate_text_with_ai(original_text_content)
        
        # --- 3. Send the translated text in a separate message ---
        if translated_text:
            await bot.send_message(
                chat_id=TELEGRAM_CHANNEL_ID,
                text=translated_text,
                parse_mode=ParseMode.MARKDOWN # Assuming AI provides markdown-compatible text
            )
            logger.info(f"Successfully sent translated text for '{title}'")
        else:
            logger.warning(f"No translated text received for '{title}'.")

        return True

    except Exception as e:
        logger.error(f"Error in send_post_with_media_and_translation: {e}")
        return False

async def process_devto_posts():
    """Main function to process and send posts"""
    logger.info("Checking for new posts...")

    url = "https://dev.to/latest"
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        now = datetime.now(timezone.utc)
        # Set threshold to check for posts published in the last 30 minutes
        time_threshold = now - timedelta(minutes=30) 

        found_new_post = False
        for article in soup.find_all('div', class_='crayons-story'):
            try:
                title_tag = article.find('h2', class_='crayons-story__title')
                if not title_tag:
                    continue

                link_tag = title_tag.find('a')
                if not link_tag:
                    continue

                title = link_tag.get_text(strip=True)
                relative_link = link_tag['href']
                post_url = f"https://dev.to{relative_link}" if not relative_link.startswith('http') else relative_link

                time_tag = article.find('time')
                if not time_tag or 'datetime' not in time_tag.attrs:
                    continue

                published_at = datetime.fromisoformat(time_tag['datetime'])
                
                # Compare aware datetimes
                if published_at < time_threshold:
                    logger.info(f"Skipping old post: '{title}' published at {published_at}")
                    continue

                logger.info(f"Found new post: '{title}' published at {published_at}")

                # Get full content
                text_content, image_url = await get_full_post_content(post_url)
                if not text_content:
                    logger.warning(f"Could not get full text content for '{title}'. Skipping.")
                    continue

                # Send to Telegram (original image + translated text)
                if await send_post_with_media_and_translation(title, post_url, text_content, image_url):
                    found_new_post = True
                    logger.info(f"Successfully processed and sent post: '{title}'")
                else:
                    logger.error(f"Failed to send post: '{title}' to Telegram.")
                
                await asyncio.sleep(10)  # Add a longer delay to avoid rate limiting for two messages

            except Exception as e:
                logger.error(f"Error processing article: {e}")
                continue
        
        if not found_new_post:
            logger.info("No new posts found within the last 30 minutes.")

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching dev.to posts: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")


async def main():
    """Main async function"""
    logger.info("Starting bot...")

    try:
        await process_devto_posts()  # اجرای وظیفه اصلی
    except Exception as e:
        logger.error(f"Error in execution: {e}")

if __name__ == "__main__":
    os.makedirs(BACKGROUND_IMAGES_DIR, exist_ok=True)

    try:
        asyncio.run(main())  # اجرا فقط یک‌بار (بدون حلقه بی‌نهایت)
    except KeyboardInterrupt:
        logger.info("Bot stopped manually by KeyboardInterrupt.")
    except Exception as e:
        logger.critical(f"Unhandled exception during bot startup: {e}")
