"""Define the workflow for the agent.
This module contains the workflow for the agent, including the nodes and edges of the graph.
"""


from typing import cast, Literal
from typing_extensions import Annotated
from typing_extensions import TypedDict

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage

from langgraph.graph import END, START, StateGraph

from agent.configuration import Configuration,DatabaseHandler,VectorStoreHandler
from agent.state import State, InputState, Router, RelevantInfoResponse, QueryOutput
from agent.utils import load_chat_model, execute_sql_query, search_in_column
import numpy as np

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
    
    messages = [
        {"role": "system", "content": configuration.router_system_prompt}
    ] + state.messages
    
    response = cast(
        Router, await model.with_structured_output(Router).ainvoke(messages)
    )
    return {"router": {"type":response.type, "logic":response.logic}}


def route_query(state: State) -> Literal["extract_relevant_info", "ask_for_more_info", "respond_to_general_query"]:
    """Determine the next step based on the query classification.

    Args:
        state (State): The current state of the agent, including the router's classification.

    Returns:
        Literal["extract_relevant_info", "ask_for_more_info", "respond_to_general_query"]: The next step to take.

    Raises:
        ValueError: If an unknown router type is encountered.
    """
    _type = state.router["type"]
    if _type == "database":
        return "extract_relevant_info"
    elif _type == "more-info":
        return "ask_for_more_info"
    elif _type == "general":
        return "respond_to_general_query"
    else:
        raise ValueError(f"Unknown router type {_type}")

async def extract_relevant_info(state: State, *, config: RunnableConfig) -> State:
    """Extract relevant tables and columns from the database schema based on the user query."""
    configuration = Configuration.from_runnable_config(config)
    model = load_chat_model(configuration.query_model)


    db_handler = configuration.db_handler
    database_schema = db_handler.load_database_schema()

    # Formatea el esquema para usarlo en el prompt 
    schema_description = str(database_schema) 

    prompt = configuration.relevant_info_system_prompt.format(
        schema_description=schema_description
    )

    messages = [
        {"role": "system", "content": prompt}
    ] + state.messages

    model_response = cast(RelevantInfoResponse, await model.with_structured_output(RelevantInfoResponse).ainvoke(messages))

    return model_response

#TODO - Work on this Node
def retrieve_relevant_values(state: State, config: Configuration) -> State:

    """Retrieve relevant values from the database based on the user's query."""

    return state


async def generate_sql(state: State, *, config: RunnableConfig) -> State:
    """SQL generation with schema validation"""
    configuration = Configuration.from_runnable_config(config)
    model = load_chat_model(configuration.query_model).with_structured_output(QueryOutput)

    db_handler = configuration.db_handler
    # Prepare schema context for LLM
    schema_context = ["schema_name: " + db_handler.schema_name]
    for table in state.relevant_tables:
        schema_context.append(db_handler.get_table_schema(table))
 
    
    prompt = configuration.generate_sql_prompt.format(
        schema_context="\n\n".join(schema_context),
        relevant_columns = state.relevant_columns,
        relevant_values = state.relevant_values,
        dialect = db_handler.dialect,
        top_k = db_handler.top_k,
    )

    messages = [
       [SystemMessage(content=prompt)] + state.messages
    ] + state.messages
    
    
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
        messages="\n\n".join([message.content for message in state.messages]), 
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
    messages =[SystemMessage(content=system_prompt)] + state.messages + state.messages
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
    messages = [SystemMessage(content=system_prompt)] + state.messages
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
workflow.add_edge("extract_relevant_info", "retrieve_relevant_values")
workflow.add_edge("retrieve_relevant_values", "sql_generation")
workflow.add_edge("sql_generation", "query_execution")
workflow.add_edge("query_execution", "explanation_generation")
workflow.add_edge("ask_for_more_info", END)
workflow.add_edge("respond_to_general_query", END)
workflow.add_edge("explanation_generation", END)


# Compile the workflow into an executable graph
graph = workflow.compile()
graph.name = "New Graph"  # This defines the custom name in LangSmith
