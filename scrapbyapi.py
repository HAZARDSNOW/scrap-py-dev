import requests
import json
import os
from datetime import datetime, timedelta
from urllib.parse import urljoin
from datetime import datetime, timedelta, timezone


# تنظیمات اولیه
DEVTO_API = "https://dev.to/api/articles?state=fresh&per_page=10" 
COMMENTS_API = "https://dev.to/api/articles/{}/comments" 
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHANNEL_ID")
POLLINATIONS_TEXT_API = "https://text.pollinations.ai/openai"  
POLLINATIONS_IMAGE_API = "https://image.pollinations.ai/prompt/" 

def generate_summary(article_text):
    try:
        payload = {
            "model": "openai",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Summarize the provided text into 3-5 lines in Persian, keeping the tone engaging and concise."
                },
                {
                    "role": "user",
                    "content": f"Summarize this text in Persian (3-5 lines): {article_text}"
                }
            ],
            "max_tokens": 150
        }
        response = requests.post(POLLINATIONS_TEXT_API, headers={"Content-Type": "application/json"}, json=payload)
        response.raise_for_status()
        summary = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if summary:
            return summary
        return "خلاصه‌ای موقت: این مقاله درباره موضوعات جذاب برنامه‌نویسی صحبت می‌کنه!"
    except Exception as e:
        print(f"خطا در خلاصه‌سازی: {e}")
        return "خلاصه‌ای موقت: این مقاله درباره موضوعات جذاب برنامه‌نویسی صحبت می‌کنه!"

def get_default_image(title):
    try:
        prompt = f"{title}, programming concept, vibrant digital art, clean design"
        url = f"{POLLINATIONS_IMAGE_API}{prompt}?model=flux&width=1024&height=1024&nologo=true"
        response = requests.get(url)
        response.raise_for_status()
        return response.url  
    except Exception as e:
        print(f"خطا در تولید تصویر: {e}")
        return None

def get_new_articles():
    try:
        response = requests.get(DEVTO_API)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"خطا در دریافت مقالات: {e}")
        return []

def get_top_comments(article_id):
    try:
        response = requests.get(COMMENTS_API.format(article_id))
        response.raise_for_status()
        comments = response.json()
        sorted_comments = sorted(
            comments,
            key=lambda x: x.get("positive_reactions_count", 0),
            reverse=True
        )
        return sorted_comments[:5]  
    except Exception as e:
        print(f"خطا در دریافت کامنت‌ها: {e}")
        return []

def send_to_telegram(article):
    title = article["title"]
    description = generate_summary(article.get("description", ""))
    url = article["url"]
    cover_image = article.get("cover_image", "")
    tags = article.get("tags", [])
    article_id = article["id"]

    hashtags = " ".join([f"#{tag}" for tag in tags])
    
    message = f"<b>{title}</b>\n\n{description}\n\n{hashtags}\n📖 <a href='{url}'>خواندن مقاله کامل</a>"

    if cover_image:
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": cover_image,
            "caption": message,
            "parse_mode": "HTML"
        }
    else:
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        default_image = get_default_image(title)
        if default_image:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "photo": default_image,
                "caption": message,
                "parse_mode": "HTML"
            }
        else:
            telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            }

    response = requests.post(telegram_url, json=payload)
    if response.status_code != 200:
        print(f"خطا در ارسال پست به تلگرام: {response.text}")
        return None
    
    message_id = response.json().get("result", {}).get("message_id")

    top_comments = get_top_comments(article_id)
    if top_comments:
        comments_message = "<b>💬 ۵ کامنت برتر:</b>\n\n"
        for comment in top_comments:
            username = comment.get("user", {}).get("username", "ناشناس")
            comment_body = comment.get("body_html", "")[:200]  # محدود به 200 کاراکتر
            reactions = comment.get("positive_reactions_count", 0)
            comments_message += f"👤 <b>{username}</b>: {comment_body}\n❤️ {reactions} لایک\n\n"
        
        comments_message += f"📜 <a href='{urljoin(url, '#comments')}'>مشاهده همه کامنت‌ها</a>"
        
        comments_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        comments_payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": comments_message,
            "parse_mode": "HTML",
            "reply_to_message_id": message_id
        }
        response = requests.post(comments_url, json=comments_payload)
        if response.status_code == 200:
            print(f"کامنت‌های مقاله '{title}' ارسال شد.")
        else:
            print(f"خطا در ارسال کامنت‌ها: {response.text}")

    print(f"مقاله '{title}' با موفقیت ارسال شد.")

 تابع اصلی
def main():
  
    time_threshold = datetime.now(timezone.utc) - timedelta(minutes=31)
    articles = get_new_articles()

    for article in articles:
        try:
            published_at = datetime.fromisoformat(article["published_at"].replace("Z", "+00:00"))
            if published_at > time_threshold:
                send_to_telegram(article)
        except KeyError as e:
            print(f"خطا در پردازش مقاله: {e}")
            continue

if __name__ == "__main__":
    main()
