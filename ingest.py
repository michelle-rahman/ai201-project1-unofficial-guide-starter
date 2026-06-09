"""
Milestone 3 — Ingestion and chunking.

Source types and chunking parameters (from planning.md):
  - Bulletin / catalog pages (sources 1–7):  400–600 tokens, 50–80 token overlap
  - Fall 2026 offerings page (source 8):      200–350 tokens, 25–40 token overlap
  - Culpa index pages (sources 9–10):         crawl linked review pages, then
                                               chunk review text at 400–600 / 50–80
"""

import json
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ---------------------------------------------------------------------------
# Source definitions
# ---------------------------------------------------------------------------

@dataclass
class Source:
    id: int
    name: str
    url: str
    source_type: str          # "bulletin" | "offerings" | "culpa_index"
    metadata: dict = field(default_factory=dict)


SOURCES = [
    Source(1,  "Columbia CS Overview",           "https://bulletin.columbia.edu/columbia-college/departments-instruction/computer-science/#text",             "bulletin"),
    Source(2,  "Columbia CS Faculty",             "https://bulletin.columbia.edu/columbia-college/departments-instruction/computer-science/#facultytext",      "bulletin"),
    Source(3,  "Columbia CS Requirements",        "https://bulletin.columbia.edu/columbia-college/departments-instruction/computer-science/#requirementstext", "bulletin"),
    Source(4,  "Columbia CS Course Catalog",      "https://bulletin.columbia.edu/columbia-college/departments-instruction/computer-science/#coursestext",      "bulletin"),
    Source(5,  "Barnard CS Course Catalog",       "https://cs.barnard.edu/course-catalogue",                                                                  "bulletin"),
    Source(6,  "Barnard CS Major Requirements",   "https://cs.barnard.edu/major-requirements",                                                                "bulletin"),
    Source(7,  "Barnard CS 4+1 Requirements",     "https://cs.barnard.edu/4-1-computer-science",                                                              "bulletin"),
    Source(8,  "CS Courses Fall 2026",            "https://doc.sis.columbia.edu/sel/COMS_Fall2026_text.html",                                                 "offerings"),
    Source(9,  "Culpa CS @ Columbia",             "https://culpa.info/department/7?code=COMS",                                                                "culpa_index"),
    Source(10, "Culpa CS @ Barnard",              "https://culpa.info/department/147?code=COMB",                                                              "culpa_index"),
]

# Approximate chars-per-token for splitter (1 token ≈ 4 chars)
CHARS_PER_TOKEN = 4

BULLETIN_CHUNK_SIZE    = 500 * CHARS_PER_TOKEN   # ~500 tokens
BULLETIN_OVERLAP       =  65 * CHARS_PER_TOKEN   # ~65 tokens
OFFERINGS_CHUNK_SIZE   = 275 * CHARS_PER_TOKEN   # ~275 tokens
OFFERINGS_OVERLAP      =  32 * CHARS_PER_TOKEN   # ~32 tokens

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; CS-Guide-Bot/1.0; +research-project)"
    )
}

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def fetch(url: str, retries: int = 3, backoff: float = 2.0) -> Optional[str]:
    """Fetch a URL and return raw HTML, or None on failure."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            print(f"  [fetch] attempt {attempt + 1} failed for {url}: {exc}")
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# Text extraction — one function per site shape
# ---------------------------------------------------------------------------

def extract_bulletin(html: str, base_url: str) -> str:
    """
    Columbia and Barnard bulletin pages share a similar CMS structure.
    Pull the main content area and discard nav, footer, and script noise.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Columbia bulletin wraps content in <div class="field-items"> or
    # <div id="main-content">; Barnard uses <main> or <article>.
    for selector in ["div#main-content", "main", "article", "div.field-items"]:
        node = soup.select_one(selector)
        if node:
            return node.get_text(separator="\n", strip=True)

    # Fallback: strip everything that is clearly boilerplate.
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def extract_offerings(html: str) -> str:
    """
    The Fall 2026 SIS page is a plain-text-style HTML table/list.
    Preserve each course block on its own lines.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def extract_culpa_review(html: str, url: str) -> str:
    """
    A single Culpa course/professor review page.
    Grab the review snippets and any rating information.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Culpa review pages put reviews inside <div class="review"> or similar.
    review_nodes = soup.select("div.review, div.nugget, section.review")
    if review_nodes:
        parts = [n.get_text(separator="\n", strip=True) for n in review_nodes]
        return "\n\n".join(parts)

    # Fallback: take everything in <main> or <body>.
    main = soup.select_one("main") or soup.body
    if main:
        for tag in main(["script", "style", "nav", "footer"]):
            tag.decompose()
        return main.get_text(separator="\n", strip=True)
    return ""


