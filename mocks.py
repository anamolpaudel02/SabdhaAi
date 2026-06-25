"""
 Local rule-engine ("Mock Mode") classifier for SabdaAI.

This module wires up the lexicon defined in words.py into an actual
classifier, following the scoring spec already documented in
words.WORD_LIST_METADATA:

    method            : max(matched_word_scores) + multi-hit bonus
    phrase_weight     : 1.0   -> phrases always score at full value
    romanized_bonus   : 0.05  -> small bonus when the match came from a
                                 romanized form (evasion attempt)
    safelist_override : True  -> CONTEXT_SAFE exceptions are skipped
                                 for both word AND phrase hits

SYSTEMIC BUGS FIXED IN THIS VERSION
------------------------------------
1. Unicode NFC normalization  – visually identical Devanagari chars that
   differ only in Unicode encoding now compare equal.
2. Zero-width evasion stripping – ZWJ / ZWNJ / ZWSP inserted between
   characters to break substring matches are removed before scanning.
3. Transliteration space collapse – re.sub wraps replacements in spaces;
   double spaces are now collapsed so multi-word phrase matching still works.
4. Verb-root + obligation-suffix scan – catches conjugation forms the
   lexicon never explicitly lists (e.g. "मार्नु पर्छ", "काटौं",
   "लखेट्नेछ") by matching a known hateful verb ROOT anywhere in the
   text and an obligation/incitement SUFFIX within 30 chars after it.
5. Multi-signal score accumulation – multiple independent hate/offensive
   signals now push the confidence score higher instead of being capped
   at the single loudest term.
6. CONTEXT_SAFE applied to phrase hits as well as word hits.
7. _normalize() actually normalises text instead of only lower-casing.

This runs with no external API / API key required, so the server has a
real offline fallback ("Mock Mode") as advertised in the README, instead
of hard-failing when GEMINI_API_KEY is not set.
"""

import re
import unicodedata

from words import (
    OFFENSIVE_WORDS,
    HATEFUL_WORDS,
    OFFENSIVE_PHRASES,
    HATEFUL_PHRASES,
    ROMANIZED_MAP,
    CONTEXT_SAFE,
)

ROMANIZED_BONUS = 0.05

# ---------------------------------------------------------------------------
# Zero-width / invisible evasion characters people insert to break matches
# U+200B ZERO WIDTH SPACE, U+200C ZWNJ, U+200D ZWJ, U+2060 WORD JOINER,
# U+FEFF BOM / ZERO WIDTH NO-BREAK SPACE
# ---------------------------------------------------------------------------
_ZERO_WIDTH_RE = re.compile(r'[\u200b\u200c\u200d\u2060\ufeff]')

# Multiple-space collapser (used after transliteration inserts spaces)
_MULTI_SPACE_RE = re.compile(r'  +')

# Sort romanized keys longest-first so multi-word forms (e.g. "muji lai")
# are tried before their shorter substrings (e.g. "muji").
_ROMANIZED_KEYS_SORTED = sorted(ROMANIZED_MAP.keys(), key=len, reverse=True)


# ---------------------------------------------------------------------------
# Verb-root + obligation/incitement suffix detection
#
# Problem: the lexicon stores FIRST-PERSON SINGULAR forms ("मार्छु",
# "काट्छु") but real-world hate speech often uses:
#   – obligation forms:   "मार्नु पर्छ"  ("must be killed")
#   – hortative forms:    "मारौं"         ("let's kill")
#   – future/3rd-person:  "मार्नेछ"      ("will kill" / "they will kill")
#   – imperative:         "मारिदे"        ("kill [them]!")
#
# Fix: if a known hateful verb ROOT appears anywhere in the text AND an
# obligation/incitement suffix follows within a 30-character window, the
# sentence is flagged regardless of exact conjugation.
# ---------------------------------------------------------------------------

