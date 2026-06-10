# [RAG] The Unofficial Guide — Columbia CS Major Courses

---

## Domain

"[Fall 2026 Edition] Computer Science Major Requirements and Available Course and Professor Reviews at Barnard College and Columbia University"

This knowledge is valuable because it automates the process of Computer Science students researching their major requirements, viewing what courses are being offered in the fall of 2026 to satisfy these requirements, and having direct access to a summary of Culpa professor reviews for each course. 

---

## Document Sources

| # | Source | Description | URL or file path |
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
Token-based (measured with the all-MiniLM-L6-v2 tokenizer). Tuned per source type: 500 tokens for Columbia Bulletin and Barnard pages, 275 for the Fall 2026 offerings page and 400 for Culpa reviews. 

**Overlap:**
~13% of chunk size — 65, 32, and 50 tokens respectively.

**Why these choices fit your documents:**
The embedding model only encodes ~256 tokens per chunk, so chunks stay small. The dense, table-like offerings page gets smaller 275-token chunks to keep each course self-contained; prose pages tolerate 500; reviews sit in between at 400. Overlap keeps a sentence that crosses a boundary intact in at least one chunk. HTML was cleaned with BeautifulSoup before chunking (scripts, nav, header, footer, and sidebars stripped; tables rendered to plain text).

**Final chunk count:**
1,903 chunks across all 10 documents.

---

## Embedding Model

**Model used:**
sentence-transformers/all-MiniLM-L6-v2 — a small, fast, local (no API key, no cost) sentence-embedding model with a 384-dimensional output and a ~256-token input window. Chosen because it runs entirely offline on CPU, is well-suited to short retrieval passages, and is more than capable for a 10-document corpus.

**Production tradeoff reflection:**
If cost weren't a constraint and this served real users, the main thing I'd revisit is the 256-token context limit — it truncates anything longer, so I'd move to a model with a larger input window (e.g. OpenAI text-embedding-3-large or Cohere embed-v3) so full reviews and requirement sections embed without being cut off. I'd also weigh accuracy on domain-specific text: a larger or domain-tuned model would better capture the nuance in course/professor reviews. The cost is latency and the local-vs-API tradeoff — MiniLM is instant and private on local hardware, whereas a hosted API adds network round-trips, rate limits, and sends data off-device. Multilingual support isn't a real factor here since the corpus is all English, but a multilingual model would matter if the documents weren't.

---

## Grounded Generation

**System prompt grounding instruction:**

The system prompt assigns the model a fixed retrieval-grounded role and gives it explicit rules, the key two being:

