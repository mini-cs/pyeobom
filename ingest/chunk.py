def chunk_pages(pages: list[tuple[int, str]], max_chars: int = 800, overlap: int = 100) -> list[tuple[int, str]]:
    chunks = []
    for page, text in pages:
        text = text.strip()
        start = 0
        while text:  # 조각은 쪽을 넘지 않는다
            chunks.append((page, text[start:start + max_chars]))
            if start + max_chars >= len(text):
                break
            start += max_chars - overlap
    return chunks
