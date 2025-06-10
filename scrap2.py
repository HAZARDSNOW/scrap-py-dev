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
import json

# --- Configure logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Telegram Settings ---
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN") # Your Dev.to bot token
TELEGRAM_CHANNEL_ID = os.getenv("CHANNEL_ID")

# Directory to store background images
BACKGROUND_IMAGES_DIR = 'background_images'
os.makedirs(BACKGROUND_IMAGES_DIR, exist_ok=True)

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

# --- AI Translation Settings ---
SYSTEM_PROMPT = """
شما یک مترجم هستید که متن های یک پست را ترجمه می‌کنید. شما نباید اسمی از خودتان در ترجمه داشته باشید و در انتهای متن ترجمه شده بنویسید:
Powerd By @HidroPv
"""

async def get_ai_translation(text):
    """Get translation from AI API"""
    try:
        url = "https://text.pollinations.ai/"
        payload = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"لطفا این متن را به فارسی روان ترجمه کن:\n{text}"}
            ]
        }
        headers = {"Content-Type": "application/json"}
        
        response = await asyncio.to_thread(requests.post, url, json=payload, headers=headers)
        response.raise_for_status()
        
        if response.headers.get('Content-Type', '').startswith('application/json'):
            response_json = response.json()
            return response_json.get("choices")[0].get("message").get("content")
        return response.text

    except Exception as e:
        logger.error(f"Error getting AI translation: {e}")
        return None

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

        # Extract text content
        text_content = main_content.get_text(separator='\n', strip=True)

        # Extract images (first image only for simplicity)
        image = main_content.find('img')
        image_url = image['src'] if image else None

        return text_content, image_url

    except Exception as e:
        logger.error(f"Error fetching full post content: {e}")
        return None, None

def create_image_with_text(text_content, background_image_path, title, is_translation=False):
    """
    Creates an image with the given text content overlaid on a background.
    """
    try:
        # Check if background image exists
        if not os.path.exists(background_image_path):
            logger.error(f"Background image not found: {background_image_path}")
            return None

        # Load background image
        try:
            base_image = Image.open(background_image_path).convert("RGBA")
        except Exception as e:
            logger.error(f"Error loading background image: {e}")
            return None

        draw = ImageDraw.Draw(base_image)

        # Image dimensions
        img_width, img_height = base_image.size

        # --- Text settings ---
        BASE_FONT_SIZE = 30
        TITLE_FONT_SIZE = 50
        TITLE_COLOR = (255, 255, 0, 255)  # Yellow for title
        CONTENT_COLOR = (173, 216, 230, 255) if not is_translation else (200, 230, 200, 255)  # Light blue for content, light green for translation

        # Use default font
        try:
            font = ImageFont.load_default(size=BASE_FONT_SIZE)
            title_font = ImageFont.load_default(size=TITLE_FONT_SIZE)
        except Exception as e:
            logger.error(f"Error loading default font: {e}")
            return None

        # Add a semi-transparent overlay
        overlay = Image.new('RGBA', base_image.size, (0, 0, 0, 150))
        base_image = Image.alpha_composite(base_image, overlay)
        draw = ImageDraw.Draw(base_image)

        # Padding for text
        padding_x = 70
        padding_y_top = 80
        padding_y_bottom = 50

        # Calculate usable width for text
        text_area_width = img_width - (2 * padding_x)

        # --- Draw the title ---
        y_cursor = padding_y_top

        # Wrap title text
        title_chars_per_line = int(text_area_width / (TITLE_FONT_SIZE * 0.6))
        title_lines = textwrap.wrap(title, width=title_chars_per_line)

        for line in title_lines:
            text_bbox = draw.textbbox((0, 0), line, font=title_font)
            line_width = text_bbox[2] - text_bbox[0]
            draw.text(((img_width - line_width) / 2, y_cursor), line, font=title_font, fill=TITLE_COLOR)
            y_cursor += TITLE_FONT_SIZE + 15

        y_cursor += 40

        # --- Draw the main text content ---
        chars_per_line = int(text_area_width / (BASE_FONT_SIZE * 0.5))
        wrapped_text = textwrap.fill(text_content, width=chars_per_line)
        lines = wrapped_text.split('\n')
        
        max_lines_height = img_height - y_cursor - padding_y_bottom
        max_lines = int(max_lines_height / (BASE_FONT_SIZE + 5))
        display_lines = lines[:max_lines]
        
        if len(lines) > max_lines:
            if display_lines:
                last_line_text = display_lines[-1]
                if draw.textlength(last_line_text + "...", font=font) < text_area_width:
                    display_lines[-1] = last_line_text + "..."
                else:
                    display_lines.append("...")

        for line in display_lines:
            draw.text((padding_x, y_cursor), line, font=font, fill=CONTENT_COLOR)
            y_cursor += BASE_FONT_SIZE + 5

        # Convert to RGB before saving as JPEG
        if base_image.mode == 'RGBA':
            base_image = base_image.convert('RGB')

        output_image_path = "temp_translation_image.jpg" if is_translation else "temp_post_image.jpg"
        base_image.save(output_image_path, quality=90, optimize=True)
        
        logger.info(f"Generated image saved to {output_image_path}")
        return output_image_path

    except Exception as e:
        logger.error(f"Error creating image with text: {e}")
        return None

