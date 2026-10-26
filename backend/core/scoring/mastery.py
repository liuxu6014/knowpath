def mastery_score(attempts, prior=0.0) -> float:
    """Weighted recent accuracy with bounded 0..1 output."""
    vals = [float(a.get("correct", a.get("score", 0))) for a in (attempts or [])]
    vals = [max(0.0, min(1.0, v / 100 if v > 1 else v)) for v in vals]
    if not vals: return max(0.0, min(1.0, float(prior)))
    weights = list(range(1, len(vals) + 1)); return round(sum(v*w for v,w in zip(vals, weights))/sum(weights), 4)
