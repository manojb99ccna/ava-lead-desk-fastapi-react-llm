"""FAQ retrieval with TF-IDF.

Two vectorizers are combined:
- word-level TF-IDF (the original matching), good for well-spelled questions;
- character n-gram TF-IDF, which tolerates spelling mistakes ("bussiness hrs").
"""
from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..models import AvaBusinessFAQ

WORD_THRESHOLD = 0.20  # original threshold of the rule-based matcher
CHAR_THRESHOLD = 0.45


def _scores(corpus: list[str], query: str) -> tuple[list[float], list[float]]:
    docs = corpus + [query]
    word, char = [0.0] * len(corpus), [0.0] * len(corpus)
    try:
        m = TfidfVectorizer().fit_transform(docs)
        word = cosine_similarity(m[-1], m[:-1]).flatten().tolist()
    except ValueError:  # empty vocabulary, e.g. only stop words or symbols
        pass
    try:
        m = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit_transform(docs)
        char = cosine_similarity(m[-1], m[:-1]).flatten().tolist()
    except ValueError:
        pass
    return word, char


def search_faq(db: Session, query: str, limit: int = 3) -> list[dict]:
    """Returns the best matching active FAQs with scores, highest first."""
    query = (query or "").strip()
    if not query:
        return []
    faqs = db.query(AvaBusinessFAQ).filter(AvaBusinessFAQ.is_active.is_(True)).all()
    if not faqs:
        return []

    word, char = _scores([f"{f.question} {f.intent.replace('_', ' ')}" for f in faqs], query)
    results = []
    for i, faq in enumerate(faqs):
        results.append({
            "id": faq.id,
            "intent": faq.intent,
            "question": faq.question,
            "answer": faq.answer,
            "score": round(max(word[i], char[i] * (WORD_THRESHOLD / CHAR_THRESHOLD)), 3),
            "confident": word[i] >= WORD_THRESHOLD or char[i] >= CHAR_THRESHOLD,
        })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


def best_answer(db: Session, query: str) -> str | None:
    """The single confident answer used by the rule-based engine, or None."""
    results = search_faq(db, query, limit=1)
    if results and results[0]["confident"]:
        return results[0]["answer"]
    return None
