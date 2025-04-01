"""Define the configurable parameters for the agent."""

from __future__ import annotations

from dataclasses import dataclass, fields, field
from typing import Optional, List
from langchain_core.runnables import RunnableConfig
from agent import prompts
from typing import Annotated
from sqlalchemy import create_engine, text, inspect
from pydantic import BaseModel

DATABASE_URL = "sqlite:///energy_consumption.db"


@dataclass(kw_only=True)
class Configuration:
    """The configuration for the agent."""

    my_configurable_param: str = "changeme"
    
    query_model: Annotated[str, {"__template_metadata__": {"kind": "llm"}}] = field(
        default="openai/gpt-4o-mini",
        metadata={
            "description": "The language model used for processing and refining queries. Should be in the form: provider/model-name."
        },
    )
    router_system_prompt: str = field(
        default=prompts.ROUTER_SYSTEM_PROMPT,
        metadata={
            "description": "The system prompt used for classifying user questions to route them to the correct node."
        },
    )
    more_info_system_prompt: str = field(
        default=prompts.MORE_INFO_SYSTEM_PROMPT,
        metadata={
            "description": "The system prompt used for asking for more information from the user."
        },
    )
    general_system_prompt: str = field(
        default=prompts.GENERAL_SYSTEM_PROMPT,
        metadata={
            "description": "The system prompt used for responding to general questions."
        },
    )
    relevant_info_system_prompt: str = field(
        default=prompts.RELEVANT_INFO_SYSTEM_PROMPT,
        metadata={
            "description": "The system prompt used for responding to relevant questions."
        },
    )
    generate_sql_prompt: str = field(
        default=prompts.GENERATE_SQL_PROMPT,
        metadata={
            "description": "The system prompt used for generating SQL queries."
        },
    )

    database_url: str = field(
        default="sqlite:///energy_consumption.db",
        metadata={"description": "The URL for the SQLite database."}
    )

    def __post_init__(self):
        """Load the database schema after initialization."""
        self.engine = create_engine(self.database_url)
        self.dialect = self.engine.dialect
        self.database_schema = self._load_database_schema()
        

    def _get_table_names(self) -> List[str]:
        """Returns a list of table names in the SQLite database."""
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    def _get_table_schema(self, table_name: str):
        """Returns schema details for a given table name."""
        inspector = inspect(self.engine)
        columns = inspector.get_columns(table_name)
        return columns

    def _load_database_schema(self):
        """Loads the entire database schema."""
        table_names = self._get_table_names()
        tables = [self._get_table_schema(table) for table in table_names]
        return tables

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> Configuration:
        """Create a Configuration instance from a RunnableConfig object."""
        configurable = (config.get("configurable") or {}) if config else {}
        _fields = {f.name for f in fields(cls) if f.init}
        # Instantiate the Configuration object with configurable parameters
        instance = cls(**{k: v for k, v in configurable.items() if k in _fields})
        return instance