# Devanagari hateful verb roots → base threat score
_HATEFUL_ROOTS = {
    "मार":    0.90,   # kill / murder
    "काट":    0.88,   # cut / chop
    "पिट":    0.85,   # beat
    "कुट":    0.83,   # beat / thrash
    "जला":    0.85,   # burn
    "लखेट":   0.92,   # expel / chase out
    "खेद":    0.85,   # drive away / chase
    "भगा":    0.88,   # chase away / flee
    "नाश":    0.82,   # destroy
    "ध्वंस":  0.82,   # ruin / destroy
    "सफाया":  0.97,   # elimination / cleansing
    "सखाप":   0.90,   # finish off / obliterate
    "समाप्त": 0.85,   # finish off
    "मेटा":   0.82,   # erase
}

# Obligation / incitement suffixes that turn a root into a call to action.
# Pattern: look for the ROOT, then within 30 chars find one of these suffixes.
_OBLIGATION_SUFFIX_RE = re.compile(
    r"नु\s*पर्"          # "नु पर्छ / पर्ने" — must [verb]
    r"|नु\s*हुन्छ"       # "नु हुन्छ"        — should [verb]
    r"|औं|ऊँ"            # "मारौं"           — let's [verb]  (hortative)
    r"|इदे|इहाल"         # "मारिदे / मारिहाल" — just do it (imperative)
    r"|नेछ|नेछौं"        # "मार्नेछ"         — will [verb] (future)
    r"|नु\s*छ"           # "मार्नु छ"        — have to [verb]
)

