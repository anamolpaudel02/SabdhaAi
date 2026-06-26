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
    ("Fishing (Devanagari)", "म माछा मार्छु"),
    ("Threat (Devanagari)", "म तिमीलाई मार्छु"),
    ("Killed it (English)", "you killed it bro"),
    ("Kill threat (English)", "i will kill you"),
    ("Fishing (Romanized)", "ma machha marchu"),
    ("Killed threat (English)", "i will get you killed"),
    ("Bug context (English)", "kill the bug"),
    ("Mosquito threat root (Nepali)", "लामखुट्टे मार्नु पर्छ"),
    ("Negation (English)", "do not kill him"),
    ("Negation (Nepali)", "तिमीलाई मार्ने होइन"),
    ("Cut grass (Benign)", "घाँस काट्नु पर्छ"),
    ("Cut person (Threat)", "तिमीलाई काट्नु पर्छ"),
    ("Burn fire (Benign)", "आगो जलाउनु पर्दैन"),
    ("Burn person (Threat)", "तिमीलाई जलाउनु पर्छ"),
    ("Finish game (Benign)", "खेल खत्तम गर्छु"),
    ("Finish person (Threat)", "तिमीलाई खत्म गर्छु"),
]

for desc, text in tests:
    r = mocks.classify_local(text)
    label = r["label"]
    conf = r["confidence"]
    hits = r["highlighted_tokens"][:2] if r["highlighted_tokens"] else []
    print(f"{desc[:45]:<47} | {label:<10} | {conf:>3}% | {hits}")
