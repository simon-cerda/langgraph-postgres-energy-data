from dataclasses import dataclass, field, fields
from typing import List, Optional
from langchain_core.runnables import RunnableConfig,ensure_config
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError,SQLAlchemyError
from typing import Annotated
from agent import prompts


DATABASE_URL = "sqlite:///energy_consumption.db"

class DatabaseHandler:
    """Handles database interactions."""

    def __init__(self, database_url: str):
     
        try:
            self.engine = create_engine(database_url)
            self.dialect = self.engine.dialect
        except OperationalError as e:
            print(f"Error al conectar a la base de datos: {e}")
            self.engine = None


    def get_table_names(self) -> List[str]:
        inspector = inspect(self.engine)
        try:
            return inspector.get_table_names()
        except SQLAlchemyError as e:
            print(f"Error al obtener nombres de tablas: {e}")
            return []

    def get_table_schema(self, table_name: str) -> List[dict]:
        inspector = inspect(self.engine)
        try:
            return inspector.get_columns(table_name)
        except SQLAlchemyError as e:
            print(f"Error al obtener el esquema de la tabla {table_name}: {e}")
            return []

    def load_database_schema(self) -> dict:
        """Loads the entire database schema."""
        table_names = self.get_table_names()
        schema = {}
        for table_name in table_names:
            schema[table_name] = self.get_table_schema(table_name)
        return schema

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
    explain_results_prompt: str = field(
        default=prompts.EXPLAIN_RESULTS_PROMPT,
        metadata={
            "description": "The system prompt used for explaining the results of SQL queries."
        },
    )
    database_url: str = field(
        default=DATABASE_URL,
        metadata={"description": "The URL for the SQLite database."}
    )
    
    def __post_init__(self):
        """Initialize the database handler and load the schema."""
        self.db_handler = DatabaseHandler(self.database_url)
        self.database_schema = self.db_handler.load_database_schema()

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> Configuration:
        """Create a Configuration instance from a RunnableConfig object."""
        configurable = (config.get("configurable") or {}) if config else {}
        _fields = {f.name for f in fields(cls) if f.init}
        return cls(**{k: v for k, v in configurable.items() if k in _fields})