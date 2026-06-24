// ─────────────────────────────────────────────────────────────────────────────
// SabdaAI — app.js  (Premium Features v2)
// Features: OCR, Diff View, Live Danger Score, Paste+Submit,
//           Flagged Words Chart, Safe-to-Post Verdict
// ─────────────────────────────────────────────────────────────────────────────

// Counters
let total = 0, normal = 0, offensive = 0, hateful = 0;

// Elements
const input = document.getElementById('comment-input');
const ctr = document.getElementById('char-count');
const form = document.getElementById('analyze-form');
const btn = document.getElementById('submit-btn');
const badge = document.getElementById('status-badge');
const results = document.getElementById('results');
const emptyState = document.getElementById('empty-state');

// Stat elements
const sTotal = document.getElementById('stat-total');
const sNormal = document.getElementById('stat-normal');
const sOffensive = document.getElementById('stat-offensive');
const sHateful = document.getElementById('stat-hateful');

// CSV Batch variables
let parsedTexts = [];
let currentCsvFile = null;
let batchResults = [];
let doughnutChart = null;
let barChart = null;
let flaggedWordsChart = null;

// ── Feature 3: Live Danger Score keyword sets (client-side) ──────────────────
const DANGER_HATEFUL = [
    'मार्छु','काट्छु','मार्ने','काट्ने','मरोस्','सखाप','धोती','भते','मर्स्या','जाठो',
    'hate','kill','destroy','scum','die'
];
const DANGER_OFFENSIVE = [
    'मुजी','खाते','रन्डी','गधा','मूर्ख','बदमास','फटाहा','साला','कुरूप','धत्','तेरो',
    'stupid','idiot','vulgar','nonsense'
];

// ── Boot ─────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
    checkStatus();

    input.addEventListener('input', () => {
        const n = input.value.length;
        ctr.textContent = n;
        ctr.style.color = n >= 450 ? '#fb4d6d' : n >= 350 ? '#fbbf24' : '#4b5a72';

        // Feature 3: update live danger score
        updateDangerScore(input.value);
    });

    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            await runAnalysis();
        });
    }

    // Initialize CSV upload
    initCsvUpload();
    // Initialize OCR upload (Feature 1)
    initOcrUpload();
});

// ── Feature 3: Live Danger Score ─────────────────────────────────────────────
function updateDangerScore(text) {
    const val = text.toLowerCase();
    const dangerBar = document.getElementById('danger-bar');
    const dangerLabel = document.getElementById('danger-label');
    if (!dangerBar || !dangerLabel) return;

    const isHateful = DANGER_HATEFUL.some(w => val.includes(w));
    const isOffensive = DANGER_OFFENSIVE.some(w => val.includes(w));

    if (!val.trim()) {
        input.style.background = 'rgba(0,0,0,0.28)';
        input.style.borderColor = 'var(--border)';
        input.style.boxShadow = '';
        dangerBar.className = 'danger-bar';
        dangerLabel.textContent = '🟢 Safe';
    } else if (isHateful) {
        input.style.background = 'rgba(251,77,109,0.07)';
        input.style.borderColor = 'rgba(251,77,109,0.5)';
        input.style.boxShadow = '0 0 0 3px rgba(251,77,109,0.12), inset 0 0 30px rgba(251,77,109,0.04)';
        dangerBar.className = 'danger-bar danger-hateful';
        dangerLabel.textContent = '🔴 High Danger';
    } else if (isOffensive) {
        input.style.background = 'rgba(251,191,36,0.07)';
        input.style.borderColor = 'rgba(251,191,36,0.5)';
        input.style.boxShadow = '0 0 0 3px rgba(251,191,36,0.12), inset 0 0 30px rgba(251,191,36,0.04)';
        dangerBar.className = 'danger-bar danger-offensive';
        dangerLabel.textContent = '🟡 Caution';
    } else {
        input.style.background = 'rgba(0,0,0,0.28)';
        input.style.borderColor = 'var(--border)';
        input.style.boxShadow = '';
        dangerBar.className = 'danger-bar';
        dangerLabel.textContent = '🟢 Safe';
    }
}

// ── Feature 4: Paste & Analyze ───────────────────────────────────────────────
window.pasteAndAnalyze = async function() {
    try {
        const text = await navigator.clipboard.readText();
        if (!text.trim()) { alert('Clipboard is empty!'); return; }
        input.value = text.trim();
        ctr.textContent = input.value.length;
        updateDangerScore(input.value);
        await runAnalysis();
    } catch (err) {
        // Fallback for browsers that block clipboard without user gesture on http
        alert('Clipboard access denied. Please paste manually (Ctrl+V) then click Analyze.');
    }
};

