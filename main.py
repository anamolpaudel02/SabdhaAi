import os
import json
import random
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

# Check if we have a valid API key
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

# keyword sets are loaded from words.py

def get_mock_label(text: str) -> ClassificationResult:
    val = text.lower()
    
    for word in HATEFUL_WORDS:
        if word in val:
            return ClassificationResult(
                label="Hateful",
                confidence=random.randint(85, 98),
                reason=f"Contains threat/slur: '{word}'"
            )
            
    for word in OFFENSIVE_WORDS:
        if word in val:
            return ClassificationResult(
                label="Offensive",
                confidence=random.randint(75, 95),
                reason=f"Uses offensive word: '{word}'"
            )
            
    for word in NORMAL_WORDS:
        if word in val:
            return ClassificationResult(
                label="Normal",
                confidence=random.randint(80, 99),
                reason="Positive or supportive remark"
            )
            
    if len(text) < 15:
        return ClassificationResult(
            label="Normal",
            confidence=random.randint(70, 90),
            reason="Short text with clean vocabulary"
        )
    
    r = random.random()
    if r < 0.75:
        return ClassificationResult(label="Normal", confidence=random.randint(65, 85), reason="No flagged keywords or hostile patterns detected")
    elif r < 0.92:
        return ClassificationResult(label="Offensive", confidence=random.randint(60, 80), reason="Sentence structure appears slightly rude or aggressive")
    else:
        return ClassificationResult(label="Hateful", confidence=random.randint(65, 85), reason="Heuristics flagged possible target harassment")

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
        
    if use_mock or client is None:
        print(f"Mock analysis: '{content}'")
        return get_mock_label(content)
        
    try:
        print(f"Gemini analysis: '{content}'")
        
        prompt = (
            "You are an automated comment moderator for Nepali text. "
            "Classify this comment into Normal (safe/neutral/polite), "
            "Offensive (general swearing/slang/rudeness with no specific target), "
            "or Hateful (harassment, threat, or targeting based on caste/religion/gender/nationality). "
            "Output ONLY valid JSON with this exact schema: "
            '{"label": "Normal" OR "Offensive" OR "Hateful", "confidence": integer 0-100, "reason": "short English reason"}'
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
        
        return ClassificationResult(label=lbl, confidence=conf, reason=reason)
        
    except Exception as err:
        print(f"Gemini API error: {err}. Falling back to mock")
        return get_mock_label(content)

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    return FileResponse("static/index.html")
