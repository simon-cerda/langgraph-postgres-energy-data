import streamlit as st
import asyncio
from langchain_core.messages import HumanMessage, AIMessage
# Remove direct import of run_conversation if it's defined in this file
# from chat import run_conversation  # async function
from sqlalchemy import select, Table, MetaData
from sqlalchemy.orm import sessionmaker
from agent.configuration import DatabaseHandler
from agent.state import State # Make sure State is correctly imported/defined
from langchain_core.messages import HumanMessage, AIMessage # Already imported
from agent.graph import graph  # your compiled graph

st.set_page_config(page_title="LangGraph Chatbot", page_icon="🤖")

st.title("🤖 LangGraph Chatbot")


try:
    database_handler = DatabaseHandler()
    Session = sessionmaker(bind=database_handler.engine)
    metadata = MetaData()
    metadata.reflect(bind=database_handler.engine)

    building = Table(
        "building",
        metadata,
        autoload_with=database_handler.engine,
        schema="smart_buildings" # Make sure schema name is correct
    )
except Exception as e:
    st.error(f"Error connecting to database or reflecting table: {e}")
    st.stop() # Stop execution if DB connection fails

@st.cache_data # Use cache_data for data loading
def load_filter_options():
    session = Session()
    try:
        # Get distinct categories (assuming a 'type' column exists)
        category_query = select(building.c.type).distinct()
        categories = [row[0] for row in session.execute(category_query).fetchall() if row[0] is not None] # Filter out None

        # Get buildings grouped by category
        building_query = select(building.c.name, building.c.type)
        buildings_by_category = {}
        for name, category in session.execute(building_query):
            if category and name: # Ensure category and name are not None
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
    except Exception as e:
        st.error(f"Error loading filter options from database: {e}")
        session.close()
        return [], {}, [] # Return empty structures on error
    finally:
         if session.is_active:
              session.close() # Ensure session is closed even on error


# Define run_conversation here if it's not imported
async def run_conversation(user_input, history=None):
    if history is None:
        history = []

    # Create a new list combining history and the new message for the state
    messages_for_state = history + [HumanMessage(content=user_input)]
    state = State(messages=messages_for_state)

    # If State doesn't exist or needs different init, adjust here.
    # Example: state = {"messages": messages_for_state}

    try:
        # Make sure 'graph' is your compiled LangGraph application
        result = await graph.ainvoke(state) # Use state object directly
    except Exception as e:
        st.error(f"Error invoking graph: {e}")
        # Return error message and maintain previous history
        return f"An error occurred: {e}", history, None

    # Ensure result is a dictionary-like object before accessing keys
    if not isinstance(result, dict):
         st.error(f"Unexpected result type from graph: {type(result)}")
         return "Received unexpected data from the agent.", history, None

    updated_messages = result.get("messages", []) # Default to empty list
    sql_query = result.get("sql_query", None) # Safely gets the SQL query if present

    # Finds the last AI message in the result
    assistant_message = next(
        (msg.content for msg in reversed(updated_messages) if isinstance(msg, AIMessage)),
        "Sorry, I couldn't process that request." # Fallback message
    )

    # Returns the AI text, the complete updated message list, and the SQL query
    return assistant_message, updated_messages, sql_query

