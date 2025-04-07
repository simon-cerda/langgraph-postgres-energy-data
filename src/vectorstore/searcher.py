import numpy as np
from sentence_transformers import SentenceTransformer

def search_in_column(vectorstore: dict, model: SentenceTransformer, column: str, query: str, top_k: int = 3) -> list[str]:
    query_embedding = model.encode([query])
    index = vectorstore[column]["index"]
    values = vectorstore[column]["values"]

    D, I = index.search(np.array(query_embedding), top_k)
    return [values[i] for i in I[0]]
