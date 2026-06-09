# Project 1 Planning: The Unofficial Guide

> Write this document before you write any pipeline code.
> Your spec and architecture diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Update the Retrieval Approach and Chunking Strategy sections if you change your approach during implementation.
> Update this file before starting any stretch features.

---

## Domain

"[Fall 2026 Edition] Computer Science Major Requirements and Available Course and Professor Reviews at Barnard College and Columbia University"

This knowledge is valuable because it automates the process of Computer Science students researching their major requirements, viewing what courses are being offered in the fall of 2026 to satisfy these requirements, and having direct access to a summary of Culpa professor reviews for each course. 

---

## Documents

| # | Source | Description | URL or location |
|---|--------|-------------|-----------------|
| 1 | Columbia CS Overview | An overview of the Computer Science major at Columbia University | https://bulletin.columbia.edu/columbia-college/departments-instruction/computer-science/#text |
| 2 | Columbia CS Faculty | A list of the CS Faculty / Professors at Columbia University | https://bulletin.columbia.edu/columbia-college/departments-instruction/computer-science/#facultytext |
| 3 | Columbia CS Requirements | An overview of the Computer Science major requirements at Columbia University | https://bulletin.columbia.edu/columbia-college/departments-instruction/computer-science/#requirementstext |
| 4 | Columbia CS Course Catalog | A list of Computer Science courses at Columbia University | https://bulletin.columbia.edu/columbia-college/departments-instruction/computer-science/#coursestext |
| 5 | Barnard CS Course Catalog | A list of Computer Science courses at Barnard College | https://cs.barnard.edu/course-catalogue |
| 6 | Barnard CS Major Requirements | An overview of the Computer Science major requirements at Barnard College | https://cs.barnard.edu/major-requirements |
| 7 | Barnard CS 4+1 Requirements | A list of requirements for the Computer Science BA/MS 4+1 with Barnard College and Columbia Engineering | https://cs.barnard.edu/4-1-computer-science |
| 8 | CS Courses Being Offered for Fall of 2026 | A list of Computer Science courses that are available for students to enroll in the fall of 2026 | https://doc.sis.columbia.edu/sel/COMS_Fall2026_text.html |
| 9 | Culpa: CS @ CU Courses and Professors | Student reviews of Computer Science courses and professors at Columbia | https://culpa.info/department/7?code=COMS |
| 10 |Culpa: CS @ BC Courses and Professors | tudent reviews of Computer Science courses and professors at Barnard | https://culpa.info/department/147?code=COMB |

---

## Chunking Strategy

**Chunk size:**
400–600 tokens for Columbia/Barnard bulletin pages and course catalog pages; 200–350 tokens for the Fall 2026 offerings page. Will not chunk the Culpa pages as content chunks, since they are mostly index pages with links rather than substantive text.

**Overlap:**
50–80 tokens for bulletin/catalog pages; 25–40 tokens for the Fall 2026 offerings page; no overlap needed for Culpa link indexes.

**Reasoning:**
I am using medium-sized chunks for the Columbia and Barnard bulletin pages because those documents contain dense requirement language, course tables, prerequisite notes, and section headings that should remain intact for accurate retrieval. Smaller chunks would risk splitting important conditions away from the requirements they modify, while much larger chunks would reduce precision and make it harder to retrieve the exact rule relevant to a user’s question. I am using slightly smaller chunks for the Fall 2026 course offerings page because it is more list-like and each course offering should stay together with its instructor, meeting time, and section details. I am not chunking the Culpa department index pages directly because they primarily function as link directories rather than substantive review content; instead, I would crawl the linked course and professor pages, then chunk the actual review text from those destination pages. This approach reduces noise, preserves semantic boundaries, and improves retrieval quality for questions about major requirements, course availability, and professor feedback.

---

## Retrieval Approach

**Embedding model:**
sentence-transformers/all-MiniLM-L6-v2

**Top-k:**
Top 7 chunks per query

