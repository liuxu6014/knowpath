import math, re

def _vec(s):
    return re.findall(r"[a-z0-9_+#.-]+|[\u4e00-\u9fff]", str(s).lower())

def search(query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
    q = _vec(query); qset = set(q)
    scored = []
    for i, d in enumerate(documents or []):
        toks = _vec(d.get("text", d.get("content", d.get("title", ""))))
        overlap = len(qset.intersection(toks)); score = overlap / math.sqrt(max(1, len(qset)*len(set(toks))))
        if score: scored.append((score, i, d))
    return [{**d, "score": round(score, 6)} for score, _, d in sorted(scored, reverse=True)[:max(1, int(top_k))]]
