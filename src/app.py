import streamlit as st
import asyncio
from langchain_core.messages import HumanMessage, AIMessage
from chat import run_conversation  # async function
from langchain_core.messages.base import BaseMessage
from sqlalchemy import select, Table, MetaData
from sqlalchemy.orm import sessionmaker
from agent.configuration import DatabaseHandler

st.set_page_config(page_title="LangGraph Chatbot", page_icon="🤖")

st.title("🤖 LangGraph Chatbot")

# Conexión a tu base de datos PostgreSQL
database_handler = DatabaseHandler()
Session = sessionmaker(bind=database_handler.engine)
metadata = MetaData()
metadata.reflect(bind=database_handler.engine)

building = Table(
    "building",
    metadata,
    autoload_with=database_handler.engine,
    schema="smart_buildings"
)

@st.cache_data
def load_filter_options():
    session = Session()

    # Get distinct categories (assuming a 'category' column exists)
    category_query = select(building.c.type).distinct()
    categories = [row[0] for row in session.execute(category_query).fetchall()]

    # Get buildings grouped by category
    building_query = select(building.c.name, building.c.type)
    buildings_by_category = {}
    for name, category in session.execute(building_query):
        buildings_by_category.setdefault(category, []).append(name)

    # Define metrics manually or query if stored somewhere
    metric_types = [
        "energy_consumption_kw_last_month",
        "energy_consumption_kw_previous_month",
        "energy_consumption_percentage_diff_previous_month",
        "energy_consumption_kw_min_last_month",
        "energy_consumption_kw_max_last_month",
    ]

    session.close()
    return categories, buildings_by_category, metric_types

with st.sidebar:
    st.header("Filtros")

    categories, buildings_by_category, metric_types = load_filter_options()

    selected_category = st.selectbox("Categoría", categories)
    available_buildings = buildings_by_category.get(selected_category, [])
    selected_building = st.selectbox("Nombre de Edificio", available_buildings)

    selected_metric = st.selectbox("Tipo de Métrica", metric_types)

    st.session_state.selected_filters = {
        "category": selected_category,
        "building": selected_building,
        "metric": selected_metric
    }

    if st.button("🗑️ Borrar chat"):
        st.session_state.history = []
        st.rerun()  # Opcional: para refrescar la UI después de limpiar


# Conversación principal
if "history" not in st.session_state:
    st.session_state.history = []

user_input = st.chat_input("Say something...")

for msg in st.session_state.history:
    with st.chat_message("user" if isinstance(msg, HumanMessage) else "assistant"):
        st.markdown(msg.content)

if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response, updated_history = asyncio.run(
                run_conversation(user_input, st.session_state.history)
            )
            st.markdown(response)

    st.session_state.history = updated_history