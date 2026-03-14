import os
import feedparser
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
import cohere
import google.generativeai as genai
from supabase import create_client, Client

# Инициализация
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

co = cohere.Client(os.environ.get("COHERE_API_KEY"))

# Инициализация Gemini Flash
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.ynet.co.il/Integration/StoryRss1854.xml",
    "http://www.habrahabr.ru/rss",
    "https://news.google.com/rss/search?q=%D0%A2%D0%B5%D1%85%D0%BD%D0%BE%D0%BB%D0%BE%D0%B3%D0%B8%D0%B8&hl=ru&gl=US&ceid=US:ru",
    "https://news.google.com/rss/search?q=%D0%98%D1%81%D0%BA%D1%83%D1%81%D1%81%D1%82%D0%B2%D0%B5%D0%BD%D0%BD%D1%8B%D0%B9+%D0%B8%D0%BD%D1%82%D0%B5%D0%BB%D0%BB%D0%B5%D0%BA%D1%82+OR+%D0%9D%D0%B5%D0%B9%D1%80%D0%BE%D1%81%D0%B5%D1%82%D0%B8&hl=ru&gl=US&ceid=US:ru",
    "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNREpxYW5RU0FuSjFHZ0pTVlNnQVAB?hl=ru&gl=RU&ceid=RU:ru.",
    "https://news.google.com/rss/topics/CAAqKggKIiRDQkFTRlFvSUwyMHZNREpxYW5RU0JXVnVMVWRDR2dKSlRDZ0FQAQ?hl=en-IL&gl=IL&ceid=IL%3Aen",
    "http://www.kinopoisk.ru/news.rss"
]

def clean_html(raw_html):
    if not raw_html: return ""
    return BeautifulSoup(raw_html, "html.parser").get_text(separator=" ", strip=True)

def get_embedding(text):
    response = co.embed(
        texts=[text],
        model='embed-english-v3.0',
        input_type='search_document'
    )
    return response.embeddings[0]

def get_recent_user_interests():
    """Fetches the 5 most recently saved articles to build a user interest profile."""
    try:
        res = supabase.table("saved_articles").select(
            "created_at, articles(title, summary)"
        ).order("created_at", desc=True).limit(5).execute()

        if not res.data:
            return None

        lines = []
        for i, row in enumerate(res.data, 1):
            article = row.get("articles")
            if article:
                title = article.get("title", "Untitled")
                summary = article.get("summary", "No summary")
                lines.append(f"{i}. Title: {title} | Summary: {summary}")

        if not lines:
            return None

        return "\n".join(lines)

    except Exception as e:
        print(f"Error fetching user interests: {e}")
        return None

def is_relevant(title, summary):
    """Uses Gemini Flash to filter articles based on user interests."""
    interests_block = get_recent_user_interests()

    if interests_block:
        system_prompt = (
            "You are an AI content filter. The user is generally interested in AI, "
            "software QA, and tech. Here are the topics they recently saved:\n\n"
            f"{interests_block}\n\n"
            "Prioritize keeping new articles that align with these specific interests, "
            "while still maintaining a high quality standard."
        )
    else:
        system_prompt = (
            "You are an AI content filter. The user is interested in AI, "
            "software QA, and tech. Filter out irrelevant or low-quality articles."
        )

    user_prompt = (
        f"Should the following article be kept in the user's feed?\n\n"
        f"Title: {title}\nSummary: {summary}\n\n"
        f"Respond with only YES or NO."
    )

    try:
        response = gemini_model.generate_content(
            [{"role": "user", "parts": [f"{system_prompt}\n\n{user_prompt}"]}]
        )
        answer = response.text.strip().upper()
        print(f"  Gemini verdict: {answer}")
        return "YES" in answer
    except Exception as e:
        print(f"  Gemini error (defaulting to keep): {e}")
        return True  # On error, keep the article

def cleanup_old_articles():
    """Удаляет статьи, опубликованные более 4 дней назад."""
    try:
        print("--- Очистка старых данных ---")
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
        response = supabase.table('articles').delete().lt('created_at', cutoff_date).execute()
        deleted_count = len(response.data) if response.data else 0
        print(f"Удалено старых статей (старше 4 дней): {deleted_count}")
    except Exception as e:
        print(f"Ошибка при удалении старых данных: {e}")

def process_feeds():
    print("--- Запуск с Cohere + Gemini Flash фильтрацией ---")

    # 1. Очистка старых статей перед сбором новых
    cleanup_old_articles()
    for url in FEEDS:
        print(f"Парсинг: {url}")
        feed = feedparser.parse(url)
        for entry in feed.entries[:3]:
            link = entry.get('link', '')
            title = entry.get('title', '')

            # Проверка дубликатов
            existing = supabase.table('articles').select('id').eq('link', link).execute()
            if len(existing.data) > 0: continue

            print(f"Новая статья: {title}")
            summary = clean_html(entry.get('summary', '') or entry.get('description', ''))

            # Gemini Flash relevance filter
            if not is_relevant(title, summary):
                print(f"  Отфильтровано Gemini: {title}")
                continue

            try:
                embedding = get_embedding(f"{title} {summary}")
                data = {"title": title, "link": link, "summary": summary, "embedding": embedding}
                supabase.table('articles').insert(data).execute()
                print("Успешно!")
            except Exception as e:
                print(f"Ошибка: {e}")

if __name__ == "__main__":
    process_feeds()
