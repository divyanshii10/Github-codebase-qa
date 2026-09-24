import json
import os
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

from store import search as vector_search

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "qwen/qwen3.8-27b"  # tool-calling capable on Groq's free tier

CODE_EXT = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
            ".c", ".cpp", ".cs", ".rb", ".php", ".kt",
            ".md", ".yml", ".yaml", ".toml", ".json", ".txt", ".sql"}

TOOLS = [
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List files and folders in the repo, to see the project's structure.",
        "parameters": {"type": "object", "properties": {
            "folder": {"type": "string", "description": "Folder path relative to repo root, empty for root"}
        }},
    }},
    {"type": "function", "function": {
        "name": "search_code",
        "description": "Semantic search over the indexed codebase for a concept or feature.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "What to search for, e.g. 'user authentication'"}
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a specific file's contents, optionally a line range.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path relative to repo root"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "grep",
        "description": "Search for an exact text/name across all files. Good for class or function names.",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string"}
        }, "required": ["pattern"]},
    }},
]


def _root(repo_id):
    return Path("repos") / repo_id


def _safe_path(repo_id, rel_path):
    root = _root(repo_id).resolve()
    target = (root / rel_path).resolve()
    if not str(target).startswith(str(root)):
        return None
    return target


def tool_list_files(repo_id, folder=""):
    target = _safe_path(repo_id, folder or "")
    if not target or not target.exists():
        return {"error": "invalid folder"}
    items = [("dir " if p.is_dir() else "file") + " " + str(p.relative_to(_root(repo_id).resolve()))
             for p in sorted(target.iterdir()) if p.name not in {".git", "node_modules", "venv"}]
    return items[:100]


def tool_search_code(repo_id, query):
    results = vector_search(repo_id, query, n=5)
    return [{"path": m["path"], "lines": f"{m['start']}-{m['end']}", "text": doc[:600]} for doc, m in results]


def tool_read_file(repo_id, path, start_line=None, end_line=None):
    fp = _safe_path(repo_id, path)
    if not fp or not fp.exists():
        return {"error": "file not found"}
    lines = fp.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = (start_line or 1) - 1
    end = end_line or min(start + 60, len(lines))
    snippet = "\n".join(lines[start:end])
    if len(snippet) > 2500:
        snippet = snippet[:2500] + "\n...(truncated)"
    return {"path": path, "lines": f"{start + 1}-{end}", "text": snippet}


def tool_grep(repo_id, pattern):
    root = _root(repo_id)
    matches = []
    for fp in root.rglob("*"):
        if fp.is_file() and fp.suffix in CODE_EXT and not set(fp.parts) & {".git", "node_modules", "venv"}:
            try:
                for i, line in enumerate(fp.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if pattern in line:
                        matches.append(f"{fp.relative_to(root)}:{i}: {line.strip()}")
                        if len(matches) >= 20:
                            return matches
            except Exception:
                continue
    return matches


TOOL_FUNCS = {"list_files": tool_list_files, "search_code": tool_search_code,
              "read_file": tool_read_file, "grep": tool_grep}

AGENT_RULES = """You are a coding assistant exploring a real codebase to answer a question.
You have tools: list_files, search_code, read_file, grep. Investigate before answering.
Typical approach: list_files or search_code first to orient yourself, then read_file or grep to confirm details.
Use at most 6 tool calls total.
Answer conversationally, in plain sentences, like a teammate explaining it, not a report.
Cite evidence as (path:start-end) woven into your sentences.
If you can't find something after investigating, say so plainly. Never invent code or files."""


def agent_answer(repo_id, question, max_steps=6):
    messages = [
        {"role": "system", "content": AGENT_RULES},
        {"role": "user", "content": question},
    ]
    sources_used = []

    for _ in range(max_steps):
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS, max_tokens=1200,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content, sources_used

        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": msg.tool_calls})
        for call in msg.tool_calls:
            fname = call.function.name
            args = json.loads(call.function.arguments or "{}")
            func = TOOL_FUNCS.get(fname)
            result = func(repo_id, **args) if func else {"error": "unknown tool"}
            if fname in ("search_code", "read_file", "grep"):
                sources_used.append({"tool": fname, **args})
            messages.append({
                "role": "tool", "tool_call_id": call.id, "name": fname,
                "content": json.dumps(result)[:4000],
            })

    messages.append({"role": "user", "content": "Answer now with what you've found so far."})
    resp = client.chat.completions.create(model=MODEL, messages=messages, max_tokens=1200)
    return resp.choices[0].message.content, sources_used

def agent_answer_stream(repo_id, question, max_steps=6):
    messages = [
        {"role": "system", "content": AGENT_RULES},
        {"role": "user", "content": question},
    ]
    sources_used = []

    for _ in range(max_steps):
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS, max_tokens=1200,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            yield f"data: {json.dumps({'type': 'answer', 'text': msg.content, 'sources': sources_used})}\n\n"
            return

        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": msg.tool_calls})
        for call in msg.tool_calls:
            fname = call.function.name
            args = json.loads(call.function.arguments or "{}")
            
            human_msg = f"Running {fname}..."
            if fname == "list_files":
                human_msg = f"Looking at the folder structure {args.get('folder', 'in root')}..."
            elif fname == "search_code":
                human_msg = f"Searching the codebase for '{args.get('query', '')}'..."
            elif fname == "read_file":
                human_msg = f"Reading {args.get('path', '')}..."
            elif fname == "grep":
                human_msg = f"Looking for '{args.get('pattern', '')}' across files..."
            
            yield f"data: {json.dumps({'type': 'step', 'tool': fname, 'message': human_msg})}\n\n"
            
            func = TOOL_FUNCS.get(fname)
            result = func(repo_id, **args) if func else {"error": "unknown tool"}
            if fname in ("search_code", "read_file", "grep"):
                sources_used.append({"tool": fname, **args})
            messages.append({
                "role": "tool", "tool_call_id": call.id, "name": fname,
                "content": json.dumps(result)[:4000],
            })

    messages.append({"role": "user", "content": "Answer now with what you've found so far."})
    resp = client.chat.completions.create(model=MODEL, messages=messages, max_tokens=1200)
    yield f"data: {json.dumps({'type': 'answer', 'text': resp.choices[0].message.content, 'sources': sources_used})}\n\n"