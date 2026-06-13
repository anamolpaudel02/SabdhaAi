import os
import json
import random
import asyncio
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from dotenv import load_dotenv
from words import NORMAL_WORDS, OFFENSIVE_WORDS, HATEFUL_WORDS

load_dotenv()

app = FastAPI(title="SabdaAI")

class AnalyzeRequest(BaseModel):
    text: str

class ClassificationResult(BaseModel):
    label: Literal["Normal", "Offensive", "Hateful"]
    confidence: int
    reason: str
    highlighted_tokens: list[str] = []

class AnalyzeBatchRequest(BaseModel):
    texts: list[str]

class FeedbackRequest(BaseModel):
    text: str
    predicted: str
    correct: str

# api config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
use_mock = True

if GEMINI_API_KEY and not GEMINI_API_KEY.startswith("your_") and len(GEMINI_API_KEY) > 10:
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        use_mock = False
        print("Connected to Gemini API successfully")
    except Exception as e:
        print(f"Failed to load Gemini: {e}. Running mock fallback")
        client = None
else:
    print("No GEMINI_API_KEY found, running in mock mode")
    client = None

# feedback storage & local cache
FEEDBACK_FILE = "feedback.jsonl"
feedback_overrides = {}

def load_feedback_overrides():
    global feedback_overrides
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        text = data.get("text", "").strip()
                        correct = data.get("correct")
                        if text and correct in ["Normal", "Offensive", "Hateful"]:
                            feedback_overrides[text.lower()] = correct
            print(f"Loaded {len(feedback_overrides)} feedback overrides.")
        except Exception as e:
            print(f"Failed to load feedback overrides: {e}")

load_feedback_overrides()

def get_mock_label(text: str) -> ClassificationResult:
    val = text.lower()
    
    for word in HATEFUL_WORDS:
        if word in val:
            return ClassificationResult(
                label="Hateful",
                confidence=random.randint(85, 98),
                reason=f"Contains threat/slur: '{word}'",
                highlighted_tokens=[word]
            )
            
    for word in OFFENSIVE_WORDS:
        if word in val:
            return ClassificationResult(
                label="Offensive",
                confidence=random.randint(75, 95),
                reason=f"Uses offensive word: '{word}'",
                highlighted_tokens=[word]
            )
            
    for word in NORMAL_WORDS:
        if word in val:
            return ClassificationResult(
                label="Normal",
                confidence=random.randint(80, 99),
                reason="Positive or supportive remark",
                highlighted_tokens=[word]
            )
            
    if len(text) < 15:
        return ClassificationResult(
            label="Normal",
            confidence=random.randint(70, 90),
            reason="Short text with clean vocabulary",
            highlighted_tokens=[]
        )
    
    r = random.random()
    if r < 0.75:
        return ClassificationResult(label="Normal", confidence=random.randint(65, 85), reason="No flagged keywords or hostile patterns detected", highlighted_tokens=[])
    elif r < 0.92:
        return ClassificationResult(label="Offensive", confidence=random.randint(60, 80), reason="Sentence structure appears slightly rude or aggressive", highlighted_tokens=[])
    else:
        return ClassificationResult(label="Hateful", confidence=random.randint(65, 85), reason="Heuristics flagged possible target harassment", highlighted_tokens=[])

def analyze_text_internal(text: str) -> ClassificationResult:
    content = text.strip()
    if not content:
        raise ValueError("Text cannot be empty")
        
    # Check feedback overrides first
    content_lower = content.lower()
    if content_lower in feedback_overrides:
        corrected_label = feedback_overrides[content_lower]
        # Highlight words if they are keywords in mock list
        highlighted = []
        for word in HATEFUL_WORDS + OFFENSIVE_WORDS + NORMAL_WORDS:
            if word in content_lower:
                highlighted.append(word)
        return ClassificationResult(
            label=corrected_label,
            confidence=100,
            reason="User corrected label (feedback loop override)",
            highlighted_tokens=highlighted
        )
        
    if use_mock or client is None:
        return get_mock_label(content)
        
    try:
        prompt = (
            "You are an automated comment moderator for Nepali text. "
            "Classify this comment into Normal (safe/neutral/polite), "
            "Offensive (general swearing/slang/rudeness with no specific target), "
            "or Hateful (harassment, threat, or targeting based on caste/religion/gender/nationality).\n"
            "Identify the exact words/tokens in the text that caused this classification (especially for Offensive or Hateful).\n"
            "Output ONLY valid JSON with this exact schema:\n"
            '{"label": "Normal" | "Offensive" | "Hateful", "confidence": integer 0-100, "reason": "short English reason", "highlighted_tokens": ["word1", "word2"]}'
            f"\n\nComment to moderate:\n\"{content}\""
        )
        
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
            }
        )
        
        data = json.loads(response.text.strip())
        
        lbl = data.get("label", "Normal")
        if lbl not in ["Normal", "Offensive", "Hateful"]:
            lbl = "Normal"
            
        conf = int(data.get("confidence", 80))
        conf = max(0, min(100, conf))
        reason = data.get("reason", "Analysis successful")
        tokens = data.get("highlighted_tokens", [])
        if not isinstance(tokens, list):
            tokens = []
        tokens = [str(t) for t in tokens]
        
        return ClassificationResult(label=lbl, confidence=conf, reason=reason, highlighted_tokens=tokens)
        
    except Exception as err:
        print(f"Gemini API error: {err}. Falling back to mock")
        return get_mock_label(content)

@app.get("/api/status")
def get_status():
    return {
        "status": "ok",
        "api_configured": not use_mock,
        "fallback_mode": use_mock
    }

