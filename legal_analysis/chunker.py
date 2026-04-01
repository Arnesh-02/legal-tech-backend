# chunker.py
import nltk
from nltk.tokenize import sent_tokenize
nltk.download('punkt', quiet=True)

def chunk_text(text, approx_words_per_chunk=900, overlap_words=150):
    sents = sent_tokenize(text)
    chunks = []
    cur = []
    cur_len = 0
    for sent in sents:
        words = len(sent.split())
        if cur_len + words > approx_words_per_chunk and cur:
            chunks.append(" ".join(cur))
            # keep some overlap sentences (approx)
            # approximation: keep last N sentences proportional to overlap_words
            keep = []
            k = 0
            for s in reversed(cur):
                k += len(s.split())
                keep.insert(0, s)
                if k >= overlap_words:
                    break
            cur = keep.copy()
            cur_len = sum(len(s.split()) for s in cur)
        cur.append(sent)
        cur_len += words
    if cur:
        chunks.append(" ".join(cur))
    return chunks

