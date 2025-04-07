from sqlalchemy.orm import Session
from sqlalchemy import text
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

def fetch_unique_column_values(session: Session, table_name: str, columns: list[str]) -> dict[str, list[str]]:
    values_by_column = {}
    for col in columns:
        query = text(f"SELECT DISTINCT {col} FROM {table_name} WHERE {col} IS NOT NULL")
        result = session.execute(query).fetchall()
        values = [str(row[0]) for row in result]
        values_by_column[col] = values
    return values_by_column

def build_vectorstore(values_by_column: dict[str, list[str]], model: SentenceTransformer) -> dict:
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
