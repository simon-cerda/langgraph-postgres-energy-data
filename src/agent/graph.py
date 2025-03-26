"""Define a simple chatbot agent.

This agent returns a predefined response without using an actual LLM.
"""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig


from agent.configuration import Configuration
from agent.state import State, InputState, Router

from typing import Optional, Dict, cast, Union, Literal

from langchain_openai import ChatOpenAI 
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
import psycopg2
from langgraph.graph import END, START, StateGraph
from agent.configuration import Configuration
from agent.utils import load_chat_model
llm = ChatOpenAI(model="gpt-4", temperature=0)



async def detect_intent(state: State, *, config: RunnableConfig) -> dict[str, Router]:
    """Analyze the user's query and determine the appropriate routing.

    This function uses a language model to classify the user's query and decide how to route it
    within the conversation flow.

    Args:
        state (AgentState): The current state of the agent, including conversation history.
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
    return {"router": response}



def route_query(state: State) -> Literal["table_validation", "ask_for_more_info", "respond_to_general_query"]:
    """Determine the next step based on the query classification.

    Args:
        state (State): The current state of the agent, including the router's classification.

    Returns:
        Literal["table_validation", "request_more_info", "llm_response"]: The next step to take.

    Raises:
        ValueError: If an unknown router type is encountered.
    """
    _type = state.router["type"]
    if _type == "database":
        return "table_validation"
    elif _type == "more-info":
        return "ask_for_more_info"
    elif _type == "general":
        return "respond_to_general_query"
    else:
        raise ValueError(f"Unknown router type {_type}")

def validate_table(state: State) -> State:
    # If future expansion includes multiple tables, this logic will be extended
    state.relevant_table = "building_energy_consumption"
    return state

def prune_columns(state: State) -> State:
    prompt = f"Given the table `{state.relevant_table}`, filter out unnecessary columns for the query:\n{state.user_query}"
    response = llm([HumanMessage(content=prompt)]).content
    state.relevant_columns = response.strip().split(", ")
    return state

def generate_sql(state: State, *, config: RunnableConfig) -> State:

    configuration = Configuration.from_runnable_config(config)
    system_prompt = configuration.general_system_prompt.format(
        logic=state.router["logic"]
    )
    prompt = f"Generate an SQL query for the `{state.relevant_table}` table using only these columns: {', '.join(state.relevant_columns)}.\nUser query: {state.user_query}"
    response = llm([HumanMessage(content=prompt)]).content
    state.sql_query = response.strip()
    return state


def execute_query(state: State) -> State:
    connection = psycopg2.connect(
        dbname="smart_city_db",
        user="your_user",
        password="your_password",
        host="your_host",
        port="5432"
    )
    cursor = connection.cursor()
    cursor.execute(state.sql_query)
    state.query_result = cursor.fetchall()
    cursor.close()
    connection.close()
    return state

def generate_explanation(state: State) -> State:
    prompt = f"Explain the following SQL query and its results in simple terms:\nQuery: {state.sql_query}\nResults: {state.query_result}"
    response = llm([HumanMessage(content=prompt)]).content
    state.explanation = response.strip()
    return state



async def respond_to_general_query(state: State, *, config: RunnableConfig) -> dict[str, list[BaseMessage]]:
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
    messages = [{"role": "system", "content": system_prompt}] + state.messages
    response = await model.ainvoke(messages)
    return {"messages": [response]}

async def ask_for_more_info(state: State, *, config: RunnableConfig) -> dict[str, list[BaseMessage]]:
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
    messages = [{"role": "system", "content": system_prompt}] + state.messages
    response = await model.ainvoke(messages)
    return {"messages": [response]}

# Define a new graph
workflow = StateGraph(State,input=InputState, config_schema=Configuration)

# Define the nodes and edges of the graph
workflow.add_node("intent_detection", detect_intent)
workflow.add_node(ask_for_more_info)
workflow.add_node(respond_to_general_query)
workflow.add_node("table_validation", validate_table)
workflow.add_node("column_pruning", prune_columns)
workflow.add_node("sql_generation", generate_sql)
workflow.add_node("query_execution", execute_query)
workflow.add_node("explanation_generation", generate_explanation)

workflow.add_edge(START, "intent_detection")
workflow.add_conditional_edges("intent_detection", route_query)
workflow.add_edge("table_validation", "column_pruning")
workflow.add_edge("column_pruning", "sql_generation")
workflow.add_edge("sql_generation", "query_execution")
workflow.add_edge("query_execution", "explanation_generation")
workflow.add_edge("ask_for_more_info", END)
workflow.add_edge("respond_to_general_query", END)
workflow.add_edge("explanation_generation", END)


# Compile the workflow into an executable graph
graph = workflow.compile()
graph.name = "New Graph"  # This defines the custom name in LangSmith
