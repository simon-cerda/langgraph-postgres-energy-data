"""Define the workflow for the agent.
This module contains the workflow for the agent, including the nodes and edges of the graph.
"""


from typing import cast, Literal
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage

from langgraph.graph import END, START, StateGraph

from agent.configuration import Configuration
from agent.state import State, InputState, Router, RelevantInfoResponse, QueryOutput
from agent.utils import load_chat_model, execute_sql_query
import numpy as np

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
DATE = "2025-03-27"  # Current date for SQL queries
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)


async def detect_intent(state: State, *, config: RunnableConfig) -> dict[str, Router]:
    """Analyze the user's query and determine the appropriate routing.

    This function uses a language model to classify the user's query and decide how to route it
    within the conversation flow.

    Args:
        state (State): The current state of the agent, including conversation history.
        config (RunnableConfig): Configuration with the model used for query analysis.

    Returns:
        dict[str, Router]: A dictionary containing the 'router' key with the classification result (classification type and logic).
    """
    configuration = Configuration.from_runnable_config(config)
    
    model = load_chat_model(configuration.query_model)
    
    messages = [SystemMessage(content=configuration.router_system_prompt)] + state.recent_messages
    
    response = cast(
        Router, await model.with_structured_output(Router).ainvoke(messages)
    )
    return {"router": {"type":response.type, "logic":response.logic}}


def route_query(state: State) -> Literal["retrieve_relevant_values", "ask_for_more_info", "respond_to_general_query"]:
    """Determine the next step based on the query classification.

    Args:
        state (State): The current state of the agent, including the router's classification.

    Returns:
        Literal["retrieve_relevant_values", "ask_for_more_info", "respond_to_general_query"]: The next step to take.

    Raises:
        ValueError: If an unknown router type is encountered.
    """
    ROUTE_MAP = {
    "database": "retrieve_relevant_values",
    "more-info": "ask_for_more_info",
    "general": "respond_to_general_query"
    }
    try:
        return ROUTE_MAP[state.router["type"]]
    except KeyError:
        raise ValueError(f"Unknown router type {state.router['type']}")

async def extract_relevant_info(state: State, *, config: RunnableConfig) -> State:
    """Extract relevant tables and columns from the database schema based on the user query."""
    configuration = Configuration.from_runnable_config(config)

    model = load_chat_model(configuration.query_model)

    database_schema = configuration.database_schema

    prompt = configuration.relevant_info_system_prompt.format(
        schema_description=database_schema
    )

    messages = [SystemMessage(content=prompt)] + state.recent_messages

    model_response = cast(RelevantInfoResponse, await model.with_structured_output(RelevantInfoResponse).ainvoke(messages))

    return {"relevant_tables": model_response["relevant_tables"],"relevant_columns": model_response["relevant_columns"]}


def retrieve_relevant_values(state: State, config: RunnableConfig) -> State:
    """Retrieve relevant values from the database based on the user's query."""
    configuration = Configuration.from_runnable_config(config)
    vector_handler = configuration.vectorstore_handler
    relevant_values_dict = {}
    user_query = state.messages[-1].content

    query_embedding = embedding_model.encode([user_query])
    
    for column in ["name","type"]:
        # Skip if column not in vectorstore
        if column not in vector_handler.vectorstore:
            continue

        # Get index and values
        index = vector_handler.vectorstore[column]["index"]
        values = vector_handler.vectorstore[column]["values"]

        # Search for relevant values in the column
        D, I = index.search(np.array(query_embedding), 2)

        # Collect top-k relevant values
        top_values = [values[i] for i in I[0]]
        relevant_values_dict[column] = top_values


    return {"relevant_values": relevant_values_dict}


