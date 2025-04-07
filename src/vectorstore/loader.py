import faiss
import json
import os

# Store vectors and metadata
def save_vectorstore(vectorstore: dict, save_path: str):
    os.makedirs(save_path, exist_ok=True)
    meta = {}

    for col, data in vectorstore.items():
        index_path = os.path.join(save_path, f"{col}.index")
        faiss.write_index(data["index"], index_path)
        meta[col] = data["values"]  # Just save values as metadata

    with open(os.path.join(save_path, "metadata.json"), "w") as f:
        json.dump(meta, f)

def load_vectorstore(save_path: str) -> dict:
    vectorstore = {}
    with open(os.path.join(save_path, "metadata.json")) as f:
        meta = json.load(f)

    for col, values in meta.items():
        index_path = os.path.join(save_path, f"{col}.index")
        index = faiss.read_index(index_path)
        vectorstore[col] = {
            "index": index,
            "values": values
        }

    return vectorstore
