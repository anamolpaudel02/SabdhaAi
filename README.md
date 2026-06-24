# SabdhaAi-

SabdaAI is a real-time safety moderator, text analysis platform, and browser extension designed for Nepali text (Devanagari and romanized). It classifies comments into **Normal**, **Offensive**, or **Hateful**, identifies targeted harassment, and provides features like feedback loops, screenshot OCR analysis, and text sanitization suggestions.

## Features

- **Text Safety Classification**: Categorizes comments into Normal, Offensive, or Hateful with confidence levels.
- **Context-Aware Sentiment**: Uses lexical lists and custom context mappings to filter false positives.
- **Screenshot OCR Analyzer**: Extracts text from images and runs batch safety moderation.
- **Polite Text Sanitization**: Recommends friendly, clean alternatives to offensive/hateful input.
- **Interactive Web Dashboard**: Features single analysis, bulk CSV uploads with visual charts, and a real-time feedback loop.
- **Chrome Extension**: Scans web content (e.g., social media feeds) and highlights offensive elements on-the-fly.

---

## Installation & Setup

### 1. Set Up the Virtual Environment
Create and activate a python virtual environment, then install dependencies:

```bash
# On Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# On macOS/Linux
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure the Gemini API (Optional)
By default, the server runs in **Mock Mode** using localized rule engines. To enable live Gemini AI classifications:

- Set the `GEMINI_API_KEY` environment variable in your terminal before running the server:

```powershell
# Windows PowerShell
$env:GEMINI_API_KEY="your_api_key_here"

# Windows Command Prompt
set GEMINI_API_KEY=your_api_key_here

# macOS/Linux
export GEMINI_API_KEY="your_api_key_here"
```

---

## Running the Application

### 1. Start the FastAPI Backend Server
Run the application using Uvicorn:

```bash
uvicorn main:app --reload --port 8000
```
The server will start at `http://localhost:8000`.

### 2. Access the Dashboard
Navigate to `http://localhost:8000` in your web browser. From here you can:
- Perform single comment checks.
- Upload `.csv` files for batch classification and interactive charts.
- Flag bad predictions to write corrections to the feedback loop (`feedback.jsonl`).

---

## Chrome Browser Extension

To enable safety shielding directly in your browser:
1. Open Google Chrome and navigate to `chrome://extensions/`.
2. Turn on **Developer mode** (top-right toggle).
3. Click **Load unpacked** (top-left button).
4. Select the `extension` folder located inside this project directory.
5. The extension will automatically scan and moderate relevant social media comments on sites like Instagram.
