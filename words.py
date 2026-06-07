# words.py
# ─────────────────────────────────────────────────────────────────────────────
# Keyword lists used by the SabdaAI mock classifier.
# Add, remove, or edit words here without touching main.py.
# ─────────────────────────────────────────────────────────────────────────────

NORMAL_WORDS = [
    # Nepali ma
    "राम्रो", "धन्यवाद", "उत्कृष्ट", "बधाई", "शुभकामना",
    "सुन्दर", "सफा", "मिठो",
    # English ma 
    "good", "great", "nice", "love", "congrats",
]

OFFENSIVE_WORDS = [
    # Nepali ma 
    "तेरो", "मुजी", "खाते", "रन्डी", "गधा",
    "मूर्ख", "बदमास", "फटाहा", "साला", "कुरूप", "धत्",
    # English ma
    "stupid", "idiot", "vulgar", "nonsense",
]

HATEFUL_WORDS = [
    # Nepali ma
    "मार्छु", "काट्छु", "मार्ने", "काट्ने", "मरोस्",
    "सखाप", "धोती", "भते", "मर्स्या", "जाठो",
    # English ma
    "hate", "kill", "destroy", "scum", "die",
]