**Production tradeoff reflection:**
In production, I would consider using a larger or more domain-strong embedding model if higher retrieval accuracy matters more than speed and cost. all-MiniLM-L6-v2 is lightweight and efficient, which makes it a good baseline, but it may be less precise on academic text with course codes, requirement language, and short review snippets. I would also consider hybrid retrieval with keyword search plus semantic search, since exact identifiers like course numbers and professor names often matter as much as meaning. The main tradeoff is between latency and retrieval quality, and for this project I would lean toward higher precision because students need reliable course and requirement answers.

---

## Evaluation Plan

<!-- List your 5 test questions with their expected correct answers.
     Questions should be specific enough that you can judge whether the system's response
     is right or wrong. "What are good dining halls?" is too vague.
     "What do students say about wait times at [dining hall name] during lunch?" is testable. -->

| # | Question | Expected answer |
|---|----------|-----------------|
| 1 | "Which courses have the best student reviews for satisfying my CS elective requirement?" | Retrieve review-linked upper-level COMS/Barnard CS electives rather than core courses; likely strong candidates include AI, Machine Learning, NLP, Databases, Operating Systems, and Data Structures-adjacent advanced electives, but the system should answer using the actual linked Culpa review pages rather than the index pages themselves  |
| 2 | "What are student's opinions on the professor teaching Artificial Intelligence this upcoming fall 2026 semester?" | Fall 2026 COMS W4701 is the AI course of interest, and the answer should summarize student opinions for the professor actually assigned in the linked review pages; the Columbia bulletin lists Artificial Intelligence as a 4000-level area foundation course, so the response should connect that course to the relevant professor review rather than generalize from the department page |
| 3 | "I'm choosing between taking the Columbia Natural Language Processing and Machine Learning for the fall 2026 semester. Which course has a professor with the best student reviews?" | The system should compare the Fall 2026 professor reviews for COMS W4705 Natural Language Processing and COMS W4771 Machine Learning, then recommend the one with stronger Culpa feedback; both are listed as upper-level CS courses in Columbia’s major/area foundations structure, so the final answer should cite the specific instructor reviews from the linked review pages |
| 4 | "What courses are being offered in the fall 2026 semester that I can use to satisfy my area foundations requirements?" | Fall 2026 area-foundation-relevant offerings include courses such as COMS W4701 Artificial Intelligence, COMS W4705 Natural Language Processing, COMS W4771 Machine Learning, and other upper-level COMS courses shown in the Columbia Fall 2026 listing; the answer should identify which of those can count toward the three area foundation slots in the major  |
| 5 | "Which courses are best for me to gain project experience using Python?"  | COMS W2132 Intermediate Computing in Python is the strongest direct match because it explicitly teaches essential data structures, algorithms, and practical software development in Python; for project-based experience, COMS W3998 Undergrad Projects in Computer Science and COMS W4901 Projects in Computer Science are also relevant if the student has faculty approval and wants independent project work  |

---

## Anticipated Challenges

<!-- What could go wrong? Name at least two specific risks with reasoning.
     Consider: noisy or inconsistent documents, missing source attribution, off-topic
     retrieval, chunks that split key information across boundaries. -->

1. The bulletin pages are highly structured but dense, so chunk boundaries could split a rule from the requirement it modifies, such as prerequisites, double-counting notes, or course-list conditions. That could cause the retriever to return a course without the limiting context needed to interpret it correctly.


2. The Culpa pages are link directories rather than content pages, so if they are ingested directly they will produce noisy or empty retrieval results instead of useful review evidence. The system needs to follow the linked review pages and preserve course/professor metadata; otherwise, it may fail to connect student opinions to the correct class or instructor.

---

## Architecture

