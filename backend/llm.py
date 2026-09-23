import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()   # reads the .env file and loads GROQ_API_KEY

client = Groq(api_key=os.environ["GROQ_API_KEY"])

MODEL = "openai/gpt-oss-20b"   # if this errors, tell me and we'll check the current name

RULES = """You are a helpful coding assistant answering questions about a specific codebase.

Answer like a knowledgeable teammate talking directly to the person, not like a report or documentation page:
- Start with a direct answer to their actual question, in plain sentences.
- Only mention files and code as supporting evidence for your explanation, not as the main content.
- Do not use Markdown tables, headers, or bullet-point dumps of raw code unless the person asks for a list.
- Keep it conversational and concise. A few short paragraphs is usually enough.
- Add a source reference like (path:start-end) right after a claim that needs it, woven into the sentence, not as a separate labeled section.
- Use ONLY the code chunks provided. If they don't contain the answer, say so plainly instead of guessing.
- Never invent code, file names, or behavior not shown in the chunks."""


def answer(question, results):
    context = "\n\n---\n\n".join(
        f"[{m['path']}:{m['start']}-{m['end']}]\n{doc}" for doc, m in results
    )
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=1500,
        messages=[
            {"role": "system", "content": RULES},
            {"role": "user", "content": f"Code chunks:\n\n{context}\n\nQuestion: {question}"},
        ],
    )
    return resp.choices[0].message.content


if __name__ == "__main__":
    import sys
    from ingest import clone_repo
    from store import search

    repo_url = sys.argv[1]
    question = sys.argv[2]
    _, rid = clone_repo(repo_url)   # already downloaded, so this just gets the id

    results = search(rid, question, n=5)
    print(answer(question, results))