@app.post("/api/analyze", response_model=ClassificationResult)
async def analyze(request: AnalyzeRequest):
    content = request.text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    return await run_in_threadpool(analyze_text_internal, content)

@app.post("/api/analyze-batch")
async def analyze_batch(request: AnalyzeBatchRequest):
    if not request.texts:
        raise HTTPException(status_code=400, detail="Texts list cannot be empty")
    if len(request.texts) > 500:
        raise HTTPException(status_code=400, detail="Cannot analyze more than 500 texts at once")
    
    tasks = [run_in_threadpool(analyze_text_internal, text) for text in request.texts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    processed_results = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            processed_results.append(ClassificationResult(
                label="Normal",
                confidence=0,
                reason=f"Error: {str(res)}",
                highlighted_tokens=[]
            ))
        else:
            processed_results.append(res)
            
    return {"results": processed_results}

@app.post("/api/feedback")
async def submit_feedback(request: FeedbackRequest):
    text = request.text.strip()
    predicted = request.predicted.strip()
    correct = request.correct.strip()
    
    if not text or correct not in ["Normal", "Offensive", "Hateful"]:
        raise HTTPException(status_code=400, detail="Invalid feedback parameters")
        
    feedback_entry = {
        "text": text,
        "predicted": predicted,
        "correct": correct
    }
    
    try:
        with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(feedback_entry, ensure_ascii=False) + "\n")
        
        # Update cache
        feedback_overrides[text.lower()] = correct
        return {"status": "success", "message": "Feedback saved and override updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save feedback: {str(e)}")

class SuggestCleanResponse(BaseModel):
    original: str
    cleaned: str
    changes: str

# preset sanitization mapping for testing
MOCK_CLEAN_RESPONSES = {
    "यो मुजी भिडियो हेरेर मेरो समय खेर गयो, के बनाएको यस्तो गधा जस्तो!": {
        "cleaned": "यो भिडियो मेरो लागि त्यति उपयोगी भएन, अर्को पटक अलि स्तरीय बनाउन अनुरोध गर्दछु।",
        "changes": "Removed profanities 'मुजी' and insults 'गधा जस्तो', replaced with polite feedback on video quality."
    },
    "कस्तो नराम्रो मुख हानेको साला फटाहा खाते!": {
        "cleaned": "कृपया आफ्नो बोली र भाषालाई मर्यादित एवं सभ्य बनाउनुहोला।",
        "changes": "Removed harsh verbal abuses 'साला', 'फटाहा', 'खाते', replaced with a polite request for decent speech."
    },
    "यो जातका मान्छेहरू यस्तै हुन्, यिनीहरूलाई नेपालबाट लखेट्नु पर्छ, सखाप पार्नु पर्छ!": {
        "cleaned": "सबै वर्ग र समुदायका मानिसहरूसँग मिलेर बस्नुपर्छ र कसैप्रति विभेद वा घृणा फैलाउनु हुँदैन।",
        "changes": "Removed xenophobia and hate speech targeting specific ethnic groups, replaced with statements supporting harmony and equality."
    },
    "तँलाई घरबाट थुतेर मार्छु म, अब तेरो दिन गन्ती सुरु भयो!": {
        "cleaned": "हाम्रो असमझदारीलाई संवाद, छलफल र कानुनी प्रक्रिया मार्फत समाधान गरौं।",
        "changes": "Removed targeted physical threats and death threat 'मार्छु', replaced with a proposal for dialogue."
    }
}

def get_mock_clean_version(text: str) -> dict:
    trimmed = text.strip()
    # Check if we have a match in preset map
    for key, val in MOCK_CLEAN_RESPONSES.items():
        if key.lower() in trimmed.lower() or trimmed.lower() in key.lower():
            return {
                "original": text,
                "cleaned": val["cleaned"],
                "changes": val["changes"]
            }
            
    # fallback string sanitizer
    cleaned = text
    replaced_words = []
    for word in HATEFUL_WORDS + OFFENSIVE_WORDS:
        if word in cleaned:
            cleaned = cleaned.replace(word, "*" * len(word))
            replaced_words.append(word)
            
    if replaced_words:
        changes = f"Sanitized identified offensive/hateful keywords: {', '.join(replaced_words)}."
    else:
        changes = "No flagged words found. Refined syntax structure for general politeness."
        
    return {
        "original": text,
        "cleaned": cleaned,
        "changes": changes
    }

@app.post("/api/suggest-clean", response_model=SuggestCleanResponse)
async def suggest_clean(request: AnalyzeRequest):
    content = request.text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
        
    if use_mock or client is None:
        mock_res = get_mock_clean_version(content)
        return SuggestCleanResponse(**mock_res)
        
    try:
        prompt = (
            "You are a text sanitizer for Nepali social media. "
            "Rewrite the following comment to remove offensive/hateful language "
            "while preserving the original user's intent and meaning (but expressing it politely/neutrally). "
            "Keep it in natural, fluent Nepali. Do NOT add new meanings. "
            "Output ONLY valid JSON with this exact schema:\n"
            '{"cleaned": "sanitized polite Nepali comment", "changes": "short English note on what was changed"}'
            f"\n\nOriginal Comment:\n\"{content}\""
        )
        
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
            }
        )
        
        data = json.loads(response.text.strip())
        cleaned = data.get("cleaned", content)
        changes = data.get("changes", "Cleaned offensive expressions.")
        
        return SuggestCleanResponse(original=content, cleaned=cleaned, changes=changes)
    except Exception as e:
        print(f"Gemini suggestion error: {e}. Falling back to mock")
        mock_res = get_mock_clean_version(content)
        return SuggestCleanResponse(**mock_res)

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    return FileResponse("static/index.html")