// ── Core analysis runner ──────────────────────────────────────────────────────
async function runAnalysis() {
    const msg = input.value.trim();
    if (!msg) return;

    btn.classList.add('loading');
    btn.disabled = true;

    try {
        const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: msg })
        });
        if (!res.ok) throw new Error('API error');
        const data = await res.json();
        data.text = msg;
        addCard(data);
        input.value = '';
        ctr.textContent = '0';
        ctr.style.color = '#4b5a72';
        updateDangerScore('');
    } catch (err) {
        console.error(err);
        alert('Backend unreachable. Make sure uvicorn is running.');
    } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

// ── Status check ─────────────────────────────────────────────────────────────
async function checkStatus() {
    try {
        const r = await fetch('/api/status');
        const d = await r.json();
        const lbl = badge.querySelector('.status-label');
        badge.className = 'status-pill';
        if (d.api_configured && !d.fallback_mode) {
            badge.classList.add('live');
            lbl.textContent = 'Gemini API Live';
        } else {
            badge.classList.add('mock');
            lbl.textContent = 'Mock Mode';
        }
    } catch {
        badge.className = 'status-pill mock';
        badge.querySelector('.status-label').textContent = 'Offline';
    }
}

// ── Tab switch ────────────────────────────────────────────────────────────────
window.switchTab = function(name, el) {
    document.querySelectorAll('.tp').forEach(x => x.classList.remove('on'));
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('on'));
    document.getElementById(`tab-${name}`).classList.add('on');
    el.classList.add('on');
};

// ── Load a preset into the textarea ──────────────────────────────────────────
window.load = function(text) {
    input.value = text;
    ctr.textContent = text.length;
    updateDangerScore(text);
    switchTab('single', document.getElementById('tab-btn-single'));
    input.focus();
};

// ── Highlight flagged words ───────────────────────────────────────────────────
function highlightTokens(text, tokens, labelClass) {
    if (!tokens || tokens.length === 0) return esc(text);
    let escapedText = esc(text);

    // Sort by length desc to prevent substring issues
    const sortedTokens = [...tokens].sort((a, b) => b.length - a.length);

    for (const token of sortedTokens) {
        if (!token.trim()) continue;
        const escToken = esc(token);
        try {
            const regex = new RegExp(`(${escapeRegExp(escToken)})`, 'gi');
            escapedText = escapedText.replace(regex, `<mark class="tok-${labelClass}">$1</mark>`);
        } catch(e) {
            console.error(e);
        }
    }
    return escapedText;
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// ── Feature 2: Word-level Diff Computation ────────────────────────────────────
function computeWordDiff(original, cleaned) {
    const origWords = original.trim().split(/\s+/);
    const cleanWords = cleaned.trim().split(/\s+/);

    // Build a simple LCS-based diff
    const m = origWords.length;
    const n = cleanWords.length;
    const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));

    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            if (origWords[i - 1] === cleanWords[j - 1]) {
                dp[i][j] = dp[i - 1][j - 1] + 1;
            } else {
                dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
            }
        }
    }

    // Trace back to build diff tokens
    const diffTokens = [];
    let i = m, j = n;
    while (i > 0 || j > 0) {
        if (i > 0 && j > 0 && origWords[i - 1] === cleanWords[j - 1]) {
            diffTokens.unshift({ word: origWords[i - 1], type: 'same' });
            i--; j--;
        } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
            diffTokens.unshift({ word: cleanWords[j - 1], type: 'added' });
            j--;
        } else {
            diffTokens.unshift({ word: origWords[i - 1], type: 'removed' });
            i--;
        }
    }

    return diffTokens;
}

function renderDiffHTML(diffTokens) {
    return diffTokens.map(token => {
        if (token.type === 'removed') {
            return `<del class="diff-removed">${esc(token.word)}</del>`;
        } else if (token.type === 'added') {
            return `<ins class="diff-added">${esc(token.word)}</ins>`;
        } else {
            return esc(token.word);
        }
    }).join(' ');
}