┌─────────────────────────────────────────────────────────────────────────────────┐
│                         RAG PIPELINE ARCHITECTURE                               │
└─────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────┐
│   1. DOCUMENT INGESTION   │
│                           │
│  Sources:                 │
│  • Columbia Bulletin      │
│  • Barnard CS pages       │
│  • Fall 2026 offerings    │
│  • Culpa review pages     │
│    (crawled from index)   │
│                           │
│  Tool: requests /         │
│        BeautifulSoup      │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│      2. CHUNKING          │
│                           │
│  Bulletin / catalog:      │
│    400–600 tokens         │
│    50–80 token overlap    │
│                           │
│  Fall 2026 offerings:     │
│    200–350 tokens         │
│    25–40 token overlap    │
│                           │
│  Culpa index pages:       │
│    Not chunked directly   │
│    → crawl linked pages   │
│                           │
│  Tool: LangChain          │
│  RecursiveCharacterSplitter
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│  3. EMBEDDING +           │
│     VECTOR STORE          │
│                           │
│  Model:                   │
│  sentence-transformers/   │
│  all-MiniLM-L6-v2         │
│                           │
│  Store: ChromaDB          │
│  (persistent, local)      │
│                           │
│  Tool: HuggingFace        │
│        Embeddings +       │
│        LangChain Chroma   │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│      4. RETRIEVAL         │
│                           │
│  Strategy: semantic       │
│  similarity search        │
│                           │
│  Top-k: 7 chunks          │
│  per query                │
│                           │
│  Tool: ChromaDB           │
│        .similarity_search │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│      5. GENERATION        │
│                           │
│  Context: top-7 chunks    │
│  + user query injected    │
│  into prompt template     │
│                           │
│  Model: GPT-4o /          │
│         Claude            │
│  (via LangChain LLM)      │
│                           │
│  Output: grounded answer  │
│  with source attribution  │
└───────────────────────────┘

---

## AI Tool Plan

**Milestone 3 — Ingestion and chunking:**

- **Tool:** Claude Code
- **Input:** The Documents table (all 10 sources with URLs), the Chunking
  Strategy section (chunk sizes, overlap values, and reasoning), and the
  Anticipated Challenges section (especially the Culpa crawling note)
- **Expected output:** A Python script (`ingest.py`) containing a scraper
  using `requests` and `BeautifulSoup` that fetches each URL, a crawler
  that follows linked Culpa review pages rather than ingesting the index
  directly, and a `chunk_text()` function using LangChain's
  `RecursiveCharacterSplitter` configured with the correct chunk size and
  overlap per source type (bulletin vs. offerings vs. Culpa)
- **Verification:** Manually inspect a sample of output chunks from each
  source type to confirm chunk sizes fall within the specified token ranges,
  that no Culpa index page content appears as a chunk, and that course/
  professor metadata is preserved alongside each chunk

**Milestone 4 — Embedding and retrieval:**

- **Tool:** Claude Code
- **Input:** The Retrieval Approach section (embedding model name, top-k
  value), the architecture diagram (stage 3 and 4 specifically), and the
  output chunks from Milestone 3
- **Expected output:** A script (`embed_and_store.py`) that loads
  `sentence-transformers/all-MiniLM-L6-v2` via HuggingFace Embeddings,
  embeds all chunks, and persists them to a local ChromaDB collection; plus
  a `retrieve()` function that accepts a query string and returns the top 7
  most similar chunks using ChromaDB's `.similarity_search()`
- **Verification:** Run each of the 5 evaluation questions from the
  Evaluation Plan through `retrieve()` and manually check that the returned
  chunks are topically relevant, that professor/course metadata is present,
  and that Culpa review content (not index links) is surfacing for
  review-related queries

**Milestone 5 — Generation and interface:**

- **Tool:** Claude Code
- **Input:** The Domain section (for framing the system prompt), the
  Evaluation Plan (all 5 test questions and expected answers), the
  architecture diagram (stage 5), and the `retrieve()` function signature
  from Milestone 4
- **Expected output:** A `generate.py` script with a prompt template that
  injects the top-7 retrieved chunks and the user query into a Claude API
  call, plus a simple CLI or Gradio interface that accepts a question and
  prints a grounded answer; the system prompt should instruct the model to
  cite sources and stay within the retrieved context
- **Verification:** Run all 5 evaluation questions end-to-end and compare
  responses against the expected answers in the Evaluation Plan; confirm
  that answers for professor review questions cite Culpa content rather than
  bulletin text, and that requirement answers correctly reflect Columbia vs.
  Barnard distinctions
```