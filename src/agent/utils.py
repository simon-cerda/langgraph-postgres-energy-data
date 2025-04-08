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

def load_chat_model(fully_specified_name: str) -> BaseChatModel:
    """Load a chat model from a fully specified name.

    Args:
        fully_specified_name (str): String in the format 'provider/model'.
    """
    if "/" in fully_specified_name:
        provider, model = fully_specified_name.split("/", maxsplit=1)
    else:
        provider = ""
        model = fully_specified_name
    return init_chat_model(model, model_provider=provider)


def execute_sql_query(query:str,schema,engine):
    """Execute a SQL query on the database.

    Args:
        query (str): The SQL query to execute.

    Returns:
        str: The result of the query execution.
    """

    try:
        with engine.connect() as connection:
            if schema:
                connection.execute(text(f"SET search_path TO {schema}"))
            result = connection.execute(text(query))
            query_result = result.fetchall()
            
    except SQLAlchemyError as e:
        query_result = f"Error al ejecutar la consulta SELECT: {e}"
    except Exception as e:
        query_result = f"Ocurrió un error inesperado: {e}"
    
    return query_result

def search_in_column(vectorstore: dict, model: SentenceTransformer, column: str, query: str, top_k: int = 3) -> list[str]:
    query_embedding = model.encode([query])
    index = vectorstore[column]["index"]
    values = vectorstore[column]["values"]

    D, I = index.search(np.array(query_embedding), top_k)
    return [values[i] for i in I[0]]