// ── Transliteration map ───────────────────────────────────────────────────────
function romanizeNepali(text) {
    const vowels = {
        'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo', 'ऋ': 'ri',
        'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au', 'अं': 'am', 'अः': 'ah'
    };
    const matras = {
        'ा': 'aa', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo', 'ृ': 'ri',
        'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au', 'ं': 'm', 'ः': 'h', 'ँ': 'an'
    };
    const consonants = {
        'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng',
        'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'yn',
        'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
        'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
        'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm',
        'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'w', 'श': 'sh', 'ष': 'sh', 'स': 's', 'ह': 'h',
        'क्ष': 'ksh', 'त्र': 'tr', 'ज्ञ': 'gy'
    };
    const halant = '्';

    let result = '';
    let i = 0;
    while (i < text.length) {
        let char = text[i];

        if (consonants[char]) {
            let base = consonants[char];
            let nextChar = text[i + 1];

            if (nextChar === halant) {
                result += base;
                i += 2;
            } else if (nextChar && matras[nextChar]) {
                result += base + matras[nextChar];
                i += 2;
            } else {
                let futureChar = text[i + 1];
                let isLast = !futureChar || futureChar === ' ' || /[\s\.,\/#!$%\^&\*;:{}=\-_`~()?]/.test(futureChar);
                result += base + (isLast ? '' : 'a');
                i += 1;
            }
        } else if (vowels[char]) {
            result += vowels[char];
            i += 1;
        } else if (matras[char]) {
            result += matras[char];
            i += 1;
        } else {
            result += char;
            i += 1;
        }
    }
    return result;
}

window.toggleRoman = function(btn) {
    const parent = btn.parentElement;
    const textEl = parent.querySelector('.roman-text');
    if (textEl.style.display === 'none') {
        textEl.style.display = 'block';
        btn.textContent = '🔤 Hide Phonetic English';
    } else {
        textEl.style.display = 'none';
        btn.textContent = '🔤 Show Phonetic English';
    }
};

// ── Feature 6: Safe-to-Post verdict helpers ───────────────────────────────────
function getVerdict(label) {
    if (label === 'Normal') {
        return {
            cls: 'verdict-safe',
            icon: '✅',
            title: 'SAFE TO POST',
            msg: 'This comment complies with community safety guidelines.'
        };
    } else if (label === 'Offensive') {
        return {
            cls: 'verdict-warn',
            icon: '⚠️',
            title: 'POTENTIAL VIOLATION',
            msg: 'Contains vulgarity or slang. Use with caution.'
        };
    } else {
        return {
            cls: 'verdict-danger',
            icon: '❌',
            title: 'VIOLATION DETECTED',
            msg: 'Violates hate speech policies against target groups. Do not post.'
        };
    }
}

// ── Card rendering ────────────────────────────────────────────────────────────
function addCard(res) {
    total++;
    const lc = res.label.toLowerCase();
    if (lc === 'normal') normal++;
    else if (lc === 'offensive') offensive++;
    else hateful++;

    sTotal.textContent = total;
    sNormal.textContent = normal;
    sOffensive.textContent = offensive;
    sHateful.textContent = hateful;

    emptyState.style.display = 'none';

    const shortClass = lc === 'normal' ? 'rn' : lc === 'offensive' ? 'ro' : 'rh';
    const verdict = getVerdict(res.label);

    const card = document.createElement('div');
    card.className = `rcard ${shortClass}`;
    card.dataset.text = res.text;
    card.dataset.predicted = res.label;
    card.innerHTML = `
        <!-- Feature 6: Safe-to-Post Verdict Banner -->
        <div class="verdict-banner ${verdict.cls}">
            <span class="verdict-icon">${verdict.icon}</span>
            <div class="verdict-text">
                <span class="verdict-title">${verdict.title}</span>
                <span class="verdict-msg">${verdict.msg}</span>
            </div>
        </div>

        <div class="rcard-top">
            <span class="rbadge ${shortClass}">${res.label}</span>
            <div class="conf">
                <span>${res.confidence}% confidence</span>
                <div class="conf-bar-wrap">
                    <div class="conf-fill ${shortClass}" style="width:${res.confidence}%"></div>
                </div>
            </div>
        </div>
        <div class="rcomment">${highlightTokens(res.text, res.highlighted_tokens, lc)}</div>
        
        <div class="roman-row">
            <button class="roman-toggle" onclick="toggleRoman(this)">🔤 Show Phonetic English</button>
            <div class="roman-text" style="display: none;">${esc(romanizeNepali(res.text))}</div>
        </div>

        <div class="rreason">
            <span class="rlabel">Why:</span>
            <span>${esc(res.reason)}</span>
        </div>

        <div class="rcard-footer">
            <div class="footer-btn-row">
                <button class="feedback-down-btn" onclick="toggleFeedbackWidget(this)">
                    <span>👎 Correct AI prediction</span>
                </button>
                ${(lc === 'offensive' || lc === 'hateful') ? `
                <button class="suggest-clean-btn" onclick="suggestClean(this)">
                    <span>✨ Suggest Clean Version</span>
                </button>
                ` : ''}
            </div>
            <div class="feedback-widget" style="display: none;">
                <span class="feedback-widget-title">Correction:</span>
                <div class="feedback-choices">
                    <button class="choice-btn c-normal" onclick="submitFeedback(this, 'Normal')">Normal</button>
                    <button class="choice-btn c-offensive" onclick="submitFeedback(this, 'Offensive')">Offensive</button>
                    <button class="choice-btn c-hateful" onclick="submitFeedback(this, 'Hateful')">Hateful</button>
                </div>
            </div>
            <div class="suggest-clean-panel" style="display: none;"></div>
        </div>
    `;
    results.insertBefore(card, results.firstChild);
}

// ── Feedback & correction loop ────────────────────────────────────────────────
window.toggleFeedbackWidget = function(btn) {
    const parent = btn.parentElement;
    const widget = parent.querySelector('.feedback-widget');
    if (widget.style.display === 'none') {
        widget.style.display = 'flex';
        btn.classList.add('active');
    } else {
        widget.style.display = 'none';
        btn.classList.remove('active');
    }
};

window.submitFeedback = async function(btn, correctLabel) {
    const card = btn.closest('.rcard');
    const text = card.dataset.text;
    const predicted = card.dataset.predicted;

    const choiceButtons = card.querySelectorAll('.choice-btn');
    choiceButtons.forEach(b => b.disabled = true);

    try {
        const res = await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, predicted, correct: correctLabel })
        });

        if (!res.ok) throw new Error('Feedback submission failed');

        const widget = card.querySelector('.feedback-widget');
        widget.innerHTML = `<span class="feedback-success">✅ Saved to training loop! Override live.</span>`;

        if (predicted !== correctLabel) {
            updateStatsAfterCorrection(predicted, correctLabel);
            const lc = correctLabel.toLowerCase();
            const shortClass = lc === 'normal' ? 'rn' : lc === 'offensive' ? 'ro' : 'rh';
            const verdict = getVerdict(correctLabel);

            card.className = `rcard ${shortClass}`;
            const rbadge = card.querySelector('.rbadge');
            const fill = card.querySelector('.conf-fill');
            if (rbadge) { rbadge.className = `rbadge ${shortClass}`; rbadge.textContent = correctLabel; }
            if (fill) { fill.className = `conf-fill ${shortClass}`; fill.style.width = '100%'; }
            const confSpan = card.querySelector('.conf span');
            if (confSpan) confSpan.textContent = '100% confidence';

            // Update verdict banner
            const banner = card.querySelector('.verdict-banner');
            if (banner) {
                banner.className = `verdict-banner ${verdict.cls}`;
                banner.querySelector('.verdict-icon').textContent = verdict.icon;
                banner.querySelector('.verdict-title').textContent = verdict.title;
                banner.querySelector('.verdict-msg').textContent = verdict.msg;
            }

            card.dataset.predicted = correctLabel;
        }
    } catch (err) {
        console.error(err);
        alert('Could not submit feedback to server.');
        choiceButtons.forEach(b => b.disabled = false);
    }
};