Answer ONLY using the information in the "Context documents" provided in the user message. Do not use outside knowledge, prior training, or assumptions. The context is your single source of truth.
If the context does not contain enough information to answer, reply with exactly this sentence and nothing else: "I don't have enough information on that." Do not guess, infer beyond the text, or fill gaps with general knowledge — even if you think you know the answer.
Plus structural choices: each retrieved chunk is injected into the context block with a stable [S#] tag, and the model is told to cite those tags inline after each claim. Temperature is set low (0.2) for faithful extraction rather than creativity. The user message restates "Answer using only the context above, citing [S#] tags."

**How source attribution is surfaced in the response:**
Attribution is built programmatically in code, not left to the model. After retrieval, each chunk's metadata (source name, professor/course, school, URL) is formatted into a [S#] source label, and that list is returned alongside the answer (result["sources"]). The Gradio UI shows it in a separate "Retrieved from" panel. So the source list is guaranteed even if the model forgets its inline [S#] citations — the model's inline tags and the code-built list reference the same numbered chunks.

---

## Evaluation Report

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | "Which courses have the best student reviews for satisfying my CS elective requirement?" | Return only CS electives that have high course and/or professor ratings on Culpa. Do not return any core classes. | Returned four CS courses. Two of which were core classes and the other two were electives. | Partially Relevant | Partially Accurate |
| 2 | "What are student's opinions on the professor teaching Artificial Intelligence this upcoming fall 2026 semester?"  | Retrieves the professor teaching AI in fall 2026 and then gives summarized Culpa reviews on those professors. | Did not have enough information to answer the query. | Off-target | Inaccurate|
| 3 | "I'm choosing between taking the Columbia Natural Language Processing and Machine Learning. Which course has the best student reviews?" | Returns a result (either NLP or ML) based on having more positive Culpa reviews. | Returns NLP since it had a rating of 5 and had positive professor reviews. | Relevant | Accurate |
| 4 | "What courses are being offered in the fall 2026 semester that I can use to satisfy my area foundations requirements?" | Lists about 5 courses that are offered in the fall to satisfy requirements. | Did not have enough information. | Off-target | Inaccurate |
| 5 | "Which courses are best for me to gain project experience using Python?" | Returns courses that have Python projects. | Returned two courses in the CS major that teaches Python and has projects. | Relevant | Accurate |

**Retrieval quality:** Relevant / Partially relevant / Off-target  
**Response accuracy:** Accurate / Partially accurate / Inaccurate

---

## Failure Case Analysis

**Question that failed:**
"What courses are being offered in the fall 2026 semester that I can use to satisfy my area foundations requirements?"

**What the system returned:**
It listed a few courses that satisfy the area foundations requirements and also specified that it has access to a list of courses offered in the fall of 2026, but did not create a connection between the two and stated that "The courses offered in Fall 2026 are listed in [S8] and [S9], but these lists do not explicitly state which courses can be used to satisfy area foundations requirements". 

**Root cause (tied to a specific pipeline stage):**
Did not create a connection between the retrieved chunks with the list of courses that satisfy the area foundations requirement and the list of courses that are offered in the fall of 2026.  

**What you would change to fix it:**
I'd stop relying on the LLM to join the two lists and instead do the intersection in code: extract the course codes from the area-foundations requirement chunks, extract the course codes from the Fall 2026 offerings chunks, compute the overlap programmatically, and pass that pre-matched list into the prompt. As a lighter-weight alternative, I'd loosen the grounding prompt to explicitly allow combining facts that both appear in the context (e.g. "you may cross-reference information stated across different sources"), since my current strict "do not infer beyond the text" instruction discouraged the model from making the connection even though both pieces were retrieved. I'd also make sure both the requirements chunks and the offerings chunks reliably land in the top-k for this query — raising k or force-including the offerings source — so generation always has both halves to work with.

---

## Spec Reflection

**One way the spec helped you during implementation:**
Writing the Chunking Strategy and Retrieval Approach sections up front meant the per-source-type chunk sizes (larger for dense bulletin prose, smaller for the list-like Fall 2026 offerings page) and the top-k=7 + all-MiniLM-L6-v2 choices were already decided before I wrote any code, so I could hand them straight to the AI tool and get an implementation that matched my intent instead of guessing. The Anticipated Challenges note about Culpa being link-index pages also pushed me to pull review content rather than ingesting directory pages, which is exactly the noise problem I'd flagged. And the 5 evaluation questions doubled as my built-in --test harness, so I had a ready way to check the system end-to-end.



**One way your implementation diverged from the spec, and why:**
The spec's architecture diagram named GPT-4o / Claude via LangChain for generation, but I implemented generation with Groq's llama-3.3-70b-versatile through the Groq SDK directly — I switched because Groq is free-tier, fast, and OpenAI-compatible, and calling the SDK directly was simpler than adding a LangChain layer for a single LLM call. I also diverged from the "pure semantic similarity, top-7" retrieval plan by adding logic that force-includes the Fall 2026 offerings chunks when a question looks term-related, because plain similarity search buried that one small source (~16 chunks among ~1,900) and term-availability questions kept missing it. Both changes were practical responses to behavior I only saw once the pipeline was running, which is exactly the kind of update the planning doc told me to expect.

---

## AI Usage

**Instance 1**

- *What I gave the AI:* 
My planning.md Documents table, the Chunking Strategy section (per-source token sizes and overlaps), and the Anticipated Challenges note about Culpa pages being link directories rather than content. I asked it to build ingest.py to scrape all 10 sources and chunk them per source type.

- *What it produced:*
A RecursiveCharacterTextSplitter-based ingestion script with per-source-type chunk configs and BeautifulSoup cleaning that stripped nav/header/footer/scripts.

- *What I changed or overrode:*
The first version measured chunk length in characters, but my planning.md sizes were specified in tokens and my embedding model (all-MiniLM-L6-v2) only encodes ~256 tokens — so I directed it to use a token-based length_function with the actual model tokenizer, and dropped the offerings page to 275 tokens so each course entry stays self-contained.

**Instance 2**

- *What I gave the AI:*
My Domain section, the retrieve() signature from Milestone 4, and the grounding requirement — answers from retrieved context only, with source attribution — and asked it to wire up generate.py plus a Gradio interface.

- *What it produced:*
A Groq-based generation function with a system prompt instructing the model to use the documents, and source names asked of the model in its response.

- *What I changed or overrode:*
 I tightened the grounding from a suggestion into a hard rule — added the exact refusal sentence ("I don't have enough information on that.") and an explicit "do not use outside knowledge" instruction — because the first prompt let the model fall back on general knowledge. I also moved source attribution out of the LLM's hands: instead of trusting the model to cite, I built the source list programmatically from each chunk's metadata so attribution is guaranteed even if the model omits its inline [S#] tags.
