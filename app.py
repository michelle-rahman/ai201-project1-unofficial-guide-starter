"""app.py — Milestone 5 interface: a Gradio web UI over the grounded RAG pipeline.

Enter a question; the system retrieves relevant chunks, generates a grounded answer with
Groq, and shows which documents the answer drew from.

Run:  python app.py     then open http://localhost:7860
"""

import gradio as gr

from generate import ask


def handle_query(question: str):
    question = (question or "").strip()
    if not question:
        return "Please enter a question.", ""
    result = ask(question)
    sources = "\n".join(f"• {s}" for s in result["sources"])
    return result["answer"], sources


EXAMPLES = [
    "What are students' opinions on the professor teaching Artificial Intelligence in fall 2026?",
    "Which courses are best for gaining project experience using Python?",
    "What courses can satisfy my area foundations requirement?",
]

with gr.Blocks(title="The Unofficial Guide") as demo:
    gr.Markdown(
        "# The Unofficial Guide\n"
        "Ask about Computer Science major requirements, Fall 2026 course offerings, and "
        "student reviews of courses and professors at **Barnard** and **Columbia**. "
        "Answers are grounded only in the retrieved documents."
    )
    inp = gr.Textbox(label="Your question", placeholder="e.g. Who teaches Machine Learning and how are the reviews?")
    btn = gr.Button("Ask", variant="primary")
    answer = gr.Textbox(label="Answer", lines=8)
    sources = gr.Textbox(label="Retrieved from", lines=8)

    gr.Examples(examples=EXAMPLES, inputs=inp)

    btn.click(handle_query, inputs=inp, outputs=[answer, sources])
    inp.submit(handle_query, inputs=inp, outputs=[answer, sources])

if __name__ == "__main__":
    demo.launch()
