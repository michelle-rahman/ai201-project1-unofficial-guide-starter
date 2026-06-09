"""ingest.py — fetch, preprocess, and chunk all 10 sources into documents/chunks.jsonl.

Each source family needs its own preprocessing before chunking; you cannot feed the
raw bytes to a splitter directly:

  * columbia_bulletin  -> one HTML page with four anchored tab sections; pull the
                          requested <div id="...container"> and format courseblocks /
                          requirement tables into clean text.
  * barnard_page       -> Drupal page; keep <main> content, drop nav/sidebar/footer.
  * columbia_offerings -> fixed-width text table inside <pre>; parse two-line records.
  * culpa_api          -> React SPA with no server-rendered HTML; read the JSON API
                          (departments -> professors/courses -> reviews) instead.

Run:  python ingest.py            # all sources
      python ingest.py --only 8   # one source by id
      python ingest.py --limit 15 # cap Culpa professors/courses (faster dev runs)

Output: documents/chunks.jsonl  (one JSON object per chunk; feeds Milestone 4)
        documents/raw/<id>_<name>.txt  (cleaned pre-chunk text, for manual inspection)
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

BULLETIN_URL = (
    "https://bulletin.columbia.edu/columbia-college/"
    "departments-instruction/computer-science/"
)
CULPA_API = "https://culpa.info/api"
HEADERS = {"User-Agent": "Mozilla/5.0 (UnofficialGuide RAG ingest; educational project)"}
REQUEST_PAUSE = 0.4  # seconds between requests — be polite to the servers

OUT_DIR = Path("documents")
RAW_DIR = OUT_DIR / "raw"
CHUNKS_PATH = OUT_DIR / "chunks.jsonl"

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# (chunk_size, overlap) in TOKENS, per source type — matches planning.md.
# NOTE: all-MiniLM-L6-v2 only embeds the first ~256 tokens of any chunk; anything
# past that is silently truncated at embed time. The 400-600 sizes below follow
# your spec, but consider dropping bulletin/catalog to ~256 so no chunk tail is
# lost. Tune here in one place.
CHUNK_CONFIG = {
    "columbia_bulletin": (500, 65),
    "barnard_page": (500, 65),
    "columbia_offerings": (275, 32),
    "culpa_api": (400, 50),
}

SOURCES = [
    {"id": 1, "name": "Columbia CS Overview", "type": "columbia_bulletin",
     "url": BULLETIN_URL, "section": "textcontainer", "school": "Columbia"},
    {"id": 2, "name": "Columbia CS Faculty", "type": "columbia_bulletin",
     "url": BULLETIN_URL, "section": "facultytextcontainer", "school": "Columbia"},
    {"id": 3, "name": "Columbia CS Requirements", "type": "columbia_bulletin",
     "url": BULLETIN_URL, "section": "requirementstextcontainer", "school": "Columbia"},
    {"id": 4, "name": "Columbia CS Course Catalog", "type": "columbia_bulletin",
     "url": BULLETIN_URL, "section": "coursestextcontainer", "school": "Columbia"},
    {"id": 5, "name": "Barnard CS Course Catalog", "type": "barnard_page",
     "url": "https://cs.barnard.edu/course-catalogue", "school": "Barnard"},
    {"id": 6, "name": "Barnard CS Major Requirements", "type": "barnard_page",
     "url": "https://cs.barnard.edu/major-requirements", "school": "Barnard"},
    {"id": 7, "name": "Barnard CS 4+1 Requirements", "type": "barnard_page",
     "url": "https://cs.barnard.edu/4-1-computer-science", "school": "Barnard"},
    {"id": 8, "name": "CS Courses Offered Fall 2026", "type": "columbia_offerings",
     "url": "https://doc.sis.columbia.edu/sel/COMS_Fall2026_text.html", "school": "Columbia"},
    {"id": 9, "name": "Culpa: CS @ Columbia", "type": "culpa_api",
     "url": "https://culpa.info/department/7?code=COMS", "dept_id": 7, "school": "Columbia"},
    {"id": 10, "name": "Culpa: CS @ Barnard", "type": "culpa_api",
     "url": "https://culpa.info/department/147?code=COMB", "dept_id": 147, "school": "Barnard"},
]


# --------------------------------------------------------------------------- #
# A cleaned document, before chunking
# --------------------------------------------------------------------------- #

@dataclass
class Doc:
    text: str
    metadata: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# HTTP helpers (with a tiny in-process cache so the shared bulletin URL is
# fetched only once across sources 1-4)
# --------------------------------------------------------------------------- #

_html_cache: dict[str, str] = {}

REQUEST_TIMEOUT = 60        # seconds per attempt
MAX_RETRIES = 4             # transient timeouts on culpa.info are common over long runs


def _fetch(url: str, *, accept_json: bool):
    """GET with retry + exponential backoff. Raises only after MAX_RETRIES attempts."""
    headers = {**HEADERS, "Accept": "application/json"} if accept_json else HEADERS
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            time.sleep(REQUEST_PAUSE)
            return resp
        except requests.RequestException as e:
            last_err = e
            wait = 2 ** attempt  # 1s, 2s, 4s, 8s
            print(f"     retry {attempt + 1}/{MAX_RETRIES} after {wait}s ({type(e).__name__})")
            time.sleep(wait)
    raise last_err


def get_html(url: str) -> str:
    if url not in _html_cache:
        _html_cache[url] = _fetch(url, accept_json=False).text
    return _html_cache[url]


def get_json(url: str):
    return _fetch(url, accept_json=True).json()


def clean_text(s: str) -> str:
    """Unescape entities and collapse whitespace; keep paragraph breaks."""
    if not s:
        return ""
    s = html.unescape(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# --------------------------------------------------------------------------- #
# Preprocessor 1 & 2: HTML content sections (Columbia bulletin + Barnard)
# --------------------------------------------------------------------------- #

def _courselist_to_text(table) -> str:
    """Turn a .sc_courselist requirements table into 'CODE — Title — Points' lines."""
    lines = []
    for row in table.find_all("tr"):
        cells = [clean_text(td.get_text(" ")) for td in row.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if cells:
            lines.append(" — ".join(cells))
    return "\n".join(lines)


def _section_to_text(node) -> str:
    """Format an HTML content node: courseblocks and requirement tables get
    structured rendering; everything else falls back to readable get_text."""
    # Drop non-content elements in place.
    for junk in node.find_all(["script", "style", "nav", "noscript", "form"]):
        junk.decompose()

    parts: list[str] = []

    # Course descriptions (used by both Columbia bulletin and Barnard catalogue).
    for block in node.find_all(class_="courseblock"):
        title = block.find(class_="courseblocktitle")
        desc = block.find(class_="courseblockdesc")
        title_txt = clean_text(title.get_text(" ")) if title else ""
        desc_txt = clean_text(desc.get_text(" ")) if desc else ""
        if title_txt or desc_txt:
            parts.append(f"{title_txt}\n{desc_txt}".strip())
        block.decompose()  # remove so it isn't double-counted by the fallback below

    # Requirement course tables.
    for table in node.find_all("table", class_="sc_courselist"):
        txt = _courselist_to_text(table)
        if txt:
            parts.append(txt)
        table.decompose()

    # Remaining prose (overview text, area headers, comments, faculty lists).
    remainder = clean_text(node.get_text("\n"))
    if remainder:
        parts.append(remainder)

    return clean_text("\n\n".join(p for p in parts if p))


def preprocess_columbia_bulletin(src: dict) -> list[Doc]:
    soup = BeautifulSoup(get_html(src["url"]), "html.parser")
    container = soup.find(id=src["section"])
    if container is None:
        raise RuntimeError(f"section id {src['section']!r} not found on {src['url']}")
    text = _section_to_text(container)
    return [Doc(text=text, metadata={"section": src["section"]})]


def preprocess_barnard_page(src: dict) -> list[Doc]:
    soup = BeautifulSoup(get_html(src["url"]), "html.parser")
    # Prefer the tight content region; fall back to <main>.
    node = soup.find(class_="content-main") or soup.find("main") or soup.body
    # Strip site chrome that lives inside main on some Drupal layouts.
    for sel in ["header", "footer", "nav"]:
        for el in node.find_all(sel):
            el.decompose()
    for cls in ["content-sidebar", "region-header", "region-footer", "breadcrumb"]:
        for el in node.find_all(class_=cls):
            el.decompose()
    return [Doc(text=_section_to_text(node), metadata={})]


# --------------------------------------------------------------------------- #
# Preprocessor 3: Fall 2026 fixed-width <pre> table
# --------------------------------------------------------------------------- #

_COURSE_LINE = re.compile(r"^([A-Z]{4}\s+[A-Z]?\d{4})\b")


def preprocess_columbia_offerings(src: dict) -> list[Doc]:
    soup = BeautifulSoup(get_html(src["url"]), "html.parser")
    pre = soup.find("pre")
    if pre is None:
        raise RuntimeError("no <pre> block found on offerings page")
    raw_lines = html.unescape(pre.get_text()).split("\n")

    records: list[str] = []
    current: dict | None = None

    def flush():
        if not current:
            return
        bits = [f"{current['number']} — {current['title']}"]
        meta = []
        if current.get("section"):
            meta.append(f"Section {current['section']}")
        if current.get("call"):
            meta.append(f"Call# {current['call']}")
        if current.get("points"):
            meta.append(f"{current['points']} pts")
        if current.get("activity"):
            meta.append(current["activity"])
        if current.get("subject"):
            meta.append(current["subject"])
        if meta:
            bits.append(", ".join(meta) + ".")
        if current.get("faculty"):
            bits.append(f"Instructor: {current['faculty']}.")
        for note in current.get("notes", []):
            bits.append(f"Note: {note}")
        records.append(" ".join(bits))

    for line in raw_lines:
        if _COURSE_LINE.match(line):
            # Start of a new course offering (line 1 of the 2-line record).
            flush()
            cols = re.split(r"\s{2,}", line.strip())
            current = {"number": cols[0], "notes": []}
            current["section"] = cols[1] if len(cols) > 1 else ""
            current["call"] = cols[2] if len(cols) > 2 else ""
            current["points"] = cols[3] if len(cols) > 3 else ""
            # Title plus optional trailing faculty ("Lastname, First").
            tail = cols[4:]
            if tail and ("," in tail[-1]) and not tail[-1].isupper():
                current["faculty"] = tail[-1]
                current["title"] = " ".join(tail[:-1])
            else:
                current["faculty"] = ""
                current["title"] = " ".join(tail)
        elif current is not None and line.strip().startswith("Note:"):
            current["notes"].append(line.strip()[len("Note:"):].strip())
        elif current is not None and line.strip():
            # Line 2: activity / subject (e.g. "L  LECTURE  Computer Science").
            cols = re.split(r"\s{2,}", line.strip())
            for c in cols:
                if c.isupper() and len(c) > 2 and not current.get("activity"):
                    current["activity"] = c.title()
                elif c and not c.isupper() and not current.get("subject"):
                    current["subject"] = c
    flush()

    text = "\n\n".join(records)
    return [Doc(text=text, metadata={"record_count": len(records)})]


# --------------------------------------------------------------------------- #
# Preprocessor 4: Culpa JSON API
# --------------------------------------------------------------------------- #

def _culpa_professor_reviews(pid: int) -> list[dict]:
    """Reviews are paginated 5-per-page, 1-indexed; page 0 is empty."""
    out, page = [], 1
    while True:
        data = get_json(f"{CULPA_API}/review/professor/{pid}?page={page}")
        revs = data.get("reviews", [])
        if not revs:
            break
        out.extend(revs)
        page += 1
        if page > 50:  # safety valve
            break
    return out


def _build_professor_doc(prof: dict, school: str) -> Doc | None:
    """Substantive review evidence: ai_overview + every review for one professor."""
    pid = prof["professor_id"]
    name = f"{prof.get('first_name', '').strip()} {prof.get('last_name', '').strip()}".strip()
    card = get_json(f"{CULPA_API}/professor_page/card/{pid}")

    parts = [f"Professor {name} — Computer Science ({school})."]
    overview = clean_text(card.get("ai_overview", ""))
    if overview:
        parts.append(f"Overview of student reviews: {overview}")

    taught = card.get("courses_taught") or []
    if taught:
        names = ", ".join(
            f"{c.get('course_code', '')} {c.get('course_name', '')}".strip() for c in taught
        )
        parts.append(f"Courses taught: {names}.")

    reviews = _culpa_professor_reviews(pid)
    for r in reviews:
        ch = r.get("course_header") or {}
        course = f"{ch.get('course_code', '')} {ch.get('course_name', '')}".strip()
        rating = r.get("rating")
        content = clean_text(r.get("content", ""))
        workload = clean_text(r.get("workload", ""))
        if not content and not workload:
            continue
        line = "Review"
        if course:
            line += f" for {course}"
        if rating is not None:
            line += f" (rating {rating})"
        line += f": {content}"
        if workload:
            line += f" Workload: {workload}"
        parts.append(line)

    text = clean_text("\n\n".join(parts))
    if not text:
        return None
    return Doc(text=text, metadata={
        "culpa_kind": "professor",
        "professor": name,
        "professor_id": pid,
        "num_reviews": len(reviews),
    })


def _build_course_doc(course: dict, school: str) -> Doc | None:
    """Summary/navigational doc — no full review dump (those live on professor docs,
    so we avoid ingesting every review twice)."""
    cid = course["course_id"]
    card = get_json(f"{CULPA_API}/course_page/card/{cid}")
    summary = card.get("course_summary") or {}
    header = summary.get("course_header") or {}
    code = header.get("course_code", course.get("course_code", ""))
    cname = header.get("course_name", course.get("name", ""))

    parts = [f"{code} {cname} — Computer Science ({school})."]
    if summary.get("avg_rating") is not None:
        parts.append(f"Average rating: {summary['avg_rating']}.")
    if summary.get("num_reviews") is not None:
        parts.append(f"Number of reviews: {summary['num_reviews']}.")
    profs = card.get("professors_that_taught") or []
    if profs:
        names = ", ".join(
            f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() for p in profs
        )
        parts.append(f"Professors who have taught it: {names}.")
    for q in (card.get("quotes") or [])[:5]:
        qt = clean_text(q if isinstance(q, str) else q.get("content", ""))
        if qt:
            parts.append(f"Student quote: {qt}")

    text = clean_text("\n\n".join(parts))
    if not text:
        return None
    return Doc(text=text, metadata={
        "culpa_kind": "course",
        "course_code": code,
        "course_name": cname,
        "course_id": cid,
    })


def preprocess_culpa_api(src: dict, limit: int | None) -> list[Doc]:
    dept_id = src["dept_id"]
    school = src["school"]
    docs: list[Doc] = []
    skipped = 0

    # Per-item try/except: a single bad record (e.g. a 500 on one course id, or a
    # professor whose reviews fail to page) is skipped, not fatal to the department.
    professors = get_json(f"{CULPA_API}/departments/{dept_id}/professors")
    if limit:
        professors = professors[:limit]
    for prof in professors:
        try:
            doc = _build_professor_doc(prof, school)
            if doc:
                docs.append(doc)
        except Exception as e:
            skipped += 1
            print(f"     skip professor {prof.get('professor_id')}: {type(e).__name__}")

    courses = get_json(f"{CULPA_API}/departments/{dept_id}/courses")
    if limit:
        courses = courses[:limit]
    for course in courses:
        try:
            doc = _build_course_doc(course, school)
            if doc:
                docs.append(doc)
        except Exception as e:
            skipped += 1
            print(f"     skip course {course.get('course_id')}: {type(e).__name__}")

    if skipped:
        print(f"     ({skipped} item(s) skipped after retries)")
    return docs


# --------------------------------------------------------------------------- #
# Chunking (token-aware, RecursiveCharacterTextSplitter per planning.md)
# --------------------------------------------------------------------------- #

def build_splitters():
    """Return {source_type: splitter}. Length is measured in real embed-model
    tokens so the planning.md token sizes are honored exactly."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    try:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(EMBED_MODEL)
        length_fn = lambda t: len(tok.encode(t, add_special_tokens=False))
        print(f"  token length: {EMBED_MODEL} tokenizer")
    except Exception as e:  # offline / transformers missing -> char heuristic
        length_fn = lambda t: max(1, len(t) // 4)
        print(f"  token length: heuristic (chars/4) — {e}")

    splitters = {}
    for stype, (size, overlap) in CHUNK_CONFIG.items():
        splitters[stype] = RecursiveCharacterTextSplitter(
            chunk_size=size,
            chunk_overlap=overlap,
            length_function=length_fn,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
    return splitters


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

PREPROCESSORS = {
    "columbia_bulletin": lambda s, limit: preprocess_columbia_bulletin(s),
    "barnard_page": lambda s, limit: preprocess_barnard_page(s),
    "columbia_offerings": lambda s, limit: preprocess_columbia_offerings(s),
    "culpa_api": lambda s, limit: preprocess_culpa_api(s, limit),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", type=int, help="ingest a single source id (1-10)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap Culpa professors/courses per department (dev runs)")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    splitters = build_splitters()

    sources = [s for s in SOURCES if args.only is None or s["id"] == args.only]
    total_chunks = 0

    with CHUNKS_PATH.open("w", encoding="utf-8") as out:
        for src in sources:
            print(f"\n[{src['id']}] {src['name']}  ({src['type']})")
            try:
                docs = PREPROCESSORS[src["type"]](src, args.limit)
            except Exception as e:
                print(f"  !! FAILED: {e}")
                continue

            splitter = splitters[src["type"]]
            src_chunks = 0
            raw_buf = []
            for di, doc in enumerate(docs):
                raw_buf.append(doc.text)
                for ci, chunk in enumerate(splitter.split_text(doc.text)):
                    record = {
                        "id": f"src{src['id']}-d{di}-c{ci}",
                        "text": chunk,
                        "metadata": {
                            "source_id": src["id"],
                            "source": src["name"],
                            "source_type": src["type"],
                            "url": src["url"],
                            "school": src["school"],
                            **doc.metadata,
                        },
                    }
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    src_chunks += 1

            # Save cleaned pre-chunk text for manual inspection (planning verification step).
            slug = re.sub(r"[^a-z0-9]+", "-", src["name"].lower()).strip("-")
            (RAW_DIR / f"{src['id']:02d}_{slug}.txt").write_text(
                "\n\n===== DOC BREAK =====\n\n".join(raw_buf), encoding="utf-8"
            )
            print(f"  {len(docs)} doc(s) -> {src_chunks} chunks")
            total_chunks += src_chunks

    print(f"\nDONE. {total_chunks} chunks written to {CHUNKS_PATH}")
    print(f"Cleaned text for inspection in {RAW_DIR}/")


if __name__ == "__main__":
    main()
