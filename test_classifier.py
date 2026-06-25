import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import mocks

tests = [
    ("Original failing sentence", "यो जातका मान्छेहरू यस्तै हुन्, यिनीहरूलाई नेपालबाट लखेट्नु पर्छ, सखाप पार्नु पर्छ!"),
    ("Normal greeting", "नमस्ते, तपाईंलाई कस्तो छ? आज मौसम राम्रो छ।"),
    ("Benign hurt/harm English", "i didn't mean to hurt your feelings, no harm done."),
    ("Direct kill threat (1st person)", "मार्छु तिमीलाई"),
    ("Hortative — let us kill", "मारौं यिनीहरूलाई"),
    ("Kill obligation form", "मार्नु पर्छ यिनीहरूलाई"),
    ("ZWJ evasion in kill verb", "मार\u200d्छु"),
    ("Burn hortative", "जलाऔं यिनीहरूको घर"),
    ("Beat obligation", "पिट्नु पर्छ"),
    ("Expel from Nepal", "नेपालबाट लखेट्नु पर्छ"),
    ("Sakhap obligation", "सखाप पार्नु पर्छ"),
    ("Eliminate group", "सफाया गर्नु पर्छ"),
    ("Future kill 3rd person", "मार्नेछ उसलाई"),
    ("Casual English kill context", "this will kill the vibe"),
    ("Offensive insult", "मूर्ख केटो"),
]

for desc, text in tests:
    r = mocks.classify_local(text)
    label = r["label"]
    conf = r["confidence"]
    hits = r["highlighted_tokens"][:2] if r["highlighted_tokens"] else []
    print(f"{desc[:45]:<47} | {label:<10} | {conf:>3}% | {hits}")
