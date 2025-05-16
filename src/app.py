import streamlit as st
import asyncio
from langchain_core.messages import HumanMessage, AIMessage
from sqlalchemy import select, Table, MetaData
from sqlalchemy.orm import sessionmaker
from agent.configuration import DatabaseHandler
from agent.state import State
from agent.graph import graph

st.set_page_config(page_title="Smart City Assistant", page_icon="🤖")
st.title("🤖 Smart City Assistant")

# ------------------------------
# 1. Mapeo de nombres naturales
# ------------------------------
METRIC_LABELS = {
    'total_consumption_kwh': 'Consumo total (kWh)',
    'avg_daily_consumption_kwh': 'Consumo diario promedio (kWh)',
    'total_consumption_prev_month_kwh': 'Consumo total mes anterior (kWh)',
    'diff_pct_consumption_prev_month': 'Diferencia % respecto al mes anterior',
    'std_daily_consumption_kwh': 'Desviación estándar consumo diario (kWh)',
    'ytd_consumption_kwh': 'Consumo año en curso (kWh)',
    'ytd_prev_year_consumption_kwh': 'Consumo año anterior (kWh)',
    'total_consumption_prev_year_same_month_kwh': 'Consumo en mismo mes año anterior (kWh)'
}

# Si quisieras mapear categorías o edificios, puedes crear un diccionario similar.

# ------------------------------
# 2. Conexión y carga de datos
# ------------------------------
try:
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
except Exception as e:
    st.error(f"Error conectando a la base de datos: {e}")
    st.stop()

@st.cache_data
def load_filter_options():
    session = Session()
    try:
        category_query = select(building.c.type).distinct()
        categories = [row[0] for row in session.execute(category_query).fetchall() if row[0] is not None]

        building_query = select(building.c.name, building.c.type)
        buildings_by_category = {}
        for name, category in session.execute(building_query):
            if category and name:
                 buildings_by_category.setdefault(category, []).append(name)

        metric_types = list(METRIC_LABELS.keys())
        session.close()
        return categories, buildings_by_category, metric_types
    except Exception as e:
        st.error(f"Error cargando filtros: {e}")
        session.close()
        return [], {}, []
    finally:
        if session.is_active:
            session.close()

async def run_conversation(user_input, history=None):
    if history is None:
        history = []
    messages_for_state = history + [HumanMessage(content=user_input)]
    state = State(messages=messages_for_state)
    try:
        result = await graph.ainvoke(state)
    except Exception as e:
        st.error(f"Error invocando graph: {e}")
        return f"Ocurrió un error: {e}", history, None

    if not isinstance(result, dict):
        st.error(f"Tipo de resultado inesperado: {type(result)}")
        return "Datos inesperados del agente.", history, None

    updated_messages = result.get("messages", [])
    sql_query = result.get("sql_query", None)

    assistant_message = next(
        (msg.content for msg in reversed(updated_messages) if isinstance(msg, AIMessage)),
        "No pude procesar la solicitud."
    )
    return assistant_message, updated_messages, sql_query

# ------------------------------
# 3. Sidebar: Filtros amigables
# ------------------------------
with st.sidebar:
    st.header("Filtros")
    categories, buildings_by_category, metric_types = load_filter_options()

    selected_category = st.selectbox("Categoría", categories, key="sb_category") if categories else None

    available_buildings = buildings_by_category.get(selected_category, [])
    selected_building = st.selectbox("Nombre de Edificio", available_buildings, key="sb_building") if available_buildings else None

    # Mostrar métricas con nombres naturales, guardar el valor clave interno
    if metric_types:
        metric_label_to_key = {METRIC_LABELS[k]: k for k in metric_types}
        selected_metric_label = st.selectbox("Tipo de Métrica", list(metric_label_to_key.keys()), key="sb_metric")
        selected_metric = metric_label_to_key[selected_metric_label] if selected_metric_label else None
    else:
        selected_metric = None

    st.session_state.selected_filters = {
        "category": selected_category,
        "building": selected_building,
        "metric": selected_metric
    }

    if st.button("⚙️ Generar Prompt", key="generate_button"):
        sel_metric = st.session_state.selected_filters.get("metric")
        sel_building = st.session_state.selected_filters.get("building")
        if sel_metric and sel_building:
            # Usar el nombre natural en el prompt para el usuario, pero internamente es la clave
            pretty_metric = METRIC_LABELS.get(sel_metric, sel_metric)
            generated_prompt = f"Dame el valor de '{pretty_metric}' para el edificio '{sel_building}'."
            st.session_state.queued_prompt = generated_prompt
            st.rerun()
        else:
            st.warning("Por favor, selecciona una métrica y un edificio válidos.")

    if st.button("🗑️ Borrar chat", key="clear_button"):
        st.session_state.history = []
        if 'queued_prompt' in st.session_state:
            del st.session_state['queued_prompt']
        st.rerun()

# ------------------------------
# 4. Chat principal
# ------------------------------
if "history" not in st.session_state:
    st.session_state.history = []

queued_prompt = st.session_state.pop('queued_prompt', None)

for msg in st.session_state.history:
    if hasattr(msg, 'content'):
        msg_content = msg.content
        if isinstance(msg, HumanMessage):
            with st.chat_message("user"):
                st.markdown(msg_content)
        elif isinstance(msg, AIMessage):
            with st.chat_message("assistant"):
                st.markdown(msg_content)
                if hasattr(msg, 'additional_kwargs') and 'sql_query' in msg.additional_kwargs and msg.additional_kwargs['sql_query']:
                    with st.expander("Mostrar SQL generado (historial)"):
                        st.code(msg.additional_kwargs['sql_query'], language="sql")
    else:
        st.warning(f"Mensaje sin contenido: {type(msg)}")

user_input_from_box = st.chat_input("Escribe tu consulta o genera una desde los filtros...")

input_to_process = queued_prompt or user_input_from_box

if input_to_process:
    with st.chat_message("user"):
        st.markdown(input_to_process)
    current_history_for_call = st.session_state.history[:]
    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            try:
                response, updated_history, sql_query = asyncio.run(
                    run_conversation(input_to_process, current_history_for_call)
                )
                st.markdown(response)
                if sql_query:
                    with st.expander("Mostrar SQL generado"):
                        st.code(sql_query, language="sql")
                st.session_state.history = updated_history
                if st.session_state.history and isinstance(st.session_state.history[-1], AIMessage):
                    if not hasattr(st.session_state.history[-1], 'additional_kwargs'):
                        st.session_state.history[-1].additional_kwargs = {}
                    st.session_state.history[-1].additional_kwargs['sql_query'] = sql_query
            except Exception as e:
                st.error(f"Error en el chat: {e}")
            else:
                st.rerun()
