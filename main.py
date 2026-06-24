import os
import io
import re
import json
import asyncio
from typing import Literal
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

app = FastAPI(title="SabdaAI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ClassificationResult(BaseModel):
    label: Literal["Normal", "Offensive", "Hateful"]
    confidence: int
    reason: str
    highlighted_tokens: list[str] = []

class AnalyzeRequest(BaseModel):
    text: str

class AnalyzeBatchRequest(BaseModel):
    texts: list[str]

class FeedbackRequest(BaseModel):
    text: str
    predicted: str
    correct: str

class SuggestCleanResponse(BaseModel):
    original: str
    cleaned: str
    changes: str

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = None

if GEMINI_API_KEY:
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        pass

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
        except Exception:
            pass

load_feedback_overrides()

def analyze_text_internal(text: str) -> ClassificationResult:
    content = text.strip()
    if not content:
        raise ValueError("Text cannot be empty")
        
    content_lower = content.lower()
    if content_lower in feedback_overrides:
        corrected_label = feedback_overrides[content_lower]
        return ClassificationResult(
            label=corrected_label,
            confidence=100,
            reason="User corrected label (feedback loop override)",
            highlighted_tokens=[]
        )
        
    if not client:
        raise RuntimeError("Gemini API key is not configured.")
        
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

@app.get("/api/status")
def get_status():
    return {
        "status": "ok",
        "api_configured": client is not None
    }

@app.post("/api/analyze", response_model=ClassificationResult)
async def analyze(request: AnalyzeRequest):
    content = request.text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    try:
        return await run_in_threadpool(analyze_text_internal, content)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        feedback_overrides[text.lower()] = correct
        return {"status": "success", "message": "Feedback saved and override updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save feedback: {str(e)}")

@app.post("/api/suggest-clean", response_model=SuggestCleanResponse)
async def suggest_clean(request: AnalyzeRequest):
    content = request.text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
        
    if not client:
        raise HTTPException(status_code=503, detail="Gemini API key is not configured.")
        
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
        raise HTTPException(status_code=500, detail=str(e))

def _is_devanagari_or_valid(line):
    cleaned = line.strip()
    if len(cleaned) < 3:
        return False
    has_devanagari = bool(re.search(r'[\u0900-\u097F]', cleaned))
    has_latin = bool(re.search(r'[a-zA-Z]{2,}', cleaned))
    return has_devanagari or has_latin

@app.post("/api/analyze-screenshot")
async def analyze_screenshot(file: UploadFile = File(...)):
    if not OCR_AVAILABLE:
        raise HTTPException(status_code=501, detail="OCR engine dependencies are not installed.")
        
    contents = await file.read()
    try:
        image = Image.open(io.BytesIO(contents))
        raw_text = pytesseract.image_to_string(image, lang="nep+eng")
        lines = raw_text.splitlines()
        extracted_lines = [l.strip() for l in lines if _is_devanagari_or_valid(l)]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")

    if not extracted_lines:
        return {"extracted_count": 0, "results": []}

    tasks = [run_in_threadpool(analyze_text_internal, text) for text in extracted_lines]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            processed.append({
                "text": extracted_lines[i],
                "label": "Normal", "confidence": 0,
                "reason": f"Error: {str(res)}", "highlighted_tokens": []
            })
        else:
            processed.append({
                "text": extracted_lines[i],
                "label": res.label,
                "confidence": res.confidence,
                "reason": res.reason,
                "highlighted_tokens": res.highlighted_tokens
            })

    return {
        "extracted_count": len(extracted_lines),
        "results": processed
    }

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    return FileResponse("static/index.html")
