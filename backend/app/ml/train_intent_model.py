"""Trains Ava's intent classifier.

Training data comes from the table ava_sys_intent_training_examples:
  source='generated' (from generate_intent_data.py --to-db) and source='manual' (added by people,
  weighted x3). If the table is empty, app/ml/data/intent_dataset.csv is used instead.

Model: word n-grams (1-2) + character n-grams (2-5, tolerant of typos) -> TF-IDF -> Logistic Regression.
Evaluated on a held-out 10% split and on the hand-written set app/ml/data/intent_eval.csv.

    python -m app.ml.train_intent_model            # train from the database, evaluate, save
    python -m app.ml.train_intent_model --no-db    # train from the CSV file only
"""
import argparse
import csv
import os
import time

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline

HERE = os.path.dirname(__file__)
DATASET = os.path.join(HERE, "data", "intent_dataset.csv")
EVAL_SET = os.path.join(HERE, "data", "intent_eval.csv")
MODEL_PATH = os.path.join(HERE, "artifacts", "intent_model.joblib")
CONFIDENCE_THRESHOLD = 0.40  # below this the intent is reported as "unknown"


def read_csv(path: str) -> tuple[list[str], list[str]]:
    texts, labels = [], []
    if not os.path.exists(path):
        return texts, labels
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("text") and row.get("intent"):
                texts.append(row["text"])
                labels.append(row["intent"])
    return texts, labels


def load_db_examples() -> tuple[list[str], list[str], int]:
    """Returns (texts, labels, manual_count); manual examples are repeated 3x as weighting."""
    from app.database import SessionLocal
    from app.models import AvaSysIntent, AvaSysIntentTrainingExample

    db = SessionLocal()
    try:
        rows = (
            db.query(AvaSysIntentTrainingExample.text, AvaSysIntentTrainingExample.source, AvaSysIntent.name)
            .join(AvaSysIntent, AvaSysIntent.id == AvaSysIntentTrainingExample.intent_id)
            .filter(AvaSysIntent.is_active.is_(True), AvaSysIntentTrainingExample.is_active.is_(True))
            .all()
        )
    finally:
        db.close()
    texts, labels, manual = [], [], 0
    for text, source, name in rows:
        repeat = 3 if source == "manual" else 1
        manual += source == "manual"
        texts += [text] * repeat
        labels += [name] * repeat
    return texts, labels, manual


def build_pipeline() -> Pipeline:
    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, lowercase=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True,
                                 lowercase=True, max_features=150_000)),
    ])
    return Pipeline([("features", features), ("clf", LogisticRegression(max_iter=2000, C=4.0))])


def train(use_db: bool = True) -> dict:
    texts, labels = [], []
    if use_db:
        try:
            texts, labels, manual = load_db_examples()
            print(f"Database examples: {len(texts) - 2 * manual} ({manual} manual, weighted x3)")
        except Exception as exc:
            print(f"Database not available ({type(exc).__name__}); using the CSV file")
    if not texts:
        texts, labels = read_csv(DATASET)
        print(f"CSV examples: {len(texts)}")
    if len(set(labels)) < 2:
        raise SystemExit("Not enough training data. Run: python -m app.ml.generate_intent_data")

    x_train, x_test, y_train, y_test = train_test_split(texts, labels, test_size=0.1, random_state=7,
                                                        stratify=labels)
    started = time.time()
    pipeline = build_pipeline().fit(x_train, y_train)
    print(f"Trained on {len(x_train)} examples in {time.time() - started:.1f}s")

    split_acc = accuracy_score(y_test, pipeline.predict(x_test))
    print(f"\nHeld-out split accuracy (synthetic, optimistic): {split_acc:.3f}")

    report = {"split_accuracy": split_acc}
    eval_texts, eval_labels = read_csv(EVAL_SET)
    if eval_texts:
        predicted = pipeline.predict(eval_texts)
        eval_acc = accuracy_score(eval_labels, predicted)
        report["eval_accuracy"] = eval_acc
        print(f"Hand-written eval accuracy (realistic): {eval_acc:.3f}  ({len(eval_texts)} messages)\n")
        print(classification_report(eval_labels, predicted, zero_division=0))
        for text, want, got in zip(eval_texts, eval_labels, predicted):
            if want != got:
                print(f"  MISS  {want:22s} -> {got:22s} | {text}")

    # Final model uses all data.
    pipeline = build_pipeline().fit(texts, labels)
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump({"version": 2, "pipeline": pipeline, "threshold": CONFIDENCE_THRESHOLD,
                 "intents": sorted(set(labels))}, MODEL_PATH, compress=3)
    print(f"\nSaved model to {MODEL_PATH} ({os.path.getsize(MODEL_PATH) / 1e6:.1f} MB)")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-db", action="store_true")
    args = parser.parse_args()
    train(use_db=not args.no_db)