# Context window (chars) to look for a suffix after each root
_ROOT_WINDOW = 30


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """
    Clean & normalise text before classification.

    Steps (order matters):
    1. Strip zero-width evasion characters (ZWJ, ZWNJ, ZWSP, etc.)
    2. Apply Unicode NFC normalization so visually identical Devanagari
       characters in different encodings compare equal.
    3. Lower-case (primarily for Latin content).
    4. Strip leading/trailing whitespace.
    """
    text = _ZERO_WIDTH_RE.sub('', text)
    text = unicodedata.normalize('NFC', text)
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

    After substitutions, multiple consecutive spaces are collapsed so that
    multi-word Devanagari phrase matching still works correctly.
    """
    expanded = text_lower
    romanized_hits = set()
    for roman in _ROMANIZED_KEYS_SORTED:
        pattern = r"(?<![a-z0-9])" + re.escape(roman) + r"(?![a-z0-9])"
        if re.search(pattern, expanded):
            expanded = re.sub(pattern, " " + ROMANIZED_MAP[roman] + " ", expanded)
            romanized_hits.add(roman)
    # Collapse any double-spaces introduced by wrapping replacements
    expanded = _MULTI_SPACE_RE.sub(' ', expanded).strip()
    return expanded, romanized_hits


def _scan_phrases(text_lower: str, phrases: list[str]) -> list[str]:
    """Substring scan for known multi-word phrases."""
    hits = []
    for phrase in phrases:
        phrase_l = phrase.lower()
        if phrase_l in text_lower:
            # Apply CONTEXT_SAFE to phrases as well
            if _is_context_safe(text_lower, phrase_l):
                continue
            hits.append(phrase)
    return hits


def _scan_words(text_lower: str, word_scores: dict) -> list[tuple[str, float]]:
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


def _scan_verb_roots(text_lower: str) -> list[tuple[str, float]]:
    """
    Detect hateful verb ROOTS followed by obligation/incitement suffixes
    within a short context window.

    This catches conjugation forms not explicitly listed in HATEFUL_WORDS:
      – "मार्नु पर्छ"   (must kill / must be killed)
      – "मारौं"          (let's kill)
      – "लखेट्नु पर्छ"  (must be expelled)
      – "सफाया गर्नु पर्छ" (must be eliminated)
    etc.
    """
    hits = []
    for root, score in _HATEFUL_ROOTS.items():
        pos = text_lower.find(root)
        while pos != -1:
            window = text_lower[pos: pos + len(root) + _ROOT_WINDOW]
            if _OBLIGATION_SUFFIX_RE.search(window):
                label = f"{root}[+obligation]"
                # Avoid duplicate if already caught by exact-word scan
                if not any(h[0] == label for h in hits):
                    hits.append((label, score))
            pos = text_lower.find(root, pos + 1)
    return hits


def _accumulate_score(scores: list[float], romanized_bonus: float) -> float:
    """
    Convert a list of per-signal scores into a single confidence value.

    Strategy:
    – The strongest single signal dominates (max).
    – Each additional independent signal adds a small bonus (capped at 0.15)
      so that texts with multiple hate signals score higher than those with
      just one marginal hit.
    – The romanized-evasion bonus is applied on top.
    – Result is clamped to [0.0, 1.0].
    """
    if not scores:
        return 0.0
    primary = max(scores)
    extra = len(scores) - 1          # number of additional signals
    multi_bonus = min(0.15, extra * 0.05)
    return min(1.0, primary + multi_bonus + romanized_bonus)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_local(text: str) -> dict:
    """
    Classify text using the local lexicon in words.py.

    Returns a dict: {label, confidence, reason, highlighted_tokens}
    matching the shape expected by ClassificationResult in main.py.
    """
    original_lower = _normalize(text)
    expanded_lower, romanized_hits = _transliterate(original_lower)

    bonus = ROMANIZED_BONUS if romanized_hits else 0.0

    # ---- Hateful: phrases → words → verb-root+suffix ----
    hateful_phrase_hits = _scan_phrases(expanded_lower, HATEFUL_PHRASES)
    hateful_word_hits   = _scan_words(expanded_lower, HATEFUL_WORDS)
    hateful_root_hits   = _scan_verb_roots(expanded_lower)  # NEW: conjugation coverage

    # ---- Offensive: phrases → words ----
    offensive_phrase_hits = _scan_phrases(expanded_lower, OFFENSIVE_PHRASES)
    offensive_word_hits   = _scan_words(expanded_lower, OFFENSIVE_WORDS)

    best_label  = "Normal"
    best_score  = 0.0
    highlighted = []
    reason_bits = []

    if hateful_phrase_hits or hateful_word_hits or hateful_root_hits:
        scores = (
            [1.0 for _ in hateful_phrase_hits]
            + [s for _, s in hateful_word_hits]
            + [s for _, s in hateful_root_hits]
        )
        best_score = _accumulate_score(scores, bonus)
        best_label = "Hateful"
        highlighted = list(dict.fromkeys(
            hateful_phrase_hits
            + [w for w, _ in hateful_word_hits]
            + [w for w, _ in hateful_root_hits]
        ))
        reason_bits.append("matched hateful term(s)")

    elif offensive_phrase_hits or offensive_word_hits:
        scores = (
            [1.0 for _ in offensive_phrase_hits]
            + [s for _, s in offensive_word_hits]
        )
        best_score = _accumulate_score(scores, bonus)
        best_label = "Offensive"
        highlighted = list(dict.fromkeys(
            offensive_phrase_hits + [w for w, _ in offensive_word_hits]
        ))
        reason_bits.append("matched offensive term(s)")

    else:
        best_label = "Normal"
        best_score = 0.85          # reduced from 0.95 — no lexicon hit is
        reason_bits.append("no offensive/hateful terms matched")
        # Note: 0.85 (not 0.95) because the local lexicon has finite coverage;
        # a miss is not as certain as a positive hit. Gemini is the better
        # judge for unknown content when an API key is configured.

    if romanized_hits:
        reason_bits.append(
            "romanized evasion form(s) detected: " + ", ".join(sorted(romanized_hits))
        )

    confidence = int(round(best_score * 100))
    confidence = max(0, min(100, confidence))

    reason = "Local rule engine (Mock Mode): " + "; ".join(reason_bits)

    return {
        "label":              best_label,
        "confidence":         confidence,
        "reason":             reason,
        "highlighted_tokens": highlighted,
    }