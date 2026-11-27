import csv
import glob
import json
import os
from pathlib import Path

import chroma_db
from pypdf import PdfReader

client = chroma_db.PersistentClient(path="./chroma_db")


def _make_embedding_function():
    try:
        from chromadb.utils import embedding_functions
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    except Exception:
        # ChromaDB's built-in/default embedding function can still support local RAG
        # when the SentenceTransformers package or model has not been downloaded.
        return None


embed_fn = _make_embedding_function()
collection = client.get_or_create_collection(
    "queue_docs",
    embedding_function=embed_fn,
)


def chunk_text(text, size=500, overlap=80):
    words = " ".join(str(text).split()).split()
    if not words:
        return
    step = max(1, size - overlap)
    for i in range(0, len(words), step):
        yield " ".join(words[i:i + size])


def _read_document(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix in {".txt", ".md", ".csv", ".json"}:
        if suffix == ".csv":
            with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                rows = csv.DictReader(handle)
                return "\n".join(
                    " | ".join(f"{column}: {value}" for column, value in row.items())
                    for row in rows
                )
        if suffix == ".json":
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return json.dumps(data, ensure_ascii=False, indent=2)
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    return ""


def ingest(folder="data/docs"):
    patterns = ("*.pdf", "*.txt", "*.md", "*.csv", "*.json")
    paths = []
    for pattern in patterns:
        paths.extend(glob.glob(os.path.join(folder, "**", pattern), recursive=True))

    ingested = 0
    for path in sorted(set(paths)):
        text = _read_document(path)
        for i, chunk in enumerate(chunk_text(text)):
            source = os.path.relpath(path, folder).replace("\\", "/")
            document_id = f"{source}-{i}"
            collection.upsert(
                documents=[chunk],
                metadatas=[{"source": source}],
                ids=[document_id],
            )
            ingested += 1
    return {"documents": len(set(paths)), "chunks": ingested}


def retrieve(query, k=4):
    res = collection.query(query_texts=[query], n_results=min(k, max(1, collection.count())))
    return [
        {"text": document, "source": metadata.get("source", "unknown")}
        for document, metadata in zip(res["documents"][0], res["metadatas"][0])
    ]


ingest()