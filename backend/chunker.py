import tree_sitter_python as tspython
from tree_sitter import Language, Parser

MAX_BYTES = 1500   # target maximum size of one chunk

# one ready-made parser per file type; add more languages here later
PARSERS = {
    ".py": Parser(Language(tspython.language())),
}


def split_node(node, max_bytes):
    """Return (start, end) spans; open up any piece that is too big."""
    size = node.end_byte - node.start_byte
    if size <= max_bytes or not node.children:
        return [(node.start_byte, node.end_byte)]
    spans = []
    for child in node.children:
        spans += split_node(child, max_bytes)
    return spans


def merge_spans(spans, max_bytes):
    """Glue small neighbouring spans together until a chunk is nearly full."""
    if not spans:
        return []
    merged = []
    cur_start, cur_end = spans[0]
    for start, end in spans[1:]:
        if end - cur_start <= max_bytes:
            cur_end = end
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = start, end
    merged.append((cur_start, cur_end))
    return merged


def chunk_with_parser(path, source, parser):
    tree = parser.parse(source)
    spans = merge_spans(split_node(tree.root_node, MAX_BYTES), MAX_BYTES)
    chunks = []
    for start, end in spans:
        start = source.rfind(b"\n", 0, start) + 1   # begin at the start of the line
        text = source[start:end].decode("utf-8", errors="ignore")
        if not text.strip():
            continue
        start_line = source.count(b"\n", 0, start) + 1
        end_line = source.count(b"\n", 0, end) + 1
        chunks.append({
            "text": f"File: {path}\n{text}",
            "meta": {"path": path, "start": start_line, "end": end_line},
        })
    return chunks


def chunk_by_lines(path, text, size=40, overlap=10):
    lines = text.splitlines()
    chunks = []
    for i in range(0, len(lines), size - overlap):
        piece = "\n".join(lines[i:i + size])
        if piece.strip():
            chunks.append({
                "text": f"File: {path}\n{piece}",
                "meta": {"path": path, "start": i + 1,
                         "end": min(i + size, len(lines))},
            })
    return chunks


def chunk_file(path, source: bytes, suffix):
    parser = PARSERS.get(suffix)
    if parser:
        return chunk_with_parser(path, source, parser)
    return chunk_by_lines(path, source.decode("utf-8", errors="ignore"))


def chunk_repo(root, files):
    all_chunks = []
    for f in files:
        rel = f.relative_to(root).as_posix()
        all_chunks += chunk_file(rel, f.read_bytes(), f.suffix)
    return all_chunks


if __name__ == "__main__":
    import sys
    from ingest import clone_repo, list_files

    root, rid = clone_repo(sys.argv[1])
    chunks = chunk_repo(root, list(list_files(root)))
    sizes = [len(c["text"]) for c in chunks]
    print(f"Total chunks: {len(chunks)}")
    print(f"Average size: {sum(sizes) // len(sizes)} characters")
    print(f"Biggest chunk: {max(sizes)} characters")

    shown = 0
    for c in chunks:
        if c["meta"]["path"].endswith("signer.py") and shown < 2:
            print("\n" + "=" * 60)
            print(f"Lines {c['meta']['start']}-{c['meta']['end']}")
            print(c["text"])
            shown += 1