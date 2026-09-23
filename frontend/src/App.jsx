import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import "./App.css";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const SUGGESTIONS = [
  "How does authentication work?",
  "Explain the database schema",
  "What are the main features?",
];

function SourcesBlock({ sources }) {
  const [open, setOpen] = useState(false);
  if (!sources || sources.length === 0) return null;
  return (
    <div className="sources">
      <div className="sources-toggle" onClick={() => setOpen(!open)}>
        {open ? "▾" : "▸"} Sources · {sources.length} file{sources.length > 1 ? "s" : ""}
      </div>
      {open && (
        <div className="sources-list">
          {sources.map((s, i) => (
            <span className="source-chip" key={i}>
              {s.path}:{s.start}-{s.end}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [repoUrl, setRepoUrl] = useState("");
  const [repoId, setRepoId] = useState("");
  const [chunkCount, setChunkCount] = useState(null);
  const [status, setStatus] = useState({ text: "", error: false });
  const [indexing, setIndexing] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function indexRepo() {
    if (!repoUrl.trim() || indexing) return;
    setIndexing(true);
    setStatus({ text: "Indexing... this can take a minute", error: false });
    setMessages([]);
    try {
      const res = await fetch(`${API}/index`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: repoUrl }),
      });
      if (!res.ok) throw new Error();
      const started = await res.json();
      setRepoId(started.repo_id);
      let data = started;
      while (data.status === "indexing") {
        await new Promise((r) => setTimeout(r, 2000));
        const poll = await fetch(`${API}/index/${started.repo_id}`);
        if (!poll.ok) throw new Error();
        data = await poll.json();
      }
      if (data.status === "error") throw new Error(data.error || "Index failed");
      setChunkCount(data.chunks_indexed);
      setStatus({ text: `Repository indexed · ${data.chunks_indexed} chunks`, error: false });
    } catch {
      setStatus({ text: "Failed to index. Is the backend running?", error: true });
    }
    setIndexing(false);
  }

  async function ask(text) {
    const q = (text ?? question).trim();
    if (!q || loading || !repoId) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setQuestion("");
    setLoading(true);
    try {
      const res = await fetch(`${API}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_id: repoId, question: q }),
      });
      const data = await res.json();
      setMessages((m) => [...m, { role: "assistant", text: data.answer, sources: data.sources }]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", text: "Something went wrong answering that." }]);
    }
    setLoading(false);
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask();
    }
  }

  return (
    <div className="app">
      <div className="header">
        <div className="header-left">
          <span>◈</span>
          <span className="header-title">Codebase Q&A</span>
          <span className="header-badge">AI-powered</span>
        </div>
        <div className="header-right">
          {chunkCount != null ? `Indexed: ${chunkCount} chunks` : ""}
        </div>
      </div>

      <div className="repo-row">
        <input
          className="repo-input"
          placeholder="🔗 GitHub repository URL"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && indexRepo()}
        />
        <button className="repo-btn" onClick={indexRepo} disabled={indexing}>
          {indexing ? "Indexing..." : "Index"}
        </button>
      </div>
      {status.text && (
        <div className={`repo-status ${status.error ? "error" : ""}`}>
          {status.error ? status.text : `✓ ${status.text}`}
        </div>
      )}

      <div className="chat-scroll">
        {messages.length === 0 ? (
          <div className="empty-state">
            <div style={{ fontSize: 28 }}>◈</div>
            <h2>Codebase Q&A</h2>
            <p>Ask anything about your indexed repository.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={i}
                  className="suggestion-btn"
                  disabled={!repoId}
                  onClick={() => ask(s)}
                >
                  "{s}"
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="chat-inner">
            {messages.map((m, i) => (
              <div key={i} className={`msg-row ${m.role}`}>
                <div className={`bubble ${m.role}`}>
                  <ReactMarkdown>{m.text}</ReactMarkdown>
                  {m.role === "assistant" && <SourcesBlock sources={m.sources} />}
                </div>
              </div>
            ))}
            {loading && (
              <div className="msg-row assistant">
                <div className="bubble assistant">
                  <div className="typing"><span /><span /><span /></div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="composer-wrap">
        <div className="composer">
          <textarea
            ref={textareaRef}
            rows={1}
            placeholder={repoId ? "Ask about your codebase..." : "Index a repo first"}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={!repoId}
          />
          <button className="send-btn" onClick={() => ask()} disabled={loading || !repoId}>
            ➤
          </button>
        </div>
      </div>
    </div>
  );
}