function updateStatsAfterCorrection(oldLabel, newLabel) {
    const oldLc = oldLabel.toLowerCase();
    const newLc = newLabel.toLowerCase();

    if (oldLc === newLc) return;

    if (oldLc === 'normal') normal--;
    else if (oldLc === 'offensive') offensive--;
    else hateful--;

    if (newLc === 'normal') normal++;
    else if (newLc === 'offensive') offensive++;
    else hateful++;

    sNormal.textContent = normal;
    sOffensive.textContent = offensive;
    sHateful.textContent = hateful;
    sTotal.textContent = total;
}

window.clearAll = function() {
    total = normal = offensive = hateful = 0;
    sTotal.textContent = sNormal.textContent = sOffensive.textContent = sHateful.textContent = 0;
    results.innerHTML = '';
    emptyState.style.display = 'flex';
};

// ── CSV Batch Analysis & Charts ───────────────────────────────────────────────
function initCsvUpload() {
    const dropZone = document.getElementById('csv-drop-zone');
    const fileInput = document.getElementById('csv-file-input');
    const csvInfo = document.getElementById('csv-info');
    const csvFilename = document.getElementById('csv-filename');
    const csvRowcount = document.getElementById('csv-rowcount');
    const csvProcessBtn = document.getElementById('csv-process-btn');

    if (!dropZone) return;

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleCsvFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (fileInput.files.length) {
            handleCsvFile(fileInput.files[0]);
        }
    });

    function handleCsvFile(file) {
        if (!file.name.endsWith('.csv')) {
            alert('Please select a valid CSV file.');
            return;
        }
        currentCsvFile = file;
        csvFilename.textContent = file.name;

        const reader = new FileReader();
        reader.onload = function(e) {
            const text = e.target.result;
            parsedTexts = parseCSV(text);
            csvRowcount.textContent = `${parsedTexts.length} comments detected`;
            csvInfo.style.display = 'block';
        };
        reader.readAsText(file);
    }

    csvProcessBtn.addEventListener('click', async () => {
        if (parsedTexts.length === 0) return;

        csvProcessBtn.classList.add('loading');
        csvProcessBtn.disabled = true;

        try {
            const res = await fetch('/api/analyze-batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ texts: parsedTexts })
            });

            if (!res.ok) throw new Error('API error');
            const data = await res.json();
            openCsvDashboard(currentCsvFile.name, data.results);
        } catch (err) {
            console.error(err);
            alert('Failed to process batch. Make sure backend is running.');
        } finally {
            csvProcessBtn.classList.remove('loading');
            csvProcessBtn.disabled = false;
        }
    });
}

