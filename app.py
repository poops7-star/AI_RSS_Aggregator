import streamlit as st
import os
from supabase import create_client, Client

# Настройка страницы
st.set_page_config(page_title="AI RSS Дашборд", page_icon="📰", layout="wide")

st.title("📰 AI RSS Дашборд")
st.markdown("Ваша умная лента новостей, отсортированная по релевантности.")

# Инициализация клиентов
@st.cache_resource
def init_clients():
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY", "")
    
    if not supabase_url or not supabase_key:
        st.error("⚠️ Не заданы переменные окружения SUPABASE_URL и SUPABASE_KEY. Настройте их для работы с БД.")
        st.stop()
        
    client: Client = create_client(supabase_url, supabase_key)
    
    return client

supabase = init_clients()

# Условный ID пользователя (можно заменить на реальную систему авторизации)
USER_ID = os.environ.get("USER_ID", "default_user_123")

def fetch_articles(search_query=""):
    """
    Получает статьи с использованием RPC match_articles.
    В зависимости от реализации RPC в БД, может принимать embedding для поиска
    или user_id для рекомендаций.
    """
    try:
        if search_query:
            # Note: semantic search from the frontend requires passing the query string directly
            # to the RPC if it supports it, or doing the embedding generation elsewhere.
            # Assuming the RPC might handle the query directly or we fallback to user recommendations
            response = supabase.rpc("match_articles", {
                "query": search_query, # changed to query instead of embedding
                "match_threshold": 0.1,
                "match_count": 20
            }).execute()
            return response.data
        else:
            # Получение персонализированной ленты по пользователю
            # Если RPC не принимает user_id, вы можете изменить ключи здесь.
            response = supabase.rpc("match_articles", {
                "user_id": USER_ID
            }).execute()
            return response.data
            
    except Exception as e:
        st.warning(f"Подсказка: возможно, параметры вашей RPC `match_articles` отличаются. Оригинальная ошибка: {e}")
        # Фолбэк: если RPC не отработал, просто загружаем последние новости
        res = supabase.table("articles").select("*").order("id", desc=True).limit(20).execute()
        return res.data

def handle_interaction(article_id):
    """
    Вызывает RPC handle_article_interaction для сохранения взаимодействия пользователя.
    """
    try:
        response = supabase.rpc("handle_article_interaction", {
            "p_user_id": USER_ID,
            "p_article_id": article_id,
            "p_interaction_type": "interested"
        }).execute()
        st.toast("✅ Отметка сохранена! Ваш профиль обновляется.")
    except Exception as e:
        st.error(f"Ошибка сохранения взаимодействия: {e}")

# --- UI Дашборда ---

# Поле для семантического поиска (опционально поверх рекомендационной ленты)
st.subheader("Поиск по новостям")
query = st.text_input("Введите тему для семантического поиска (оставьте пустым для вашей ленты):", "")

st.divider()

with st.spinner("Загрузка новостей..."):
    articles = fetch_articles(query)

if not articles:
    st.info("Нет доступных новостей или поиск не дал результатов.")
else:
    # Рендер ленты
    for article in articles:
        # Для карточек используем container(border=True) 
        with st.container(border=True):
            title = article.get("title", "Без заголовка")
            summary = article.get("summary", "")
            link = article.get("link", "#")
            article_id = article.get("id", None)
            
            st.subheader(title)
            if summary:
                st.write(summary)
            
            col1, col2 = st.columns([1, 4])
            with col1:
                # Кнопка интереса/прочтения
                if st.button("👍 Прочитано / Интересно", key=f"btn_{article_id}"):
                    if article_id:
                        handle_interaction(article_id)
                    else:
                        st.error("Отсутствует ID статьи")
            with col2:
                st.markdown(f"**[Читать в источнике]({link})**")
