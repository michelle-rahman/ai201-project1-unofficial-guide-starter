"""embed_and_store.py — Milestone 4: embed chunks, store in ChromaDB, retrieve.

Pipeline stages 3 (EMBEDDING + VECTOR STORE) and 4 (RETRIEVAL) from planning.md:

  * Load every chunk produced by ingest.py (documents/chunks.jsonl).
  * Embed each chunk with sentence-transformers/all-MiniLM-L6-v2.
  * Persist to a local, on-disk ChromaDB collection, carrying the full source
    metadata (source name, school, url, culpa professor/course, etc.) so the
    generation step can cite where each answer came from.
  * Expose retrieve(query, k=7) returning the top-k most similar chunks —
    this is the function Milestone 5's generate.py will import.

Run:
  python embed_and_store.py                 # (re)build the vector store from chunks.jsonl
  python embed_and_store.py --rebuild       # wipe and rebuild the collection from scratch
  python embed_and_store.py --query "..."   # one-off retrieval, prints top 7 chunks
  python embed_and_store.py --test          # run the 5 planning.md evaluation questions

Output: chroma_db/  (persistent ChromaDB store; gitignored)
"""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

# --------------------------------------------------------------------------- #
# Config — keep in sync with planning.md Retrieval Approach
# --------------------------------------------------------------------------- #

CHUNKS_PATH = Path("documents") / "chunks.jsonl"
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "unofficial_guide"

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 7                # planning.md: top 7 chunks per query
ADD_BATCH = 256          # embed/insert in batches for progress + memory

# all-MiniLM-L6-v2 produces normalized embeddings, so cosine distance is the
# right similarity space (Chroma defaults to L2 otherwise).
COLLECTION_METADATA = {"hnsw:space": "cosine"}

# The 5 testable questions from planning.md's Evaluation Plan.
EVAL_QUESTIONS = [
    "Which courses have the best student reviews for satisfying my CS elective requirement?",
    "What are students' opinions on the professor teaching Artificial Intelligence this upcoming fall 2026 semester?",
    "I'm choosing between taking Columbia Natural Language Processing and Machine Learning for fall 2026. Which course has a professor with the best student reviews?",
    "What courses are being offered in fall 2026 that I can use to satisfy my area foundations requirements?",
    "Which courses are best for me to gain project experience using Python?",
]


# --------------------------------------------------------------------------- #
# Embedding + collection setup
# --------------------------------------------------------------------------- #

def _embedding_fn():
    """all-MiniLM-L6-v2 wrapped as a Chroma embedding function. Storing this on
    the collection means queries are embedded with the exact same model."""
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )


def get_collection():
    """Return the persistent collection, creating it if it does not yet exist.
    Imported by generate.py (Milestone 5) so it shares one source of truth."""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=_embedding_fn(),
        metadata=COLLECTION_METADATA,
    )


# --------------------------------------------------------------------------- #
# Building the store
# --------------------------------------------------------------------------- #

def _clean_metadata(meta: dict) -> dict:
    """ChromaDB only accepts scalar metadata values (str/int/float/bool) and no
    None. Drop anything else so the load can't fail on an odd record."""
    clean = {}
    for k, v in meta.items():
        if isinstance(v, bool) or isinstance(v, (int, float, str)):
            clean[k] = v
        # silently skip None / lists / nested dicts
    return clean


def load_chunks(path: Path = CHUNKS_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run `python ingest.py` first (Milestone 3)."
        )
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def build(rebuild: bool = False) -> None:
    """Embed all chunks and (up)load them into ChromaDB."""
    if rebuild:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"  dropped existing collection {COLLECTION_NAME!r}")
        except Exception:
            pass  # nothing to drop

    collection = get_collection()
    records = load_chunks()
    print(f"Loaded {len(records)} chunks from {CHUNKS_PATH}")
    print(f"Embedding with {EMBED_MODEL} -> ChromaDB ({CHROMA_DIR}/)")

    total = len(records)
    for start in range(0, total, ADD_BATCH):
        batch = records[start:start + ADD_BATCH]
        # upsert (not add) so re-running updates in place instead of erroring on
        # duplicate ids — each chunk id from ingest.py is already unique/stable.
        collection.upsert(
            ids=[r["id"] for r in batch],
            documents=[r["text"] for r in batch],
            metadatas=[_clean_metadata(r["metadata"]) for r in batch],
        )
        print(f"  embedded {min(start + ADD_BATCH, total)}/{total}")

    print(f"\nDONE. Collection {COLLECTION_NAME!r} now holds {collection.count()} chunks.")


# --------------------------------------------------------------------------- #
# Retrieval (pipeline stage 4) — the function Milestone 5 imports
# --------------------------------------------------------------------------- #

def retrieve(query: str, k: int = TOP_K) -> list[dict]:
    """Return the top-k most similar chunks to `query`.

    Each result: {"id", "text", "metadata", "distance"} where smaller distance
    means more similar (cosine distance in [0, 2])."""
    collection = get_collection()
    res = collection.query(
        query_texts=[query],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    hits = []
    for cid, doc, meta, dist in zip(
        res["ids"][0],
        res["documents"][0],
        res["metadatas"][0],
        res["distances"][0],
    ):
        hits.append({"id": cid, "text": doc, "metadata": meta, "distance": dist})
    return hits


# --------------------------------------------------------------------------- #
# Inspection helpers (verification step in planning.md)
# --------------------------------------------------------------------------- #

def _print_hits(query: str, hits: list[dict]) -> None:
    print("\n" + "=" * 88)
    print(f"QUERY: {query}")
    print("=" * 88)
    for i, h in enumerate(hits, 1):
        m = h["metadata"]
        # Build a compact source label that highlights culpa professor/course.
        label = m.get("source", "?")
        if m.get("professor"):
            label += f" | Prof. {m['professor']}"
        elif m.get("course_code"):
            label += f" | {m['course_code']} {m.get('course_name', '')}".rstrip()
        snippet = textwrap.shorten(h["text"].replace("\n", " "), width=320, placeholder=" …")
        print(f"\n[{i}] dist={h['distance']:.4f}  {label}  ({m.get('school', '?')})")
        print(f"    {snippet}")


def run_eval() -> None:
    for q in EVAL_QUESTIONS:
        _print_hits(q, retrieve(q))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild", action="store_true",
                    help="drop and rebuild the collection from scratch")
    ap.add_argument("--query", type=str, help="run a one-off retrieval and print top 7")
    ap.add_argument("--test", action="store_true",
                    help="run the 5 evaluation questions from planning.md")
    ap.add_argument("-k", type=int, default=TOP_K, help="top-k for --query/--test")
    args = ap.parse_args()

    if args.query:
        _print_hits(args.query, retrieve(args.query, k=args.k))
    elif args.test:
        run_eval()
    else:
        build(rebuild=args.rebuild)


if __name__ == "__main__":
    main()
