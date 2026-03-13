import streamlit as st
import os
from supabase import create_client, Client

# Настройка страницы
st.set_page_config(page_title="AI RSS Dashboard", page_icon="📰", layout="wide")

st.title("📰 AI RSS Dashboard")
st.markdown("Your smart news feed, sorted by relevance.")

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
    В зависимости от реализации RPC в БД, может принимать embedding для поиска
    или user_id для рекомендаций.
    """
    try:
        if search_query:
            response = supabase.rpc("match_articles", {
                "query": search_query,
                "match_threshold": 0.1,
                "match_count": 20
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
                    "match_count": 15
                }).execute()
                return response.data
            else:
                # Фолбэк, если профиль не найден или у него нет вектора
                st.warning("User interest vector not found. Showing latest news.")
                res = supabase.table("articles").select("*").order("id", desc=True).limit(20).execute()
                return res.data
    except Exception as e:
        st.warning(f"Hint: your `match_articles` RPC parameters might differ. Original error: {e}")
        # Фолбэк: если RPC не отработал, просто загружаем последние новости
        res = supabase.table("articles").select("*").order("id", desc=True).limit(20).execute()
        return res.data


def fetch_latest_articles():
    """
    Получает последние 30 статей напрямую из таблицы articles,
    отсортированных по дате публикации (по убыванию).
    Игнорирует вектор пользователя — чистый хронологический фид.
    """
    try:
        res = supabase.table("articles").select("*").order(
            "published_at", desc=True
        ).limit(30).execute()
        # Если published_at отсутствует или пуст, фолбэк на created_at
        if not res.data:
            res = supabase.table("articles").select("*").order(
                "created_at", desc=True
            ).limit(30).execute()
        return res.data
    except Exception:
        # Фолбэк на created_at если колонки published_at нет
        try:
            res = supabase.table("articles").select("*").order(
                "created_at", desc=True
            ).limit(30).execute()
            return res.data
        except Exception as e:
            st.error(f"Failed to load latest articles: {e}")
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


def render_article_card(article, show_interaction_button=True):
    """Рендерит карточку статьи. show_interaction_button=False для вкладки Latest News."""
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
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if show_interaction_button:
                if st.button("👍 Read / Relevant", key=f"btn_{article_id}"):
                    if article_id:
                        handle_interaction(article_id)
                    else:
                        st.error("Missing article ID")
        with col2:
            st.markdown(f"**[Read at source]({link})**")


# --- UI Дашборда ---

# Поле для семантического поиска
st.subheader("News Search")
query = st.text_input("Enter a topic for semantic search (leave empty for your feed):", "")

st.divider()

# Вкладки: For You / Latest News
tab_for_you, tab_latest = st.tabs(["🎯 For You", "🕐 Latest News"])

with tab_for_you:
    with st.spinner("Loading recommendations..."):
        articles = fetch_articles(query)
    
    if not articles:
        st.info("No recommendations available or search yielded no results.")
    else:
        for article in articles:
            render_article_card(article, show_interaction_button=True)

with tab_latest:
    with st.spinner("Loading latest news..."):
        latest = fetch_latest_articles()
    
    if not latest:
        st.info("No recent articles found.")
    else:
        for article in latest:
            render_article_card(article, show_interaction_button=False)
