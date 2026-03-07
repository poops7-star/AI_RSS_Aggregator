import os
import feedparser
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
import cohere
from supabase import create_client, Client

# Инициализация
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

co = cohere.Client(os.environ.get("COHERE_API_KEY"))

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
    # Модель embed-multilingual-v3.0 выдает 1024 измерения по умолчанию, 
    # Но мы заставим её дать нужный нам формат или адаптируем базу.
    # Для начала попробуем стандартную английскую v3 (она дает 1024)
    response = co.embed(
        texts=[text],
        model='embed-english-v3.0',
        input_type='search_document'
    )
    return response.embeddings[0]

def cleanup_old_articles():
    """Удаляет статьи, опубликованные более 4 дней назад."""
    try:
        print("--- Очистка старых данных ---")
        # Вычисляем дату(timestamp), которая была 4 дня назад
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
        
        # Запрашиваем удаление всех записей, где created_at < cutoff_date
        # Предполагается, что в таблице 'articles' есть колонка с датой создания, например 'created_at'
        response = supabase.table('articles').delete().lt('created_at', cutoff_date).execute()
        
        deleted_count = len(response.data) if response.data else 0
        print(f"Удалено старых статей (старше 4 дней): {deleted_count}")
        
    except Exception as e:
        print(f"Ошибка при удалении старых данных: {e}")

def process_feeds():
    print("--- Запуск с Cohere ---")
    
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
            
            try:
                # ВАЖНО: Модель v3 выдает 1024 числа. 
                # Нам нужно либо изменить таблицу, либо обрезать вектор.
                # Давайте сделаем по-умному: просто обновим таблицу в Supabase под 1024.
                embedding = get_embedding(f"{title} {summary}")
                
                data = {"title": title, "link": link, "summary": summary, "embedding": embedding}
                supabase.table('articles').insert(data).execute()
                print("Успешно!")
            except Exception as e:
                print(f"Ошибка: {e}")

if __name__ == "__main__":
    process_feeds()
