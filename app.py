import streamlit as st
import os
from supabase import create_client, Client

# Настройка страницы
st.set_page_config(page_title="AI RSS Dashboard", page_icon="📰", layout="wide")

st.title("📰 AI RSS Dashboard")
st.markdown("Your smart news feed, sorted by relevance.")

# --- Session State: Pagination ---
if "feed_limit" not in st.session_state:
    st.session_state.feed_limit = 15

# Инициализация клиентов
@st.cache_resource
def init_clients():
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY", "")
    
    if not supabase_url or not supabase_key:
        st.error("⚠️ SUPABASE_URL and SUPABASE_KEY environment variables are not set. Configure them to connect to the DB.")
        st.stop()
        
    client: Client = create_client(supabase_url, supabase_key)
    
    return client

supabase = init_clients()

# --- Sidebar: Reset Profile ---
with st.sidebar:
    st.header("⚙️ Settings")
    if st.button("🔄 Reset Profile / Clear Interests"):
        user_id = st.session_state.get("user_id")
        if user_id:
            try:
                zero_vector = [0.0] * 1024
                supabase.table("user_profile").update(
                    {"interest_embedding": zero_vector}
                ).eq("id", user_id).execute()
                st.toast("✅ Profile reset! Your recommendations will now be neutral.")
            except Exception as e:
                st.error(f"Failed to reset profile: {e}")
        else:
            st.warning("User profile not loaded yet. Please wait for the feed to load first.")


def fetch_articles(search_query=""):
    """
    Получает статьи с использованием RPC match_articles.
    Uses dynamic st.session_state.feed_limit for pagination.
    """
    limit = st.session_state.feed_limit
    try:
        if search_query:
            response = supabase.rpc("match_articles", {
                "query": search_query,
                "match_threshold": 0.1,
                "match_count": limit
            }).execute()
            return response.data
        else:
            # Получение interest_embedding пользователя (первого попавшегося для MVP)
            user_profile = supabase.table("user_profile").select("id, interest_embedding").limit(1).execute()
            
            user_vector = None
            if user_profile.data:
                st.session_state.user_id = user_profile.data[0].get("id")
                user_vector = user_profile.data[0].get("interest_embedding")
            else:
                # Холодный старт: таблица пуста. Генерируем вектор нулей размерностью 1024
                zero_vector = [0.0] * 1024
                try:
                    new_profile = supabase.table("user_profile").insert({"interest_embedding": zero_vector}).execute()
                    if new_profile.data:
                        st.session_state.user_id = new_profile.data[0].get("id")
                        user_vector = new_profile.data[0].get("interest_embedding")
                        st.success("Basic user profile created!")
                except Exception as e:
                    st.error(f"Failed to initialize profile: {e}")

            if user_vector:
                # Получение персонализированной ленты по вектору интересов пользователя
                response = supabase.rpc("match_articles", {
                    "query_embedding": user_vector,
                    "match_threshold": 0.05,
                    "match_count": limit
                }).execute()
                return response.data
            else:
                # Фолбэк, если профиль не найден или у него нет вектора
                st.warning("User interest vector not found. Showing latest news.")
                res = supabase.table("articles").select("*").order("id", desc=True).limit(limit).execute()
                return res.data
    except Exception as e:
        st.warning(f"Hint: your `match_articles` RPC parameters might differ. Original error: {e}")
        res = supabase.table("articles").select("*").order("id", desc=True).limit(limit).execute()
        return res.data


def fetch_latest_articles():
    """
    Получает последние статьи напрямую из таблицы articles,
    отсортированных по дате публикации (по убыванию).
    Uses dynamic st.session_state.feed_limit for pagination.
    """
    limit = st.session_state.feed_limit
    try:
        res = supabase.table("articles").select("*").order(
            "published_at", desc=True
        ).limit(limit).execute()
        if not res.data:
            res = supabase.table("articles").select("*").order(
                "created_at", desc=True
            ).limit(limit).execute()
        return res.data
    except Exception:
        try:
            res = supabase.table("articles").select("*").order(
                "created_at", desc=True
            ).limit(limit).execute()
            return res.data
        except Exception as e:
            st.error(f"Failed to load latest articles: {e}")
            return []


def fetch_saved_articles():
    """
    Получает сохранённые пользователем статьи из таблицы saved_articles,
    с join на таблицу articles для получения полных данных.
    """
    user_id = st.session_state.get("user_id")
    if not user_id:
        return []
    try:
        res = supabase.table("saved_articles").select(
            "article_id, articles(*)"
        ).eq("user_id", user_id).execute()
        # Извлекаем вложенные данные articles из результата join
        articles = []
        if res.data:
            for row in res.data:
                article_data = row.get("articles")
                if article_data:
                    articles.append(article_data)
        return articles
    except Exception as e:
        st.error(f"Failed to load saved articles: {e}")
        return []


