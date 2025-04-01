"""Define the state structures for the agent."""

from __future__ import annotations


from dataclasses import dataclass, field
from typing import Annotated, Literal, Optional, List, Dict, Any
from typing_extensions import TypedDict
from langchain_core.documents import Document
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from pydantic import Field, BaseModel

@dataclass(kw_only=True)
class InputState:
    """Represents the input state for the agent.

    This class defines the structure of the input state, which includes
    the messages exchanged between the user and the agent. It serves as
    a restricted version of the full State, providing a narrower interface
    to the outside world compared to what is maintained internally.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    """Messages track the primary execution state of the agent.

    Typically accumulates a pattern of Human/AI/Human/AI messages; if
    you were to combine this template with a tool-calling ReAct agent pattern,
    it may look like this:

    1. HumanMessage - user input
    2. AIMessage with .tool_calls - agent picking tool(s) to use to collect
         information
    3. ToolMessage(s) - the responses (or errors) from the executed tools
    
        (... repeat steps 2 and 3 as needed ...)
    4. AIMessage without .tool_calls - agent responding in unstructured
        format to the user.

    5. HumanMessage - user responds with the next conversational turn.

        (... repeat steps 2-5 as needed ... )
    
    Merges two lists of messages, updating existing messages by ID.

    By default, this ensures the state is "append-only", unless the
    new message has the same ID as an existing message.

    Returns:
        A new list of messages with the messages from `right` merged into `left`.
        If a message in `right` has the same ID as a message in `left`, the
        message from `right` will replace the message from `left`."""

class Router(TypedDict):
    """Classify user query."""

    logic: str
    type: Literal["more-info", "database", "general"]



@dataclass(kw_only=True)
class State(InputState):
    """Defines the input state for the agent."""

    router: Router = Field(default_factory=lambda: Router(type="general", logic=""))
    relevant_tables: List[str] = Field(default_factory=list)
    relevant_columns: Dict[str, List[str]] = Field(default_factory=dict)
    sql_query: Optional[str] = None
    query_result: Optional[str] = None
    explanation: Optional[str] = None
    validation_notes: List[str] = Field(default_factory=list)

class RelevantInfoResponse(TypedDict):
    """The response to a relevant info query."""

    relevant_tables: List[str]
    relevant_columns: Dict[str, List[str]]