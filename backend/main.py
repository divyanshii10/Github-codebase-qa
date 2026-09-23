import os
import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ingest import clone_repo, list_files, repo_id_from_url
from chunker import chunk_repo
from store import save_chunks, search
from llm import answer

app = FastAPI()

_jobs = {}
_jobs_lock = threading.Lock()


def _origins():
    origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    extra = os.getenv("FRONTEND_ORIGIN", "")
    for item in extra.split(","):
        item = item.strip().rstrip("/")
        if not item:
            continue
        if not item.startswith("http"):
            item = "https://" + item
        origins.append(item)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


class IndexReq(BaseModel):
    repo_url: str


class AskReq(BaseModel):
    repo_id: str
    question: str


def _run_index(url: str, repo_id: str):
    try:
        root, rid = clone_repo(url)
        files = list(list_files(root))
        chunks = chunk_repo(root, files)
        save_chunks(rid, chunks)
        with _jobs_lock:
            _jobs[repo_id] = {
                "status": "ready",
                "repo_id": rid,
                "chunks_indexed": len(chunks),
                "error": None,
            }
    except Exception as exc:
        with _jobs_lock:
            _jobs[repo_id] = {
                "status": "error",
                "repo_id": repo_id,
                "chunks_indexed": None,
                "error": str(exc),
            }


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/index")
def index_repo(req: IndexReq):
    repo_id = repo_id_from_url(req.repo_url)
    with _jobs_lock:
        _jobs[repo_id] = {
            "status": "indexing",
            "repo_id": repo_id,
            "chunks_indexed": None,
            "error": None,
        }
    thread = threading.Thread(target=_run_index, args=(req.repo_url, repo_id), daemon=True)
    thread.start()
    return {"repo_id": repo_id, "status": "indexing"}


@app.get("/index/{repo_id}")
def index_status(repo_id: str):
    with _jobs_lock:
        job = _jobs.get(repo_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown repo_id")
    return job


@app.post("/ask")
def ask(req: AskReq):
    with _jobs_lock:
        job = _jobs.get(req.repo_id)
    if job and job.get("status") == "indexing":
        raise HTTPException(status_code=409, detail="Indexing is still running")
    results = search(req.repo_id, req.question)
    return {
        "answer": answer(req.question, results),
        "sources": [
            {"path": m["path"], "start": m["start"], "end": m["end"]}
            for _, m in results
        ],
    }