def handle_interaction(article_id):
    """
    Вызывает RPC handle_article_interaction для сохранения взаимодействия пользователя.
    """
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.error("Error: User ID not found. Please wait for the feed to load.")
        return
        
    try:
        response = supabase.rpc("handle_article_interaction", {
            "p_user_id": user_id,
            "p_article_id": article_id,
            "p_interaction_type": "interested"
        }).execute()
        st.toast("✅ Mark saved! Your profile is updating.")
    except Exception as e:
        st.error(f"Error saving interaction: {e}")


def save_article(article_id):
    """
    Сохраняет статью в закладки пользователя (таблица saved_articles).
    Игнорирует ошибку уникального ограничения при повторном сохранении.
    """
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.error("Error: User ID not found. Please wait for the feed to load.")
        return

    try:
        supabase.table("saved_articles").insert({
            "user_id": user_id,
            "article_id": article_id
        }).execute()
        st.toast("💾 Article saved to bookmarks!")
    except Exception as e:
        error_msg = str(e)
        if "duplicate" in error_msg.lower() or "unique" in error_msg.lower() or "23505" in error_msg:
            st.toast("📌 Article already saved.")
        else:
            st.error(f"Error saving article: {e}")


def render_article_card(article, show_interaction_button=True, show_save_button=True, card_prefix=""):
    """
    Рендерит карточку статьи.
    show_interaction_button: показывать кнопку 👍 (For You)
    show_save_button: показывать кнопку 💾 (For You + Latest News, но не Saved)
    card_prefix: префикс для уникальности ключей кнопок между вкладками
    """
    with st.container(border=True):
        title = article.get("title", "Untitled")
        summary = article.get("summary", "")
        link = article.get("link", "#")
        article_id = article.get("id", None)
        published = article.get("published_at") or article.get("created_at", "")

        st.subheader(title)
        if published:
            st.caption(f"📅 {published}")
        if summary:
            st.write(summary)
        
        # Определяем колонки в зависимости от видимых кнопок
        if show_interaction_button and show_save_button:
            col1, col2, col3 = st.columns([1, 1, 3])
        elif show_interaction_button or show_save_button:
            col1, col3 = st.columns([1, 4])
            col2 = None
        else:
            col1, col3 = None, None

        if show_interaction_button and col1:
            with col1:
                if st.button("👍 Read / Relevant", key=f"{card_prefix}btn_{article_id}"):
                    if article_id:
                        handle_interaction(article_id)
                    else:
                        st.error("Missing article ID")
        
        if show_save_button:
            save_col = col2 if col2 else col1
            if save_col:
                with save_col:
                    if st.button("💾 Save", key=f"{card_prefix}save_{article_id}"):
                        if article_id:
                            save_article(article_id)
                        else:
                            st.error("Missing article ID")
        
        if col3:
            with col3:
                st.markdown(f"**[Read at source]({link})**")
        elif not show_interaction_button and not show_save_button:
            st.markdown(f"**[Read at source]({link})**")


# --- UI Дашборда ---

# Поле для семантического поиска
st.subheader("News Search")
query = st.text_input("Enter a topic for semantic search (leave empty for your feed):", "")

st.divider()

# Вкладки: For You / Latest News / Saved
tab_for_you, tab_latest, tab_saved = st.tabs(["🎯 For You", "🕐 Latest News", "📌 Saved"])

with tab_for_you:
    with st.spinner("Loading recommendations..."):
        articles = fetch_articles(query)
    
    if not articles:
        st.info("No recommendations available or search yielded no results.")
    else:
        for article in articles:
            render_article_card(article, show_interaction_button=True, show_save_button=True, card_prefix="fy_")
        
        # Load More button at the bottom of the feed
        if st.button("🔄 Load More", key="load_more_for_you"):
            st.session_state.feed_limit += 15
            st.rerun()

with tab_latest:
    with st.spinner("Loading latest news..."):
        latest = fetch_latest_articles()
    
    if not latest:
        st.info("No recent articles found.")
    else:
        for article in latest:
            render_article_card(article, show_interaction_button=False, show_save_button=True, card_prefix="lt_")
        
        # Load More button at the bottom of the feed
        if st.button("🔄 Load More", key="load_more_latest"):
            st.session_state.feed_limit += 15
            st.rerun()

with tab_saved:
    with st.spinner("Loading saved articles..."):
        saved = fetch_saved_articles()
    
    if not saved:
        st.info("No saved articles yet. Use the 💾 Save button to bookmark articles.")
    else:
        for article in saved:
            render_article_card(article, show_interaction_button=False, show_save_button=False, card_prefix="sv_")