async def generate_sql(state: State, *, config: RunnableConfig) -> State:
    """SQL generation with schema validation"""
    configuration = Configuration.from_runnable_config(config)
    model = load_chat_model(configuration.query_model).with_structured_output(QueryOutput)
    database_handler = configuration.db_handler
    database_schema = configuration.database_schema

    prompt = configuration.generate_sql_prompt.format(
        schema_context=database_schema,
        relevant_values = state.relevant_values,
        dialect = database_handler.dialect,
        date =DATE,
    )

    messages = [SystemMessage(content=prompt)] + state.recent_messages
    
    
    response = await model.ainvoke(messages)
    
    return {"sql_query":response.query.strip()}

#TODO - Add validation for SQL query
async def get_database_results(state: State, *, config: RunnableConfig) -> State:
    """Ejecuta una consulta SQL y maneja errores."""

    configuration = Configuration.from_runnable_config(config)
    db_handler = configuration.db_handler

    query_result = execute_sql_query(query=state.sql_query,
                                     schema=db_handler.schema_name, 
                                     engine=db_handler.engine)

    return {'query_result': query_result}



async def generate_explanation(state: State,config:RunnableConfig) -> State:

    configuration = Configuration.from_runnable_config(config)
    
    prompt = configuration.explain_results_prompt.format(
        messages="\n\n".join([message.content for message in state.recent_messages]),
        sql = state.sql_query,
        sql_results=state.query_result)

    model = load_chat_model(configuration.query_model)

    response = await model.ainvoke(prompt)


    return {"messages": [response]}



async def respond_to_general_query(state: State, *, config: RunnableConfig) -> State:
    """Generate a response to a general query not related to LangChain.

    This node is called when the router classifies the query as a general question.

    Args:
        state (AgentState): The current state of the agent, including conversation history and router logic.
        config (RunnableConfig): Configuration with the model used to respond.

    Returns:
        dict[str, list[str]]: A dictionary with a 'messages' key containing the generated response.
    """
    configuration = Configuration.from_runnable_config(config)
    model = load_chat_model(configuration.query_model)
    system_prompt = configuration.general_system_prompt.format(
        logic=state.router["logic"]
    )
    messages =[SystemMessage(content=system_prompt)] + state.recent_messages
    response = await model.ainvoke(messages)
    return {"messages": [response]}

async def ask_for_more_info(state: State, *, config: RunnableConfig) -> State:
    """Generate a response asking the user for more information.

    This node is called when the router determines that more information is needed from the user.

    Args:
        state (AgentState): The current state of the agent, including conversation history and router logic.
        config (RunnableConfig): Configuration with the model used to respond.

    Returns:
        dict[str, list[str]]: A dictionary with a 'messages' key containing the generated response.
    """
    configuration = Configuration.from_runnable_config(config)
    model = load_chat_model(configuration.query_model)
    system_prompt = configuration.more_info_system_prompt.format(
        logic=state.router["logic"]
    )
    messages = [SystemMessage(content=system_prompt)] + state.recent_messages
    response = await model.ainvoke(messages)
    return {"messages": [response]}

# Define a new graph
workflow = StateGraph(State,input=InputState, config_schema=Configuration)

# Define the nodes and edges of the graph
workflow.add_node("intent_detection", detect_intent)
workflow.add_node(ask_for_more_info)
workflow.add_node(respond_to_general_query)
workflow.add_node("extract_relevant_info", extract_relevant_info)
workflow.add_node("retrieve_relevant_values", retrieve_relevant_values)
workflow.add_node("sql_generation", generate_sql)
workflow.add_node("query_execution", get_database_results)
workflow.add_node("explanation_generation", generate_explanation)

workflow.add_edge(START, "intent_detection")
workflow.add_conditional_edges("intent_detection", route_query)
# workflow.add_edge("extract_relevant_info", "retrieve_relevant_values")
workflow.add_edge("retrieve_relevant_values", "sql_generation")
workflow.add_edge("sql_generation", "query_execution")
workflow.add_edge("query_execution", "explanation_generation")
workflow.add_edge("ask_for_more_info", END)
workflow.add_edge("respond_to_general_query", END)
workflow.add_edge("explanation_generation", END)


# Compile the workflow into an executable graph
graph = workflow.compile()
graph.name = "New Graph"  # This defines the custom name in LangSmith
