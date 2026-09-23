import re
from pathlib import Path
from git import Repo

SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__",
             "dist", "build", "target", ".idea", ".vscode"}
KEEP_EXT = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
            ".c", ".cpp", ".cs", ".rb", ".php", ".kt",
            ".md", ".yml", ".yaml", ".toml", ".json", ".txt", ".sql"}
MAX_FILE_BYTES = 200_000   # skip files bigger than ~200 KB
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "composer.lock", "Cargo.lock",
}

def repo_id_from_url(url: str) -> str:
    name = url.strip().rstrip("/").removesuffix(".git").split("github.com/")[-1]
    cleaned = re.sub(r"[^a-zA-Z0-9]", "_", name)[:60]
    cleaned = cleaned.strip("_")          # never start/end with underscore
    if len(cleaned) < 3:                  # Chroma requires at least 3 characters
        cleaned = (cleaned + "___")[:3]
    return cleaned


def clone_repo(url: str):
    rid = repo_id_from_url(url)
    dest = Path("repos") / rid
    if not dest.exists():
        Repo.clone_from(url, dest, depth=1)
    return dest, rid


def list_files(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(root).parts
        if set(rel_parts) & SKIP_DIRS:
            continue
        if p.name in SKIP_FILES:
            continue
        if p.suffix not in KEEP_EXT:
            continue
        if p.stat().st_size > MAX_FILE_BYTES:
            continue
        yield p

if __name__ == "__main__":
    import sys
    root, rid = clone_repo(sys.argv[1])
    files = list(list_files(root))
    print(f"Repo id: {rid}")
    print(f"Found {len(files)} useful files. First 10:")
    for f in files[:10]:
        print("  ", f.relative_to(root))