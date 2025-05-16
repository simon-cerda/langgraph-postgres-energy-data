from dotenv import load_dotenv
load_dotenv(override=True)

"""Shared utility functions used in the project.

Functions:
    format_docs: Convert documents to an xml-formatted string.
    load_chat_model: Load a chat model from a model name.
"""

from typing import Optional

from langchain.chat_models import init_chat_model
from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from sentence_transformers import SentenceTransformer
import faiss
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import numpy as np
from datetime import date
from decimal import Decimal
import os

BASE_URL = os.getenv('BASE_URL')

def load_chat_model(fully_specified_name: str, **kwargs) -> BaseChatModel:
    """Load a chat model from a fully specified name.

    Args:
        fully_specified_name (str): String in the format 'provider/model'.
        **kwargs: Additional keyword arguments to pass to init_chat_model.
    """
    if "/" in fully_specified_name:
        provider, model = fully_specified_name.split("/", maxsplit=1)

    else:
        provider = ""
        model = fully_specified_name

    if provider == "ollama-nexus":
            return init_chat_model(model, model_provider='ollama',base_url=BASE_URL, **kwargs)
    
    return init_chat_model(model, model_provider=provider, **kwargs)


from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

def execute_sql_query(query: str, schema: str, engine) -> str:
    """
    Execute a SQL query on the database and return results formatted as a Markdown table.
    
    Args:
        query (str): The SQL query to execute.
        schema (str): Schema to set before execution.
        engine: SQLAlchemy engine.
        
    Returns:
        str: Markdown-formatted results or a custom message if no results.
    """
    try:
        with engine.connect() as connection:
            if schema:
                connection.execute(text(f"SET search_path TO {schema}"))
            result = connection.execute(text(query))
            rows = result.fetchall()
            columns = result.keys()

            if not rows:
                return "La consulta no devolvió resultados."

            # Build markdown table


        def format_value(value):
            if isinstance(value, float):
                return f"{value:.2f}"
            elif isinstance(value, Decimal):
                return f"{float(value):.2f}"
            elif isinstance(value, date):
                return value.isoformat()  # YYYY-MM-DD
            else:
                return str(value)

        markdown_table = []
        markdown_table.append("| " + " | ".join(columns) + " |")
        markdown_table.append("| " + " | ".join(["---"] * len(columns)) + " |")

        for row in rows:
            formatted_row = [format_value(cell) for cell in row]
            markdown_table.append("| " + " | ".join(formatted_row) + " |")

        markdown_result = "\n".join(markdown_table)
        return markdown_result
    except SQLAlchemyError as e:
        print(f"Error al ejecutar la consulta SQL: {e}")
        
        return "ERROR SQL"
    except Exception as e:
        return f"Ocurrió un error inesperado: {e}"


def search_in_column(vectorstore: dict, model: SentenceTransformer, column: str, query: str, top_k: int = 3) -> list[str]:
    query_embedding = model.encode([query])
    index = vectorstore[column]["index"]
    values = vectorstore[column]["values"]

    D, I = index.search(np.array(query_embedding), top_k)
    return [values[i] for i in I[0]]