def crawl_culpa_index(html: str, index_url: str) -> list[dict]:
    """
    The Culpa department index page contains links to individual course and
    professor review pages.  Follow each link and return a list of
    {"url": ..., "text": ...} dicts for the destination pages.
    """
    soup = BeautifulSoup(html, "html.parser")
    base = "https://culpa.info"

    # Collect unique review-page hrefs
    seen = set()
    review_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Culpa review pages look like /courses/NNN or /professors/NNN
        if href.startswith("/courses/") or href.startswith("/professors/"):
            full = base + href
            if full not in seen:
                seen.add(full)
                review_links.append(full)

    print(f"  [culpa] found {len(review_links)} review links in {index_url}")

    pages = []
    for link in review_links:
        print(f"  [culpa] fetching {link}")
        page_html = fetch(link)
        if not page_html:
            continue
        text = extract_culpa_review(page_html, link)
        if text.strip():
            pages.append({"url": link, "text": text})
        time.sleep(0.5)   # polite crawl delay

    return pages


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def make_splitter(chunk_size: int, overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", " ", ""],
    )


BULLETIN_SPLITTER  = make_splitter(BULLETIN_CHUNK_SIZE,  BULLETIN_OVERLAP)
OFFERINGS_SPLITTER = make_splitter(OFFERINGS_CHUNK_SIZE, OFFERINGS_OVERLAP)


def chunk_text(text: str, source_type: str) -> list[str]:
    """Split text according to the source type's parameters."""
    splitter = OFFERINGS_SPLITTER if source_type == "offerings" else BULLETIN_SPLITTER
    return splitter.split_text(text)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def ingest_all() -> list[dict]:
    """
    Fetch, extract, and chunk all sources.
    Returns a flat list of chunk dicts ready for embedding.
    """
    all_chunks = []

    for src in SOURCES:
        print(f"\n[{src.id}] {src.name} ({src.source_type})")
        html = fetch(src.url)
        if not html:
            print(f"  Skipping — could not fetch {src.url}")
            continue

        if src.source_type == "culpa_index":
            # Crawl linked review pages; do not chunk the index itself.
            review_pages = crawl_culpa_index(html, src.url)
            for page in review_pages:
                chunks = chunk_text(page["text"], "bulletin")
                for i, chunk in enumerate(chunks):
                    all_chunks.append({
                        "source_id":   src.id,
                        "source_name": src.name,
                        "source_type": "culpa_review",
                        "url":         page["url"],
                        "chunk_index": i,
                        "text":        chunk,
                    })
            print(f"  -> {len(review_pages)} review pages, "
                  f"{sum(1 for c in all_chunks if c['source_id'] == src.id)} chunks")

        else:
            extract_fn = extract_offerings if src.source_type == "offerings" else extract_bulletin
            text = extract_fn(html, src.url) if src.source_type == "bulletin" else extract_fn(html)
            chunks = chunk_text(text, src.source_type)
            for i, chunk in enumerate(chunks):
                all_chunks.append({
                    "source_id":   src.id,
                    "source_name": src.name,
                    "source_type": src.source_type,
                    "url":         src.url,
                    "chunk_index": i,
                    "text":        chunk,
                })
            print(f"  -> {len(chunks)} chunks")

    return all_chunks


if __name__ == "__main__":
    chunks = ingest_all()
    output_path = "chunks.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"\nDone. {len(chunks)} total chunks saved to {output_path}")
