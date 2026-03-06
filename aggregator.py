import os
import feedparser
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
    "https://www.artificialintelligence-news.com/feed/"
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

def process_feeds():
    print("--- Запуск с Cohere ---")
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
