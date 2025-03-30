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

class ColumnMetadata(BaseModel):
    name: str
    type: str
    nullable: bool

class TableMetadata(BaseModel):
    name: str
    columns: List[ColumnMetadata]
    primary_keys: List[str] = []  # You might need to fetch primary keys explicitly

class DatabaseSchema(BaseModel):
    tables: List[TableMetadata]

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
    database_schema: DatabaseSchema = field(init=False) # Initialize later
    engine = field(default_factory=lambda: create_engine(f"sqlite:///{DATABASE_URL}"))

    def __post_init__(self):
        """Load the database schema after initialization."""
        self.database_schema = self._load_database_schema()

    def _get_table_names(self) -> List[str]:
        """Returns a list of table names in the SQLite database."""
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    def _get_table_schema(self, table_name: str) -> TableMetadata:
        """Returns schema details for a given table name."""
        inspector = inspect(self.engine)
        columns = inspector.get_columns(table_name)
        column_metadata_list = [
            ColumnMetadata(name=col["name"], type=str(col["type"]), nullable=col["nullable"])
            for col in columns
        ]
        # For SQLite, primary keys are part of the column info
        primary_keys = [col["name"] for col in columns if col.get("primary_key")]
        return TableMetadata(name=table_name, columns=column_metadata_list, primary_keys=primary_keys)

    def _load_database_schema(self) -> DatabaseSchema:
        """Loads the entire database schema."""
        table_names = self._get_table_names()
        tables = [self._get_table_schema(table) for table in table_names]
        return DatabaseSchema(tables=tables)

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