// ── Feature 1: Screenshot OCR Upload ─────────────────────────────────────────
function initOcrUpload() {
    const dropZone = document.getElementById('ocr-drop-zone');
    const fileInput = document.getElementById('ocr-file-input');
    const ocrInfo = document.getElementById('ocr-info');
    const ocrFilename = document.getElementById('ocr-filename');
    const ocrImgSize = document.getElementById('ocr-imgsize');
    const ocrProcessBtn = document.getElementById('ocr-process-btn');
    const ocrSkeleton = document.getElementById('ocr-skeleton');

    if (!dropZone) return;

    let selectedImageFile = null;

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) handleImageFile(e.dataTransfer.files[0]);
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) handleImageFile(fileInput.files[0]);
    });

    function handleImageFile(file) {
        if (!file.type.startsWith('image/')) {
            alert('Please select a valid image file (PNG, JPG, WEBP).');
            return;
        }
        selectedImageFile = file;
        ocrFilename.textContent = file.name;
        ocrImgSize.textContent = `${(file.size / 1024).toFixed(1)} KB — ready to scan`;
        ocrInfo.style.display = 'block';
    }

    ocrProcessBtn.addEventListener('click', async () => {
        if (!selectedImageFile) return;

        ocrProcessBtn.classList.add('loading');
        ocrProcessBtn.disabled = true;
        if (ocrSkeleton) { ocrSkeleton.style.display = 'block'; }

        try {
            const formData = new FormData();
            formData.append('file', selectedImageFile);

            const res = await fetch('/api/analyze-screenshot', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) throw new Error('OCR API error');
            const data = await res.json();

            if (ocrSkeleton) ocrSkeleton.style.display = 'none';

            // Open batch dashboard with extracted results
            // Build parsedTexts and batchResults for OCR
            parsedTexts = data.results.map(r => r.text);
            openCsvDashboard(
                `📷 ${selectedImageFile.name} (${data.extracted_count} lines extracted)`,
                data.results,
                data.ocr_notice
            );
        } catch (err) {
            console.error(err);
            alert('Failed to process screenshot. Make sure backend is running.');
            if (ocrSkeleton) ocrSkeleton.style.display = 'none';
        } finally {
            ocrProcessBtn.classList.remove('loading');
            ocrProcessBtn.disabled = false;
        }
    });
}

