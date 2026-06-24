"""
 Local rule-engine ("Mock Mode") classifier for SabdaAI.

This module wires up the lexicon defined in words.py into an actual
classifier, following the scoring spec already documented in
words.WORD_LIST_METADATA:

    method            : max(matched_word_scores)
    phrase_weight     : 1.0   -> phrases always score at full value
    romanized_bonus   : 0.05  -> small bonus when the match came from a
                                 romanized form (evasion attempt)
    safelist_override : True  -> CONTEXT_SAFE exceptions are skipped

This runs with no external API / API key required, so the server has a
real offline fallback ("Mock Mode") as advertised in the README, instead
of hard-failing when GEMINI_API_KEY is not set.
"""

import re

from words import (
    OFFENSIVE_WORDS,
    HATEFUL_WORDS,
    OFFENSIVE_PHRASES,
    HATEFUL_PHRASES,
    ROMANIZED_MAP,
    CONTEXT_SAFE,
)

ROMANIZED_BONUS = 0.05

# Sort romanized keys longest-first so multi-word forms (e.g. "muji lai")
# are tried before their shorter substrings (e.g. "muji").
_ROMANIZED_KEYS_SORTED = sorted(ROMANIZED_MAP.keys(), key=len, reverse=True)


def _normalize(text: str) -> str:
    return text.lower().strip()


def _is_context_safe(text_lower: str, matched_term: str) -> bool:
    """Check whether matched_term only appears inside a CONTEXT_SAFE exception."""
    safe_phrases = CONTEXT_SAFE.get(matched_term, [])
    if not safe_phrases:
        return False
    # If every occurrence of the term sits inside a known-safe phrase,
    # treat it as safe. We approximate this by checking whether removing
    # the safe phrases from the text removes all occurrences of the term.
    stripped = text_lower
    for safe in safe_phrases:
        stripped = stripped.replace(safe.lower(), " ")
    return matched_term not in stripped


def _transliterate(text_lower: str):
    """
    Replace romanized Nepali terms with their Devanagari equivalents.
    Returns (expanded_text, romanized_hits) where romanized_hits is the
    set of romanized keys that were matched (used for scoring bonus +
    highlighting).
    """
    expanded = text_lower
    romanized_hits = set()
    for roman in _ROMANIZED_KEYS_SORTED:
        pattern = r"(?<![a-z0-9])" + re.escape(roman) + r"(?![a-z0-9])"
        if re.search(pattern, expanded):
            expanded = re.sub(pattern, " " + ROMANIZED_MAP[roman] + " ", expanded)
            romanized_hits.add(roman)
    return expanded, romanized_hits


def _scan_phrases(text_lower: str, phrases: list[str]):
    hits = []
    for phrase in phrases:
        if phrase.lower() in text_lower:
            hits.append(phrase)
    return hits


def _scan_words(text_lower: str, word_scores: dict):
    """Token/substring scan against a {word: score} dict, honoring
    word boundaries for Latin script and plain substring match for
    Devanagari (which has no word-boundary regex support in \\b)."""
    hits = []
    for term, score in word_scores.items():
        is_latin = bool(re.fullmatch(r"[a-zA-Z0-9 '\-]+", term))
        if is_latin:
            pattern = r"(?<![a-zA-Z0-9])" + re.escape(term) + r"(?![a-zA-Z0-9])"
            found = re.search(pattern, text_lower)
        else:
            found = term in text_lower
        if found:
            if _is_context_safe(text_lower, term):
                continue
            hits.append((term, score))
    return hits


def classify_local(text: str) -> dict:
    """
    Classify text using the local lexicon in words.py.

    Returns a dict: {label, confidence, reason, highlighted_tokens}
    matching the shape expected by ClassificationResult in main.py.
    """
    original_lower = _normalize(text)
    expanded_lower, romanized_hits = _transliterate(original_lower)

    # --- Hateful: phrases first (full weight), then words ---
    hateful_phrase_hits = _scan_phrases(expanded_lower, HATEFUL_PHRASES)
    hateful_word_hits = _scan_words(expanded_lower, HATEFUL_WORDS)

    offensive_phrase_hits = _scan_phrases(expanded_lower, OFFENSIVE_PHRASES)
    offensive_word_hits = _scan_words(expanded_lower, OFFENSIVE_WORDS)

    best_label = "Normal"
    best_score = 0.0
    highlighted = []
    reason_bits = []

    if hateful_phrase_hits or hateful_word_hits:
        scores = [1.0 for _ in hateful_phrase_hits] + [s for _, s in hateful_word_hits]
        # Romanized evasion bonus applies if any matched word/phrase
        # came from a transliterated romanized term.
        bonus = ROMANIZED_BONUS if romanized_hits else 0.0
        best_score = min(1.0, max(scores) + bonus)
        best_label = "Hateful"
        highlighted = list(dict.fromkeys(
            hateful_phrase_hits + [w for w, _ in hateful_word_hits]
        ))
        reason_bits.append("matched hateful term(s)")

    elif offensive_phrase_hits or offensive_word_hits:
        scores = [1.0 for _ in offensive_phrase_hits] + [s for _, s in offensive_word_hits]
        bonus = ROMANIZED_BONUS if romanized_hits else 0.0
        best_score = min(1.0, max(scores) + bonus)
        best_label = "Offensive"
        highlighted = list(dict.fromkeys(
            offensive_phrase_hits + [w for w, _ in offensive_word_hits]
        ))
        reason_bits.append("matched offensive term(s)")

    else:
        best_label = "Normal"
        best_score = 0.95
        reason_bits.append("no offensive/hateful terms matched")

    if romanized_hits:
        reason_bits.append(
            "romanized evasion form(s) detected: " + ", ".join(sorted(romanized_hits))
        )

    confidence = int(round(best_score * 100))
    confidence = max(0, min(100, confidence))

    reason = "Local rule engine (Mock Mode): " + "; ".join(reason_bits)

    return {
        "label": best_label,
        "confidence": confidence,
        "reason": reason,
        "highlighted_tokens": highlighted,
    }