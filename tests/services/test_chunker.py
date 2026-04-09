from app.services.chunker import DocumentChunker


def test_basic_split():
    text = "A" * 2500
    chunker = DocumentChunker(chunk_size=1000, overlap=200)
    chunks = chunker.split(text)
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c["chunk_text"]) <= 1000


def test_chunk_index_sequential():
    text = "word " * 500
    chunker = DocumentChunker(chunk_size=500, overlap=100)
    chunks = chunker.split(text)
    indices = [c["chunk_index"] for c in chunks]
    assert indices == list(range(len(chunks)))


def test_content_hash_stable():
    text = "stable text " * 100
    chunker = DocumentChunker()
    c1 = chunker.split(text)
    c2 = chunker.split(text)
    assert [c["content_hash"] for c in c1] == [c["content_hash"] for c in c2]


def test_dedup_different_inputs():
    chunker = DocumentChunker(chunk_size=500, overlap=0)
    chunks_a = chunker.split("text A " * 200)
    chunks_b = chunker.split("text B " * 200)
    hashes_a = {c["content_hash"] for c in chunks_a}
    hashes_b = {c["content_hash"] for c in chunks_b}
    assert hashes_a.isdisjoint(hashes_b)


def test_empty_text():
    chunker = DocumentChunker()
    chunks = chunker.split("   ")
    assert chunks == []
