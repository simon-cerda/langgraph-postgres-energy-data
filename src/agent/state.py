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
    """Messages track the primary execution state of the agent."""

   

class Router(BaseModel):
    """Classify user query."""
    logic: str
    type: Literal["more-info", "database", "general"]


class QueryOutput(BaseModel):
    """Generated SQL query."""

    query: Annotated[str, ..., "Syntactically valid SQL query."]


@dataclass(kw_only=True)
class State(InputState):
    """Defines the input state for the agent."""
  
    router: Router = Field(default_factory=lambda: Router(type="general", logic=""))
    relevant_tables: List[str] = Field(default_factory=list)
    relevant_columns: Dict[str, List[str]] = Field(default_factory=dict)
    sql_query: Optional[str] = None
    #is_sql_valid: Optional[bool] = None
    query_result: Optional[str] = None
    relevant_values: Optional[List[str]] = None

    @property
    def recent_messages(self, n=3):
        return self.messages[-n:]


class RelevantInfoResponse(TypedDict):
    """The response to a relevant info query."""

    relevant_tables: List[str]
    relevant_columns: Dict[str, List[str]]