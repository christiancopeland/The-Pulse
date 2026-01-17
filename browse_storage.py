#!/usr/bin/env python3
"""
Simple Streamlit dashboard to browse collected news items.

Run with: streamlit run browse_storage.py
"""
import streamlit as st
import os
from datetime import datetime
from pathlib import Path

# Load env
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

# Database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://sna:sna_password@localhost/research_platform"
)

# Convert to sync URL for simplicity
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")

import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Create sync engine (simpler for Streamlit)
engine = create_engine(SYNC_DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)


def get_stats():
    """Get database statistics."""
    with Session() as db:
        total = db.execute(text("SELECT COUNT(*) FROM news_items")).scalar()

        by_source = db.execute(text("""
            SELECT source_type, COUNT(*) as cnt
            FROM news_items
            GROUP BY source_type
            ORDER BY cnt DESC
        """)).fetchall()

        by_category = db.execute(text("""
            SELECT cat, COUNT(*) as cnt
            FROM news_items, jsonb_array_elements_text(categories) AS cat
            GROUP BY cat
            ORDER BY cnt DESC
            LIMIT 20
        """)).fetchall()

        oldest = db.execute(text("SELECT MIN(collected_at) FROM news_items")).scalar()
        newest = db.execute(text("SELECT MAX(collected_at) FROM news_items")).scalar()

        return {
            'total': total,
            'by_source': {r[0]: r[1] for r in by_source},
            'by_category': {r[0]: r[1] for r in by_category},
            'oldest': oldest,
            'newest': newest,
        }


def get_items(source_type=None, category=None, search=None, limit=100, offset=0):
    """Get news items with optional filters."""
    with Session() as db:
        query = """
            SELECT id, source_type, source_name, title, summary, url,
                   published_at, collected_at, categories, relevance_score, processed
            FROM news_items
            WHERE 1=1
        """
        params = {}

        if source_type and source_type != "All":
            query += " AND source_type = :source_type"
            params['source_type'] = source_type

        if category and category != "All":
            query += " AND categories @> CAST(:category AS jsonb)"
            params['category'] = f'["{category}"]'

        if search:
            query += " AND title ILIKE :search"
            params['search'] = f'%{search}%'

        query += " ORDER BY collected_at DESC LIMIT :limit OFFSET :offset"
        params['limit'] = limit
        params['offset'] = offset

        result = db.execute(text(query), params)
        return result.fetchall()


def get_item_detail(item_id):
    """Get full item details."""
    with Session() as db:
        result = db.execute(
            text("SELECT * FROM news_items WHERE id = :id"),
            {'id': item_id}
        )
        return result.fetchone()


def get_collection_runs(limit=20):
    """Get recent collection runs."""
    with Session() as db:
        result = db.execute(text("""
            SELECT id, collector_type, collector_name, started_at, completed_at,
                   status, items_collected, items_new, items_duplicate, error_message
            FROM collection_runs
            ORDER BY started_at DESC
            LIMIT :limit
        """), {'limit': limit})
        return result.fetchall()


# Page config
st.set_page_config(
    page_title="The Pulse - Storage Browser",
    page_icon="📰",
    layout="wide"
)

st.title("📰 The Pulse - Storage Browser")

# Sidebar filters
st.sidebar.header("Filters")

# Get stats
try:
    stats = get_stats()

    # Source filter
    sources = ["All"] + list(stats['by_source'].keys())
    selected_source = st.sidebar.selectbox("Source Type", sources)

    # Category filter
    categories = ["All"] + list(stats['by_category'].keys())
    selected_category = st.sidebar.selectbox("Category", categories)

    # Search
    search_query = st.sidebar.text_input("Search titles")

    # Items per page
    per_page = st.sidebar.slider("Items per page", 10, 100, 25)

    # Stats display
    st.sidebar.markdown("---")
    st.sidebar.header("Statistics")
    st.sidebar.metric("Total Items", f"{stats['total']:,}")

    if stats['oldest'] and stats['newest']:
        st.sidebar.text(f"From: {stats['oldest'].strftime('%Y-%m-%d')}")
        st.sidebar.text(f"To: {stats['newest'].strftime('%Y-%m-%d')}")

    st.sidebar.markdown("**By Source:**")
    for src, count in list(stats['by_source'].items())[:8]:
        st.sidebar.text(f"  {src}: {count}")