function parseCSV(text) {
    const lines = [];
    let row = [""];
    let inQuotes = false;

    for (let i = 0; i < text.length; i++) {
        let char = text[i];
        let nextChar = text[i+1];

        if (char === '"') {
            if (inQuotes && nextChar === '"') {
                row[row.length - 1] += '"';
                i++;
            } else {
                inQuotes = !inQuotes;
            }
        } else if (char === ',' && !inQuotes) {
            row.push('');
        } else if ((char === '\r' || char === '\n') && !inQuotes) {
            if (char === '\r' && nextChar === '\n') {
                i++;
            }
            lines.push(row);
            row = [''];
        } else {
            row[row.length - 1] += char;
        }
    }
    if (row.length > 1 || row[0] !== '') {
        lines.push(row);
    }

    let mapped = lines.map(r => r[0] ? r[0].trim() : '').filter(txt => txt.length > 0);

    // Check header
    const headers = ['comment', 'text', 'message', 'body', 'content', 'post', 'nepali', 'input', 'pratikriya', 'sabda'];
    if (mapped.length > 0 && headers.includes(mapped[0].toLowerCase())) {
        mapped.shift();
    }

    return mapped;
}

window.openCsvDashboard = function(filename, results, ocrNotice = null) {
    batchResults = results.map((r, index) => {
        return {
            text: r.text || parsedTexts[index] || '',
            label: r.label,
            confidence: r.confidence,
            reason: r.reason,
            highlighted_tokens: r.highlighted_tokens
        };
    });

    document.getElementById('modal-filename').textContent = filename;
    document.getElementById('modal-total-count').textContent = batchResults.length;
    document.getElementById('modal-search').value = '';
    document.getElementById('modal-filter-label').value = 'all';

    // Show OCR notice if applicable
    let noticeEl = document.getElementById('ocr-modal-notice');
    if (noticeEl) noticeEl.remove();
    if (ocrNotice) {
        noticeEl = document.createElement('div');
        noticeEl.id = 'ocr-modal-notice';
        noticeEl.className = 'ocr-notice';
        noticeEl.innerHTML = `<span>⚠️ ${esc(ocrNotice)}</span>`;
        document.querySelector('.modal-body').prepend(noticeEl);
    }

    document.getElementById('csv-modal').classList.add('open');

    renderCsvTable(batchResults);
    renderCharts(batchResults);
};

window.closeCsvModal = function() {
    document.getElementById('csv-modal').classList.remove('open');
};

window.renderCsvTable = function(items) {
    const tbody = document.getElementById('csv-table-body');
    tbody.innerHTML = '';

    items.forEach((item, index) => {
        const tr = document.createElement('tr');
        const badgeClass = item.label.toLowerCase() === 'normal' ? 'rn' : item.label.toLowerCase() === 'offensive' ? 'ro' : 'rh';
        const verdict = getVerdict(item.label);

        const dispText = highlightTokens(item.text, item.highlighted_tokens, item.label.toLowerCase());
        const romanText = romanizeNepali(item.text);
        const highlightsStr = item.highlighted_tokens && item.highlighted_tokens.length > 0
            ? item.highlighted_tokens.map(t => `<code class="tok-tag ${badgeClass}">${esc(t)}</code>`).join(' ')
            : `<span style="color:var(--text-3); font-style: italic;">None</span>`;

        tr.innerHTML = `
            <td>${index + 1}</td>
            <td class="cell-text">${dispText}</td>
            <td class="cell-roman">${esc(romanText)}</td>
            <td>
                <span class="rbadge ${badgeClass}">${item.label}</span>
                <span class="table-verdict-badge ${verdict.cls}-sm" title="${verdict.msg}">${verdict.icon}</span>
            </td>
            <td><span class="conf-pct">${item.confidence}%</span></td>
            <td class="cell-details">
                <div class="cell-reason">${esc(item.reason)}</div>
                <div class="cell-highlights">${highlightsStr}</div>
            </td>
        `;
        tbody.appendChild(tr);
    });
};

window.filterCsvTable = function() {
    const searchQuery = document.getElementById('modal-search').value.toLowerCase();
    const filterLabel = document.getElementById('modal-filter-label').value;

    const filtered = batchResults.filter(item => {
        const matchesSearch = item.text.toLowerCase().includes(searchQuery);
        const matchesLabel = filterLabel === 'all' || item.label.toLowerCase() === filterLabel;
        return matchesSearch && matchesLabel;
    });

    renderCsvTable(filtered);
};

// ── Feature 5: Most Flagged Words Chart ──────────────────────────────────────
function computeFlaggedWordFrequency(data) {
    const freq = {};
    data.forEach(item => {
        if (item.highlighted_tokens && item.highlighted_tokens.length > 0) {
            item.highlighted_tokens.forEach(token => {
                const t = token.trim().toLowerCase();
                if (t) freq[t] = (freq[t] || 0) + 1;
            });
        }
    });
    // Sort by frequency descending, take top 10
    return Object.entries(freq)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10);
}