async def send_post_with_translation(title, url, text_content):
    """Send post to Telegram with both original and translated images"""
    try:
        # Get list of background images
        background_images = [os.path.join(BACKGROUND_IMAGES_DIR, f) for f in os.listdir(BACKGROUND_IMAGES_DIR) 
                           if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        
        if not background_images:
            logger.error(f"No background images found in {BACKGROUND_IMAGES_DIR}")
            return False

        # Select a random background image
        selected_background_image = random.choice(background_images)
        logger.info(f"Using background image: {selected_background_image}")

        # Create the original image with text
        original_image_path = create_image_with_text(text_content, selected_background_image, title)
        if not original_image_path:
            return False

        # Get translation from AI
        translated_text = await get_ai_translation(text_content)
        if not translated_text:
            logger.error("Failed to get translation from AI")
            return False

        # Create the translated image with text
        translated_image_path = create_image_with_text(translated_text, selected_background_image, f"ترجمه: {title}", is_translation=True)
        if not translated_image_path:
            return False

        # Send original post to Telegram
        caption = f"**{title}**\n\n[مطالعه بیشتر]({url})"
        
        with open(original_image_path, 'rb') as photo:
            await bot.send_photo(
                chat_id=TELEGRAM_CHANNEL_ID,
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )

        # Send translated post to Telegram
        with open(translated_image_path, 'rb') as photo:
            await bot.send_photo(
                chat_id=TELEGRAM_CHANNEL_ID,
                photo=photo,
                caption=f"ترجمه فارسی پست:\n\n[مطالعه متن اصلی]({url})",
                parse_mode=ParseMode.MARKDOWN
            )

        # Clean up
        os.remove(original_image_path)
        os.remove(translated_image_path)
        logger.info(f"Successfully sent post '{title}' with translation to Telegram")
        return True

    except Exception as e:
        logger.error(f"Error sending post to Telegram: {e}")
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
                if published_at < time_threshold:
                    continue

                logger.info(f"Found new post: '{title}' published at {published_at}")

                # Get full content
                text_content, image_url = await get_full_post_content(post_url)
                if not text_content:
                    logger.warning(f"Could not get full text content for '{title}'. Skipping.")
                    continue

                # Send to Telegram with translation
                if await send_post_with_translation(title, post_url, text_content):
                    found_new_post = True
                    logger.info(f"Successfully processed and sent post: '{title}'")
                else:
                    logger.error(f"Failed to send post: '{title}' to Telegram.")
                
                await asyncio.sleep(5)  # Avoid rate limiting

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
    """
    Main async function.
    This version is designed to run ONCE and then exit.
    The scheduling is handled by an external tool like cron or GitHub Actions.
    """
    logger.info("Starting a single run to check for new posts...")
    await process_devto_posts()
    logger.info("Single run finished successfully.")

if __name__ == "__main__":
    try:
        # حالا تابع main فقط یک بار اجرا شده و به پایان می‌رسد
        asyncio.run(main())
    except Exception as e:
        # اگر در حین اجرا خطایی رخ دهد، آن را لاگ کرده و با کد خطا از اسکریپت خارج می‌شویم
        # این کار باعث می‌شود اجرای Action در گیت‌هاب به عنوان "Failed" ثبت شود
        logger.critical(f"Script failed with an unhandled exception: {e}")
        sys.exit(1)
