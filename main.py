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

from mocks import classify_local

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
        from google import genai  # pylint: disable=import-outside-toplevel
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:  # pylint: disable=broad-exception-caught
        pass

FEEDBACK_FILE = "feedback.jsonl"
SUBMISSIONS_FILE = "submissions.jsonl"
APPROVED_FILE = "approved_data.jsonl"

# Admin password — change this !
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "anamol 1223")

feedback_overrides = {}


def load_feedback_overrides():
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
        except Exception:  # pylint: disable=broad-exception-caught
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

    # Mock Mode: local lexicon-based rule engine (words.py), always
    # available with no API key required. This is the default engine.
    if not client:
        local_result = classify_local(content)
        return ClassificationResult(**local_result)

    # If a Gemini API key is configured, use it as the primary engine,
    # falling back to the local rule engine if the call fails for any
    # reason (network error, bad response, etc.) so analysis never
    # hard-fails when a local fallback is available.
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

        gemini_result = ClassificationResult(label=lbl, confidence=conf, reason=reason, highlighted_tokens=tokens)

        # Cross-check against the local lexicon: if the local engine is
        # confident this is Hateful/Offensive but Gemini said Normal,
        # prefer the stricter local result rather than silently missing
        # known slurs/threats (this is what caused "muji" to slip through
        # while "kill" was caught - Gemini's judgement alone is not
        # consistent across known terms already curated in words.py).
        local_result = classify_local(content)
        severity = {"Normal": 0, "Offensive": 1, "Hateful": 2}
        if severity[local_result["label"]] > severity[gemini_result.label]:
            return ClassificationResult(**local_result)

        return gemini_result
    except Exception:  # pylint: disable=broad-exception-caught
        local_result = classify_local(content)
        return ClassificationResult(**local_result)

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
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.post("/api/analyze-batch")
async def analyze_batch(request: AnalyzeBatchRequest):
    if not request.texts:
        raise HTTPException(status_code=400, detail="Texts list cannot be empty")
    if len(request.texts) > 500:
        raise HTTPException(status_code=400, detail="Cannot analyze more than 500 texts at once")
    
    tasks = [run_in_threadpool(analyze_text_internal, text) for text in request.texts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    processed_results = []
    for _, res in enumerate(results):
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
        raise HTTPException(status_code=500, detail=f"Failed to save feedback: {str(e)}") from e

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
        raise HTTPException(status_code=500, detail=str(e)) from e

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
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}") from e

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

@app.get("/admin")
def admin_page():
    return FileResponse("static/admin.html")

@app.get("/demo")
def demo_page():
    return FileResponse("static/demo.html")


# ─────────────────────────────────────────────────────────────
# CONTRIBUTION PIPELINE
# ─────────────────────────────────────────────────────────────

class ContributeRequest(BaseModel):
    text: str
    suggested_label: Literal["Normal", "Offensive", "Hateful"]
    note: str = ""          # optional context note from contributor

class ReviewRequest(BaseModel):
    submission_id: str
    action: Literal["approve", "reject"]
    final_label: Literal["Normal", "Offensive", "Hateful"] = "Normal"
    admin_note: str = ""

def _check_admin(request_password: str):
    """Raise 401 if admin password is wrong."""
    if request_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized: wrong admin password")


@app.post("/api/contribute")
async def contribute(request: ContributeRequest):
    """
    Public endpoint — anyone can submit a text sample with a suggested label.
    The submission is saved to submissions.jsonl for admin review.
    """
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    if len(text) > 1000:
        raise HTTPException(status_code=400, detail="Text too long (max 1000 chars)")

    import uuid, datetime
    entry = {
        "id":              str(uuid.uuid4()),
        "text":            text,
        "suggested_label": request.suggested_label,
        "note":            request.note.strip()[:500],
        "submitted_at":    datetime.datetime.utcnow().isoformat() + "Z",
        "status":          "pending",   # pending | approved | rejected
    }
    try:
        with open(SUBMISSIONS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {"status": "success", "message": "Thank you! Your submission is under review."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save submission: {str(e)}") from e


@app.get("/api/admin/submissions")
def admin_list_submissions(
    password: str = "",
    status_filter: str = "pending"
):
    """Admin-only: list all submissions, filtered by status."""
    _check_admin(password)
    results = []
    if os.path.exists(SUBMISSIONS_FILE):
        with open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if status_filter == "all" or entry.get("status") == status_filter:
                        results.append(entry)
                except json.JSONDecodeError:
                    continue
    # Newest first
    results.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
    return {"total": len(results), "submissions": results}


@app.post("/api/admin/review")
async def admin_review(request: ReviewRequest, password: str = ""):
    """
    Admin-only: approve or reject a pending submission.
    Approved entries are also saved to approved_data.jsonl.
    """
    _check_admin(password)

    if not os.path.exists(SUBMISSIONS_FILE):
        raise HTTPException(status_code=404, detail="No submissions file found")

    # Read all, find & update the target entry
    lines = []
    found = False
    import datetime
    with open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("id") == request.submission_id:
                    found = True
                    entry["status"]       = request.action + "d"   # "approved" or "rejected"
                    entry["final_label"]  = request.final_label
                    entry["admin_note"]   = request.admin_note
                    entry["reviewed_at"]  = datetime.datetime.utcnow().isoformat() + "Z"
                    if request.action == "approve":
                        # Also write to approved_data.jsonl
                        approved_entry = {
                            "text":        entry["text"],
                            "label":       request.final_label,
                            "source":      "community",
                            "approved_at": entry["reviewed_at"],
                        }
                        with open(APPROVED_FILE, "a", encoding="utf-8") as af:
                            af.write(json.dumps(approved_entry, ensure_ascii=False) + "\n")
                lines.append(json.dumps(entry, ensure_ascii=False))
            except json.JSONDecodeError:
                lines.append(line)

    if not found:
        raise HTTPException(status_code=404, detail="Submission ID not found")

    # Rewrite the submissions file with updated status
    with open(SUBMISSIONS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return {"status": "success", "action": request.action + "d", "id": request.submission_id}


@app.get("/api/admin/export")
def admin_export(password: str = "", file_format: str = "json"):
    """
    Admin-only: download all approved submissions as JSON or CSV.
    """
    _check_admin(password)
    approved = []
    if os.path.exists(APPROVED_FILE):
        with open(APPROVED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        approved.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    if file_format == "csv":
        import csv, io as _io
        output = _io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["text", "label", "source", "approved_at"])
        writer.writeheader()
        writer.writerows(approved)
        from fastapi.responses import Response
        return Response(
            content=output.getvalue().encode("utf-8"),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=sabdaai_approved_data.csv"}
        )

    # Default: JSON
    from fastapi.responses import Response
    return Response(
        content=json.dumps(approved, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=sabdaai_approved_data.json"}
    )

@app.get("/api/admin/stats")
def admin_stats(password: str = ""):
    """Admin-only: quick stats about submission pipeline."""
    _check_admin(password)
    counts = {"pending": 0, "approved": 0, "rejected": 0, "total": 0}
    if os.path.exists(SUBMISSIONS_FILE):
        with open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    status = entry.get("status", "pending")
                    if status in counts:
                        counts[status] += 1
                    counts["total"] += 1
                except json.JSONDecodeError:
                    continue
    approved_count = 0
    if os.path.exists(APPROVED_FILE):
        with open(APPROVED_FILE, "r", encoding="utf-8") as f:
            approved_count = sum(1 for line in f if line.strip())
    counts["approved_data_entries"] = approved_count
    return counts