function renderCharts(data) {
    const counts = { Normal: 0, Offensive: 0, Hateful: 0 };
    const confidences = { Normal: [], Offensive: [], Hateful: [] };

    data.forEach(item => {
        counts[item.label]++;
        confidences[item.label].push(item.confidence);
    });

    const avgConf = {
        Normal: confidences.Normal.length ? Math.round(confidences.Normal.reduce((a, b) => a + b, 0) / confidences.Normal.length) : 0,
        Offensive: confidences.Offensive.length ? Math.round(confidences.Offensive.reduce((a, b) => a + b, 0) / confidences.Offensive.length) : 0,
        Hateful: confidences.Hateful.length ? Math.round(confidences.Hateful.reduce((a, b) => a + b, 0) / confidences.Hateful.length) : 0,
    };

    // 1. Doughnut Chart
    const ctxDoughnut = document.getElementById('chart-doughnut').getContext('2d');
    if (doughnutChart) doughnutChart.destroy();
    doughnutChart = new Chart(ctxDoughnut, {
        type: 'doughnut',
        data: {
            labels: ['Normal', 'Offensive', 'Hateful'],
            datasets: [{
                data: [counts.Normal, counts.Offensive, counts.Hateful],
                backgroundColor: ['#22d3a5', '#fbbf24', '#fb4d6d'],
                borderWidth: 1,
                borderColor: '#141b30'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#eef2ff', font: { family: 'Inter', size: 11 } }
                }
            }
        }
    });

    // 2. Bar Chart (Avg Confidence)
    const ctxBar = document.getElementById('chart-bar').getContext('2d');
    if (barChart) barChart.destroy();
    barChart = new Chart(ctxBar, {
        type: 'bar',
        data: {
            labels: ['Normal', 'Offensive', 'Hateful'],
            datasets: [{
                label: 'Avg Confidence (%)',
                data: [avgConf.Normal, avgConf.Offensive, avgConf.Hateful],
                backgroundColor: ['rgba(34, 211, 165, 0.75)', 'rgba(251, 191, 36, 0.75)', 'rgba(251, 77, 109, 0.75)'],
                borderColor: ['#22d3a5', '#fbbf24', '#fb4d6d'],
                borderWidth: 1.5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            scales: {
                x: {
                    min: 0, max: 100,
                    grid: { color: 'rgba(255,255,255,0.06)' },
                    ticks: { color: '#8b9ab8', font: { family: 'Inter' } }
                },
                y: {
                    grid: { display: false },
                    ticks: { color: '#eef2ff', font: { family: 'Inter', weight: 'bold' } }
                }
            },
            plugins: { legend: { display: false } }
        }
    });

    // 3. Feature 5: Top 10 Flagged Words Chart
    const topWords = computeFlaggedWordFrequency(data);
    const flaggedContainer = document.getElementById('chart-flagged-words');
    const flaggedEmpty = document.getElementById('chart-flagged-empty');

    if (flaggedWordsChart) flaggedWordsChart.destroy();

    if (topWords.length === 0) {
        flaggedContainer.style.display = 'none';
        if (flaggedEmpty) flaggedEmpty.style.display = 'block';
    } else {
        flaggedContainer.style.display = 'block';
        if (flaggedEmpty) flaggedEmpty.style.display = 'none';

        const ctxFlagged = flaggedContainer.getContext('2d');

        // Colour each bar based on danger level
        const barColors = topWords.map(([word]) => {
            if (DANGER_HATEFUL.includes(word)) return 'rgba(251, 77, 109, 0.8)';
            if (DANGER_OFFENSIVE.includes(word)) return 'rgba(251, 191, 36, 0.8)';
            return 'rgba(139, 154, 184, 0.7)';
        });
        const borderColors = topWords.map(([word]) => {
            if (DANGER_HATEFUL.includes(word)) return '#fb4d6d';
            if (DANGER_OFFENSIVE.includes(word)) return '#fbbf24';
            return '#8b9ab8';
        });

        flaggedWordsChart = new Chart(ctxFlagged, {
            type: 'bar',
            data: {
                labels: topWords.map(([w]) => w),
                datasets: [{
                    label: 'Occurrences',
                    data: topWords.map(([, c]) => c),
                    backgroundColor: barColors,
                    borderColor: borderColors,
                    borderWidth: 1.5,
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                scales: {
                    x: {
                        grid: { color: 'rgba(255,255,255,0.06)' },
                        ticks: { color: '#8b9ab8', font: { family: 'Inter' }, stepSize: 1 }
                    },
                    y: {
                        grid: { display: false },
                        ticks: { color: '#eef2ff', font: { family: 'Inter', size: 12, weight: '600' } }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => ` ${ctx.raw} occurrence${ctx.raw !== 1 ? 's' : ''}`
                        }
                    }
                }
            }
        });
    }
}

window.exportCsvResults = function() {
    if (batchResults.length === 0) return;

    let csvContent = "data:text/csv;charset=utf-8,";
    csvContent += "Index,Comment,Romanized,Classification,Confidence,Reason,Trigger Words\r\n";

    batchResults.forEach((item, index) => {
        const indexStr = (index + 1).toString();
        const textStr = `"${item.text.replace(/"/g, '""')}"`;
        const romanStr = `"${romanizeNepali(item.text).replace(/"/g, '""')}"`;
        const labelStr = `"${item.label}"`;
        const confStr = `"${item.confidence}%"`;
        const reasonStr = `"${(item.reason || '').replace(/"/g, '""')}"`;
        const highlightsStr = `"${(item.highlighted_tokens || []).join(', ').replace(/"/g, '""')}"`;

        csvContent += `${indexStr},${textStr},${romanStr},${labelStr},${confStr},${reasonStr},${highlightsStr}\r\n`;
    });

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);

    const originalName = currentCsvFile ? currentCsvFile.name.replace('.csv', '') : 'batch';
    link.setAttribute("download", `${originalName}_sabdaai_results.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
};

function esc(s) {
    return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Feature 2: Suggest Clean + Diff View ─────────────────────────────────────
window.suggestClean = async function(btn) {
    const card = btn.closest('.rcard');
    const text = card.dataset.text;
    const panel = card.querySelector('.suggest-clean-panel');

    btn.disabled = true;
    const originalContent = btn.innerHTML;
    btn.innerHTML = '<span>✨ Cleaning...</span>';

    try {
        const res = await fetch('/api/suggest-clean', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });

        if (!res.ok) throw new Error('Failed to get clean suggestion');
        const data = await res.json();

        // Feature 2: Compute word-level diff
        const diffTokens = computeWordDiff(data.original, data.cleaned);
        const diffHTML = renderDiffHTML(diffTokens);

        panel.style.display = 'block';
        panel.innerHTML = `
            <div class="clean-box">
                <div class="clean-header">
                    <span class="clean-badge">✨ Sanitized Suggestion</span>
                    <button class="copy-clean-btn" onclick="copyCleanText(this, ${JSON.stringify(data.cleaned)})">Copy</button>
                </div>
                <div class="clean-txt">"${esc(data.cleaned)}"</div>

                <!-- Feature 2: Side-by-side diff view -->
                <div class="diff-section">
                    <div class="diff-title">📝 What Changed</div>
                    <div class="diff-cards">
                        <div class="diff-card diff-original">
                            <div class="diff-card-label">Original</div>
                            <div class="diff-card-body">${renderDiffHTML(
                                diffTokens.map(t => ({ word: t.word, type: t.type === 'added' ? 'same' : t.type }))
                            )}</div>
                        </div>
                        <div class="diff-card diff-cleaned">
                            <div class="diff-card-label">Cleaned</div>
                            <div class="diff-card-body">${renderDiffHTML(
                                diffTokens.map(t => ({ word: t.word, type: t.type === 'removed' ? 'same' : t.type }))
                            )}</div>
                        </div>
                    </div>
                </div>

                <div class="clean-changes">
                    <strong>Changes:</strong> ${esc(data.changes)}
                </div>
            </div>
        `;
        btn.style.display = 'none';
    } catch (err) {
        console.error(err);
        alert('Could not generate clean version.');
        btn.disabled = false;
        btn.innerHTML = originalContent;
    }
};

window.copyCleanText = function(btn, text) {
    navigator.clipboard.writeText(text).then(() => {
        const originalText = btn.textContent;
        btn.textContent = 'Copied!';
        btn.style.background = 'rgba(34, 211, 165, 0.15)';
        btn.style.color = 'var(--green)';
        setTimeout(() => {
            btn.textContent = originalText;
            btn.style.background = '';
            btn.style.color = '';
        }, 2000);
    }).catch(err => {
        console.error('Copy failed', err);
    });
};
