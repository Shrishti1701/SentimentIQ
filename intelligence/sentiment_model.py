"""Aspect sentiment model interface; FinBERT is a candidate, not configured."""


def analyze_aspect(text: str, aspect: str) -> dict[str, object]:
    """Classify sentiment with evidence (TODO: implement and evaluate ABSA)."""
    raise NotImplementedError("Sentiment inference is not implemented")