# --- Sidebar ---
with st.sidebar:
    st.header("Filtros")

    categories, buildings_by_category, metric_types = load_filter_options()

    # Ensure options are available before showing selectboxes
    if not categories:
        st.warning("No categories found in the database.")
        selected_category = None
    else:
        selected_category = st.selectbox("Categoría", categories, key="sb_category")

    # Filter buildings based on selected category
    available_buildings = buildings_by_category.get(selected_category, [])
    if not available_buildings and selected_category:
         st.warning(f"No buildings found for category '{selected_category}'.")
         selected_building = None
    elif not selected_category:
        selected_building = None # No building if no category selected
    else:
        # Add a check for available_buildings not being empty before selectbox
        if available_buildings:
            selected_building = st.selectbox("Nombre de Edificio", available_buildings, key="sb_building")
        else:
            selected_building = None # Explicitly set to None if list is empty


    if not metric_types:
        st.warning("No metric types defined.")
        selected_metric = None
    else:
        selected_metric = st.selectbox("Tipo de Métrica", metric_types, key="sb_metric")

    # Store selections for the generate button
    st.session_state.selected_filters = {
        "category": selected_category, # Store None if not selected
        "building": selected_building, # Store None if not selected
        "metric": selected_metric      # Store None if not selected
    }

    # --- Generate Prompt Button ---
    if st.button("⚙️ Generar Prompt", key="generate_button"):
        sel_metric = st.session_state.selected_filters.get("metric")
        sel_building = st.session_state.selected_filters.get("building")

        # Check specifically for None or empty strings
        if sel_metric and sel_building:
            generated_prompt = f"Give me the {sel_metric} for the building {sel_building}."
            st.session_state.queued_prompt = generated_prompt
            st.rerun()
        else:
            st.warning("Por favor, selecciona una métrica y un edificio válidos para generar el prompt.")

    # --- Clear Chat Button ---
    if st.button("🗑️ Borrar chat", key="clear_button"):
        st.session_state.history = []
        if 'queued_prompt' in st.session_state:
            del st.session_state['queued_prompt']
        st.rerun()

# --- Main Chat Interface ---

if "history" not in st.session_state:
    st.session_state.history = []

# Process queued prompt
queued_prompt = st.session_state.pop('queued_prompt', None)

# Display existing chat messages first
for msg in st.session_state.history:
    # Ensure msg has a 'content' attribute and handle potential type issues
    if hasattr(msg, 'content'):
        msg_content = msg.content
        if isinstance(msg, HumanMessage):
             with st.chat_message("user"):
                  st.markdown(msg_content)
        elif isinstance(msg, AIMessage):
             with st.chat_message("assistant"):
                  st.markdown(msg_content)
                  # --- MODIFICATION: Display SQL Query from previous AI messages if stored ---
                  # Check if the message object itself has the SQL query stored (might need adjustment based on State structure)
                  if hasattr(msg, 'additional_kwargs') and 'sql_query' in msg.additional_kwargs and msg.additional_kwargs['sql_query']:
                      with st.expander("Show SQL Query (from history)"):
                           st.code(msg.additional_kwargs['sql_query'], language="sql")
        else:
             # Handle other message types if necessary
             pass # Or log unexpected type
    else:
         st.warning(f"Skipping message without content: {type(msg)}")


# Get user input
user_input_from_box = st.chat_input("Escribe tu consulta o genera una desde los filtros...")

# Determine the input for this turn
input_to_process = queued_prompt or user_input_from_box

if input_to_process:
    # Display the user message immediately
    with st.chat_message("user"):
        st.markdown(input_to_process)

    # Prepare history for the call (exclude the current input)
    current_history_for_call = st.session_state.history[:]

    # Call the conversation function and display assistant response
    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            try:
                # --- MODIFICATION: Get all three return values ---
                response, updated_history, sql_query = asyncio.run(
                    run_conversation(input_to_process, current_history_for_call)
                )

                # Display the main text response
                st.markdown(response)

                # --- MODIFICATION: Display the SQL query in an expander if it exists ---
                if sql_query:
                    with st.expander("Show Generated SQL Query"):
                        st.code(sql_query, language="sql")

                # Update the session state history with the definitive result from run_conversation
                st.session_state.history = updated_history

                # --- Add SQL to the last AI message for history display ---
                # This assumes updated_history is a list and the last item is the AIMessage
                # You might need to adjust this if your State/Graph modifies history differently
                if st.session_state.history and isinstance(st.session_state.history[-1], AIMessage):
                    # Ensure additional_kwargs exists
                    if not hasattr(st.session_state.history[-1], 'additional_kwargs'):
                         st.session_state.history[-1].additional_kwargs = {}
                    # Store the SQL query in the message itself for redisplay
                    st.session_state.history[-1].additional_kwargs['sql_query'] = sql_query


            except Exception as e:
                st.error(f"Error processing chat: {e}")
                # Avoid rerun on error to show the message

    # Rerun only if the conversation was processed successfully
    # Avoid rerun if there was an exception caught above
            else: # Use else block for successful execution
                st.rerun()