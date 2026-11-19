"""Scikit-learn intent classifier (TF-IDF + Logistic Regression) with keyword overrides."""
import logging
import os
import threading

import joblib

logger = logging.getLogger("ava.intent")

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "ml", "artifacts", "intent_model.joblib")

_lock = threading.Lock()
_artifacts = None
_load_failed = False

_KEYWORD_OVERRIDES = [
    ("pricing", ["price", "pricing", "cost", "charge", "charges", "rate", "rates", "fee", "fees"]),
    ("services", ["service", "services", "offer", "do you do", "build"]),
    ("business_hours", ["hour", "hours", "open", "close", "closing", "weekend", "timing", "timings"]),
    ("contact", ["contact", "email", "phone number", "reach", "address", "location", "where are you"]),
]


def _load():
    global _artifacts, _load_failed
    if _artifacts is not None or _load_failed:
        return _artifacts
    with _lock:
        if _artifacts is None and not _load_failed:
            try:
                _artifacts = joblib.load(MODEL_PATH)
            except Exception:  # missing or incompatible file: keyword rules still work
                logger.exception("Intent model could not be loaded from %s", MODEL_PATH)
                _load_failed = True
    return _artifacts


def reload_model():
    global _artifacts, _load_failed
    with _lock:
        _artifacts, _load_failed = None, False
    return _load()


def classify(message: str) -> tuple[str, float]:
    """Raw model output: (intent, confidence 0-1). ("unknown", 0.0) if no model is available."""
    message = (message or "").strip()
    artifacts = _load()
    if not message or not artifacts:
        return "unknown", 0.0
    try:
        if "pipeline" in artifacts:  # version 2: word + char TF-IDF pipeline with probabilities
            probabilities = artifacts["pipeline"].predict_proba([message])[0]
            best = probabilities.argmax()
            intent, confidence = str(artifacts["pipeline"].classes_[best]), float(probabilities[best])
            if confidence < artifacts.get("threshold", 0.4):
                return "unknown", confidence
            return intent, confidence
        # version 1: separate vectorizer and model, no calibrated confidence
        return str(artifacts["model"].predict(artifacts["vectorizer"].transform([message]))[0]), 0.5
    except Exception:
        logger.exception("Intent prediction failed")
        return "unknown", 0.0


def predict_intent(message: str) -> str:
    message = (message or "").strip()
    if not message:
        return "unknown"

    intent, _ = classify(message)

    # Keyword overrides only correct the four topic intents; the newer intents trust the model.
    if intent in {"cancel_appointment", "reschedule_appointment", "complaint", "follow_up", "lead_inquiry"}:
        return intent
    lower = message.lower()
    for name, keywords in _KEYWORD_OVERRIDES:
        if any(k in lower for k in keywords):
            return name
    return intent
