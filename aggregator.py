import os
import feedparser
from bs4 import BeautifulSoup
import google.generativeai as genai
from supabase import create_client, Client

# Инициализация клиентов через скрытые переменные окружения
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Целевые источники (можно менять и дополнять)
FEEDS = [
    "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/medical-devices/rss.xml",
    "https://www.artificialintelligence-news.com/feed/",
    "https://www.softwaretestinghelp.com/feed/"
]

def clean_html(raw_html):
    if not raw_html:
        return ""
    return BeautifulSoup(raw_html, "html.parser").get_text(separator=" ", strip=True)

def get_embedding(text):
    # Используем максимально прямое имя модели без лишних префиксов
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_document"
    )
    return result['embedding']

def process_feeds():
    for url in FEEDS:
        print(f"Парсинг ленты: {url}")
        feed = feedparser.parse(url)
        
        for entry in feed.entries[:5]:  # Берем 5 последних новостей из каждой ленты
            link = entry.get('link', '')
            title = entry.get('title', '')
            summary_raw = entry.get('summary', '') or entry.get('description', '')
            summary = clean_html(summary_raw)
            
            if not link or not title:
                continue
                
            # Шаг 1: Проверка дубликатов (экономия токенов)
            existing = supabase.table('articles').select('id').eq('link', link).execute()
            if len(existing.data) > 0:
                print(f"Пропуск (уже в базе): {title}")
                continue
                
            print(f"Обработка новой статьи: {title}")
            
            # Шаг 2: Векторизация смысла (Заголовок + Краткое содержание)
            text_for_ai = f"Title: {title}. Summary: {summary}"
            try:
                embedding = get_embedding(text_for_ai)
            except Exception as e:
                print(f"Ошибка API Gemini: {e}")
                continue
                
            # Шаг 3: Запись в базу данных
            data = {
                "title": title,
                "link": link,
                "summary": summary,
                "embedding": embedding
            }
            try:
                supabase.table('articles').insert(data).execute()
                print("Успешно сохранено.")
            except Exception as e:
                print(f"Ошибка записи Supabase: {e}")

if __name__ == "__main__":
    process_feeds()
