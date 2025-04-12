from dataclasses import dataclass, field, fields
from typing import List, Optional
from langchain_core.runnables import RunnableConfig,ensure_config
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError,SQLAlchemyError
from typing import Annotated
from agent import prompts
import os
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.orm import Session
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import json

import pickle
import yaml
from pathlib import Path
from typing import Dict

# DATABASE_URL = "sqlite:///energy_consumption.db"

# Load environment variables from .env file
load_dotenv()
# Get the variables
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_NAME = os.getenv('DB_NAME')
DB_SCHEMA = os.getenv('DB_SCHEMA')

if not DB_USER:
    raise ValueError("DB_USER environment variable is required.")
# Construct the database URL
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

VECTORSTORE_PATH = os.getenv('VECTORSTORE_PATH')

SCHEMA_PATH = "src/agent/schema_context.yaml"

class VectorStoreHandler:
    """Handles vector store interactions."""

    def __init__(self, vectorstore_path: str):
        self.vectorstore_path = vectorstore_path
        self.vectorstore = self.load_vectorstore(vectorstore_path)

    def save_vectorstore(self,vectorstore: dict, save_path: str):
        with open(save_path, "wb") as f:
            pickle.dump(vectorstore, f)

    def load_vectorstore(self,save_path: str) -> dict:
        with open(save_path, "rb") as f:
            vectorstore = pickle.load(f)

        return vectorstore

    def fetch_unique_column_values(self,session: Session, table_name: str, columns: list[str]) -> dict[str, list[str]]:
        values_by_column = {}
        for col in columns:
            query = text(f"SELECT DISTINCT {col} FROM {table_name} WHERE {col} IS NOT NULL")
            result = session.execute(query).fetchall()
            values = [str(row[0]) for row in result]
            values_by_column[col] = values
        return values_by_column

    def build_vectorstore(self,values_by_column: dict[str, list[str]], model: SentenceTransformer) -> dict:
        vectorstore = {}
        for col, values in values_by_column.items():
            embeddings = model.encode(values)
            index = faiss.IndexFlatL2(embeddings.shape[1])
            index.add(np.array(embeddings))
            vectorstore[col] = {
                "index": index,
                "values": values
            }
        return vectorstore
    

class DatabaseHandler:
    """Handles database interactions."""

    def __init__(self, database_url: str):
     
        try:
            self.engine = create_engine(
            database_url,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=3600
        )
            self.dialect = self.engine.dialect.name
            self.top_k = 5  # Default value for top_k
            self.schema_name = DB_SCHEMA
        except OperationalError as e:
            print(f"Error al conectar a la base de datos: {e}")
            self.engine = None


    def get_table_names(self) -> List[str]:
        inspector = inspect(self.engine)
        try:
            return inspector.get_table_names(schema=self.schema_name)+inspector.get_view_names(schema=self.schema_name)
        except SQLAlchemyError as e:
            print(f"Error al obtener nombres de tablas: {e}")
            return []

    def get_table_schema(self,table_name: str) -> List[str]:
        inspector = inspect(self.engine)
        try:
            # Get the schema of the table
            columns = inspector.get_columns(table_name, schema=self.schema_name)
            schema = "table_name: " + table_name + "\n"
            schema += "columns: \n"
            for column in columns:
                schema += f"  - name: {column['name']}\n"
                schema += f"    type: {column['type'].__class__.__name__}\n"
            
            return schema
        except SQLAlchemyError as e:
            print(f"Error al obtener el esquema de la tabla {table_name}: {e}")
            return []

    def load_database_schema(self) -> dict:
        """Loads the entire database schema with only table names and column names."""
        table_names = self.get_table_names()
        schema = {}
        for table in table_names:
            try:
                columns = inspect(self.engine).get_columns(table, schema=self.schema_name)
                schema[table] = [col["name"] for col in columns]
            except SQLAlchemyError as e:
                print(f"Error loading schema for {table}: {e}")
        return schema
    
    def load_schema_from_yaml(self, file_path: Path) -> None:
        """Load the entire schema definition from a YAML file."""
        try:
            with open(file_path, 'r') as f:
                self.schema_data = yaml.safe_load(f)
            return self._build_schema_context()
        except Exception as e:
            raise ValueError(f"Failed to load schema from YAML: {str(e)}")
    
    def _build_schema_context(self) -> None:
        """ Build the schema context string from loaded schema data."""
        if not self.schema_data:
            raise ValueError("No schema data loaded")
            
        output_str = f"Schema: {self.schema_data['schema']}\nDescription: {self.schema_data['description']}\n\n"

        # Iterate through each table and add details to the output string
        for table in self.schema_data['tables']:
            output_str += f"Table: {table['name']}\nDescription: {table['description']}\n"
            
            for column in table.get('columns', []):
                output_str += f"  Column: {column['name']}\n"
                output_str += f"    Description: {column['description']}\n"
            
            output_str += "\n"

        
        return output_str

    def get_table_description(self, table_name: str) -> Optional[Dict]:
        """Get complete description of a table including columns."""
        if not self.schema_data:
            return None
            
        # Check cache first
        if table_name in self.loaded_tables:
            return self.loaded_tables[table_name]
            
        # Find in schema data
        for table in self.schema_data.get('tables', []):
            if table['name'] == table_name:
                self.loaded_tables[table_name] = {
                    "name": table["name"],
                    "description": table.get("description", ""),
                    "columns": table.get("columns", [])
                }
                return self.loaded_tables[table_name]
                
        return None
    
    def get_schema_context(self) -> str:
        """ Get the formatted schema context string."""
        if not self.schema_context:
            raise ValueError("Schema context not loaded")
        return self.schema_context

    def get_all_table_names(self) -> List[str]:
        """ Get list of all table names in the schema."""
        if not self.schema_data:
            return []
        return [table['name'] for table in self.schema_data.get('tables', [])]
    

@dataclass(kw_only=True)
class Configuration:
    """The configuration for the agent."""

    
    
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
        default=prompts.GENERATE_SQL_PROMPT_V2,
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
    vectorstore_path: str = field(
        default=VECTORSTORE_PATH,
        metadata={"description": "The path to the vectorstore."}
    )

  
    def __post_init__(self):
        """Initialize the database handler and load the schema."""
        self.db_handler = DatabaseHandler(self.database_url)
        self.database_schema = self.db_handler.load_schema_from_yaml(SCHEMA_PATH)
        self.vectorstore_handler = VectorStoreHandler(self.vectorstore_path)
    
 

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig object."""
        configurable = (config.get("configurable") or {}) if config else {}
        _fields = {f.name for f in fields(cls) if f.init}
        return cls(**{k: v for k, v in configurable.items() if k in _fields})