except Exception as e:
    st.error(f"Database connection error: {e}")
    st.info("Make sure PostgreSQL is running: `sudo systemctl start postgresql`")
    st.stop()

# Main content tabs
tab1, tab2, tab3 = st.tabs(["📋 Browse Items", "📊 Collection Runs", "🔍 Item Detail"])

with tab1:
    # Pagination
    if 'page' not in st.session_state:
        st.session_state.page = 0

    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("⬅️ Previous") and st.session_state.page > 0:
            st.session_state.page -= 1
    with col2:
        st.write(f"Page {st.session_state.page + 1}")
    with col3:
        if st.button("Next ➡️"):
            st.session_state.page += 1

    # Get items
    offset = st.session_state.page * per_page
    items = get_items(
        source_type=selected_source,
        category=selected_category,
        search=search_query if search_query else None,
        limit=per_page,
        offset=offset
    )

    if not items:
        st.info("No items found with current filters.")
    else:
        for item in items:
            item_id, source_type, source_name, title, summary, url, published_at, collected_at, categories, relevance_score, processed = item

            with st.expander(f"**{title[:100]}**" if title else "No title"):
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.markdown(f"**Source:** {source_name} ({source_type})")
                    st.markdown(f"**Categories:** {', '.join(categories or [])}")
                    if published_at:
                        st.markdown(f"**Published:** {published_at.strftime('%Y-%m-%d %H:%M')}")
                    if collected_at:
                        st.markdown(f"**Collected:** {collected_at.strftime('%Y-%m-%d %H:%M')}")

                    if summary:
                        st.markdown("**Summary:**")
                        st.write(summary[:500] + "..." if len(summary or '') > 500 else summary)

                    if url:
                        st.markdown(f"[🔗 Original Link]({url})")

                with col2:
                    st.metric("Relevance", f"{relevance_score:.2f}" if relevance_score else "N/A")
                    st.text(f"Processed: {'✅' if processed == 1 else '❌'}")
                    st.text(f"ID: {str(item_id)[:8]}...")

                    if st.button("View Full", key=f"view_{item_id}"):
                        st.session_state.selected_item = str(item_id)

with tab2:
    st.header("Recent Collection Runs")

    runs = get_collection_runs(limit=30)

    if runs:
        for run in runs:
            run_id, collector_type, collector_name, started_at, completed_at, status, items_collected, items_new, items_duplicate, error_message = run

            status_icon = "✅" if status == "completed" else "❌" if status == "failed" else "🔄"
            duration = (completed_at - started_at).total_seconds() if completed_at and started_at else 0

            with st.expander(f"{status_icon} {collector_name} - {started_at.strftime('%Y-%m-%d %H:%M') if started_at else 'N/A'}"):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("New Items", items_new or 0)
                col2.metric("Duplicates", items_duplicate or 0)
                col3.metric("Total", items_collected or 0)
                col4.metric("Duration", f"{duration:.1f}s")

                if error_message:
                    st.error(f"Error: {error_message}")
    else:
        st.info("No collection runs found.")

with tab3:
    st.header("Item Detail View")

    item_id = st.text_input("Enter Item ID (or use 'View Full' button):",
                           value=st.session_state.get('selected_item', ''))

    if item_id:
        try:
            item = get_item_detail(item_id)

            if item:
                st.subheader(item.title)

                st.markdown(f"""
                **Source:** {item.source_name} ({item.source_type})
                **URL:** [{item.url}]({item.url})
                **Published:** {item.published_at}
                **Collected:** {item.collected_at}
                **Author:** {item.author or 'Unknown'}
                **Categories:** {', '.join(item.categories or [])}
                **Relevance Score:** {item.relevance_score}
                **Processed:** {item.processed}
                """)

                st.markdown("---")
                st.markdown("### Summary")
                st.write(item.summary or "No summary available")

                st.markdown("---")
                st.markdown("### Full Content")
                st.write(item.content or "No content available")

                st.markdown("---")
                st.markdown("### Metadata")
                st.json(item.item_metadata or {})
            else:
                st.warning("Item not found")
        except Exception as e:
            st.error(f"Error loading item: {e}")

# Footer
st.markdown("---")
st.caption("The Pulse Intelligence Platform - Storage Browser")
