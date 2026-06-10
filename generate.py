"""generate.py — Milestone 5: grounded generation over retrieved chunks.

Pipeline stage 5 (GENERATION) from planning.md: take a user question, retrieve the
top-k chunks (Milestone 4's retrieve()), inject them into a grounded prompt, and ask
the LLM to answer ONLY from that context — never from its own training knowledge.

Grounding is enforced two ways:
  1. The system prompt instructs the model to answer only from the provided context and
     to say "I don't have enough information on that." when the context doesn't cover it.
  2. Source attribution is built programmatically from each retrieved chunk's metadata
     (see ask()["sources"]) — it does NOT depend on the model remembering to cite. The
     model is also asked to cite inline [S#] tags so claims map back to specific chunks.

Run:
  python generate.py --query "..."     # answer one question, print answer + sources
  python generate.py --test            # run the 5 planning.md evaluation questions
  python generate.py --query "What's the weather?"   # out-of-domain → should decline

Requires GROQ_API_KEY in .env (see .env.example).
"""

from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

from groq import Groq
from embed_and_store import retrieve, TOP_K, EVAL_QUESTIONS

load_dotenv()

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

MODEL = "llama-3.3-70b-versatile"   # Groq free-tier, OpenAI-compatible
MAX_TOKENS = 2048
TEMPERATURE = 0.2                   # low — we want faithful extraction, not creativity

# The Fall 2026 course-offerings page is source_id 8 (see embed_and_store.SOURCES). It's
# only ~16 chunks among ~1900, so plain retrieval buries it. When a question is about
# what's offered or who is teaching this term, we force those chunks into the context.
OFFERINGS_SOURCE_ID = 8
_OFFERINGS_HINTS = (
    "fall", "2026", "this semester", "next semester", "upcoming", "offered",
    "offering", "available", "who teaches", "who is teaching", "who's teaching",
    "teaching this", "being offered", "enroll",
)


def _wants_offerings(question: str) -> bool:
    q = question.lower()
    return any(h in q for h in _OFFERINGS_HINTS)

REFUSAL = "I don't have enough information on that."

SYSTEM_PROMPT = f"""You are "The Unofficial Guide," a retrieval-grounded assistant for \
Computer Science students at Barnard College and Columbia University. You answer \
questions about CS major requirements, Fall 2026 course offerings, and student reviews \
of courses and professors (from Culpa).

Follow these rules exactly:

1. Answer ONLY using the information in the "Context documents" provided in the user \
message. Do not use outside knowledge, prior training, or assumptions. The context is \
your single source of truth.

2. If the context does not contain enough information to answer the question, reply with \
exactly this sentence and nothing else: "{REFUSAL}" Do not guess, infer beyond the text, \
or fill gaps with general knowledge — even if you think you know the answer.

3. Cite your sources inline using their bracket tags (e.g. [S1], [S3]) immediately after \
the claim each one supports. Only cite tags that actually appear in the context.

4. Reviews are subjective and often mixed. When sources disagree, say so rather than \
presenting one opinion as fact. Distinguish Columbia from Barnard when it matters.

5. Be concise and specific: name exact course codes, professor names, and ratings when \
the context provides them.

Respond with your final answer only — no meta-commentary about your process."""


# --------------------------------------------------------------------------- #
# Context assembly + programmatic source attribution
# --------------------------------------------------------------------------- #

def _source_label(meta: dict) -> str:
    """A concise human-readable label for one chunk's origin, built from metadata."""
    parts = [meta.get("source", "Unknown source")]
    if meta.get("professor"):
        parts.append(f"Prof. {meta['professor']}")
    elif meta.get("course_code"):
        cc = f"{meta.get('course_code', '')} {meta.get('course_name', '')}".strip()
        if cc:
            parts.append(cc)
    label = " — ".join(parts)
    if meta.get("school"):
        label += f" ({meta['school']})"
    return label


def _build_context(hits: list[dict]) -> tuple[str, list[str]]:
    """Return (context_block, sources). Each chunk gets a stable [S#] tag so the model
    can cite it and so the returned source list maps 1:1 to the citations."""
    blocks, sources = [], []
    for i, h in enumerate(hits, 1):
        label = _source_label(h["metadata"])
        url = h["metadata"].get("url", "")
        blocks.append(f"[S{i}] {label}\n{h['text']}")
        sources.append(f"[S{i}] {label}" + (f" — {url}" if url else ""))
    return "\n\n".join(blocks), sources


# --------------------------------------------------------------------------- #
# The end-to-end function the interface calls
# --------------------------------------------------------------------------- #

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        if not os.getenv("GROQ_API_KEY"):
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file "
                "(see .env.example) before running generation."
            )
        _client = Groq()
    return _client


def ask(question: str, k: int = TOP_K) -> dict:
    """Retrieve, ground, and answer.

    Returns {"answer": str, "sources": list[str], "hits": list[dict]}. `sources` is built
    from chunk metadata in code, so attribution holds even if the model omits its inline
    citations."""
    ensure = [OFFERINGS_SOURCE_ID] if _wants_offerings(question) else None
    hits = retrieve(question, k=k, ensure_sources=ensure)
    context, sources = _build_context(hits)

    user_message = (
        f"Context documents:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer using only the context above, citing [S#] tags."
    )

    response = _get_client().chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    answer = (response.choices[0].message.content or "").strip()
    return {"answer": answer, "sources": sources, "hits": hits}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _print_result(question: str, result: dict) -> None:
    print("\n" + "=" * 88)
    print(f"Q: {question}")
    print("=" * 88)
    print(f"\n{result['answer']}\n")
    print("Retrieved from:")
    for s in result["sources"]:
        print(f"  • {s}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--query", type=str, help="ask one question")
    ap.add_argument("--test", action="store_true",
                    help="run the 5 evaluation questions from planning.md")
    ap.add_argument("-k", type=int, default=TOP_K, help="number of chunks to retrieve")
    args = ap.parse_args()

    if args.query:
        _print_result(args.query, ask(args.query, k=args.k))
    elif args.test:
        for q in EVAL_QUESTIONS:
            _print_result(q, ask(q, k=args.k))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
