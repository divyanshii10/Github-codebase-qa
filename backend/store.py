import chromadb

client = chromadb.PersistentClient(path="index")   # saved in the 'index' folder


def save_chunks(repo_id, chunks):
    try:
        client.delete_collection(repo_id)   # re-indexing replaces only THIS repo
    except Exception:
        pass
    col = client.create_collection(repo_id)

    # add in batches so big repos don't overload Chroma
    batch = 500
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        col.add(
            ids=[str(i + j) for j in range(len(part))],
            documents=[c["text"] for c in part],
            metadatas=[c["meta"] for c in part],
        )


def search(repo_id, question, n=5):
    col = client.get_collection(repo_id)
    res = col.query(query_texts=[question], n_results=n)
    return list(zip(res["documents"][0], res["metadatas"][0]))


if __name__ == "__main__":
    import sys
    from ingest import clone_repo, list_files
    from chunker import chunk_repo

    root, rid = clone_repo(sys.argv[1])
    chunks = chunk_repo(root, list(list_files(root)))
    save_chunks(rid, chunks)
    print(f"Saved {len(chunks)} chunks for {rid}")

    questions = [
        "how does signing work",
        "what happens when a signature is wrong",
        "how are timestamps checked",
    ]
    for q in questions:
        print(f"\nQUESTION: {q}")
        for doc, meta in search(rid, q, n=3):
            print(f"  {meta['path']}:{meta['start']}-{meta['end']}")