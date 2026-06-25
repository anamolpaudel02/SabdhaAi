const BACKEND_URL = 'http://localhost:8000';
let stats = { scanned: 0, offensive: 0, hateful: 0, enabled: true };
const isInstagram = window.location.hostname.includes('instagram.com');

let currentMode = 'adult';

function updateBodyModeClass(mode) {
    document.body.classList.remove('sabdaai-mode-adult', 'sabdaai-mode-parental');
    if (mode === 'parental') {
        document.body.classList.add('sabdaai-mode-parental');
    } else {
        document.body.classList.add('sabdaai-mode-adult');
    }
}

chrome.storage.local.get(['mode'], (result) => {
    if (result.mode) {
        currentMode = result.mode;
    }
    updateBodyModeClass(currentMode);
});

chrome.storage.onChanged.addListener((changes, namespace) => {
    if (namespace === 'local' && changes.mode) {
        currentMode = changes.mode.newValue;
        updateBodyModeClass(currentMode);
    }
});

// styling for visual overlays
const styleEl = document.createElement('style');
styleEl.textContent = `
    /* Instagram specific overlays */
    .sabdaai-inst-hateful {
        border: 1.5px solid #fb4d6d !important;
        background-color: rgba(251, 77, 109, 0.12) !important;
        padding: 3px 8px !important;
        border-radius: 6px !important;
        display: inline-block !important;
        margin: 2px 0 !important;
        position: relative !important;
        transition: all 0.25s ease !important;
    }
    .sabdaai-inst-hateful .sabdaai-blur-text {
        filter: blur(6px) !important;
        opacity: 0.3 !important;
        pointer-events: none !important;
        user-select: none !important;
        transition: all 0.3s ease !important;
    }
    .sabdaai-mode-adult .sabdaai-inst-hateful {
        cursor: pointer !important;
    }
    .sabdaai-mode-adult .sabdaai-inst-hateful::before {
        content: "⚠️ Hateful Comment Hidden (Click to Reveal)" !important;
        color: #fb4d6d !important;
        font-weight: 700 !important;
        font-size: 11px !important;
        margin-right: 6px !important;
        display: inline-block !important;
    }
    .sabdaai-mode-parental .sabdaai-inst-hateful {
        cursor: default !important;
    }
    .sabdaai-mode-parental .sabdaai-inst-hateful::before {
        content: "⚠️ Hateful Comment Hidden" !important;
        color: #fb4d6d !important;
        font-weight: 700 !important;
        font-size: 11px !important;
        margin-right: 6px !important;
        display: inline-block !important;
    }
    .sabdaai-inst-hateful.revealed {
        border-color: rgba(255, 255, 255, 0.08) !important;
        background-color: rgba(255, 255, 255, 0.02) !important;
    }
    .sabdaai-inst-hateful.revealed::before {
        content: "⚠️ Hateful (Revealed):" !important;
        opacity: 0.6 !important;
    }
    .sabdaai-inst-hateful.revealed .sabdaai-blur-text {
        filter: none !important;
        opacity: 1 !important;
        pointer-events: auto !important;
        user-select: text !important;
    }

    /* Parental mode offensive style (hidden/blurred) */
    .sabdaai-mode-parental .sabdaai-inst-offensive {
        border: 1.5px solid #fbbf24 !important;
        background-color: rgba(251, 191, 36, 0.08) !important;
        padding: 3px 8px !important;
        border-radius: 6px !important;
        cursor: default !important;
        display: inline-block !important;
        margin: 2px 0 !important;
        position: relative !important;
        transition: all 0.25s ease !important;
    }
    .sabdaai-mode-parental .sabdaai-inst-offensive .sabdaai-offensive-text {
        filter: blur(3.5px) !important;
        opacity: 0.45 !important;
        pointer-events: none !important;
        user-select: none !important;
        transition: all 0.3s ease !important;
    }
    .sabdaai-mode-parental .sabdaai-inst-offensive::before {
        content: "⚠️ Offensive Comment Hidden" !important;
        color: #fbbf24 !important;
        font-weight: 700 !important;
        font-size: 11px !important;
        margin-right: 6px !important;
        display: inline-block !important;
    }
    .sabdaai-mode-parental .sabdaai-inst-offensive.revealed {
        border-color: rgba(255, 255, 255, 0.08) !important;
        background-color: rgba(255, 255, 255, 0.02) !important;
    }
    .sabdaai-mode-parental .sabdaai-inst-offensive.revealed::before {
        content: "⚠️ Offensive (Revealed):" !important;
        opacity: 0.6 !important;
    }
    .sabdaai-mode-parental .sabdaai-inst-offensive.revealed .sabdaai-offensive-text {
        filter: none !important;
        opacity: 1 !important;
        pointer-events: auto !important;
        user-select: text !important;
    }

    /* Adult mode offensive style (looks completely normal) */
    .sabdaai-mode-adult .sabdaai-inst-offensive {
        border: none !important;
        background-color: transparent !important;
        padding: 0 !important;
        border-radius: 0 !important;
        cursor: text !important;
        display: inline !important;
        margin: 0 !important;
    }
    .sabdaai-mode-adult .sabdaai-inst-offensive .sabdaai-offensive-text {
        filter: none !important;
        opacity: 1 !important;
        pointer-events: auto !important;
        user-select: text !important;
    }
    .sabdaai-mode-adult .sabdaai-inst-offensive::before {
        content: "" !important;
        display: none !important;
    }

    /* Testing Page specific highlights */
    .sabdaai-ext-highlight-offensive {
        background-color: rgba(251, 191, 36, 0.2) !important;
        border-bottom: 2px dashed #fbbf24 !important;
        color: inherit !important;
        border-radius: 3px !important;
        padding: 0 2px !important;
    }
    .sabdaai-ext-highlight-hateful {
        background-color: rgba(251, 77, 109, 0.2) !important;
        border-bottom: 2px dashed #fb4d6d !important;
        color: inherit !important;
        border-radius: 3px !important;
        padding: 0 2px !important;
    }
`;
document.head.appendChild(styleEl);

// High-signal English words/phrases that must always be scanned regardless
// of whether the text contains Devanagari or romanized Nepali.
const ENGLISH_SCAN_RE = /\b(kill|murder|stab|shoot|bomb|slaughter|exterminate|massacre|genocide|destroy|annihilate|hate|die|dead|threat|rape|lynch|hang|behead|terroris[mt]|white\s*supremac|nazi|fascist|i\s+will\s+kill|i\s+will\s+hurt|i\s+will\s+destroy|you\s+will\s+pay|watch\s+your\s+back|your\s+time\s+is\s+up|go\s+to\s+hell|rot\s+in\s+hell|burn\s+in\s+hell|end\s+yourself|kill\s+yourself|kys)\b/i;

function findNepaliTextNodes(root = document.body) {
    if (!root) return [];
    const walker = document.createTreeWalker(
        root,
        NodeFilter.SHOW_TEXT,
        {
            acceptNode: function(node) {
                const parent = node.parentNode;
                if (parent) {
                    const tag = parent.tagName.toLowerCase();
                    if (tag === 'script' || tag === 'style' || tag === 'textarea' || tag === 'input' || tag === 'noscript' || 
                        parent.classList.contains('sabdaai-ext-highlight-offensive') || 
                        parent.classList.contains('sabdaai-ext-highlight-hateful') ||
                        parent.classList.contains('sabdaai-blur-text') ||
                        parent.classList.contains('sabdaai-offensive-text') ||
                        parent.classList.contains('sabdaai-inst-hateful') ||
                        parent.classList.contains('sabdaai-inst-offensive')) {
                        return NodeFilter.FILTER_REJECT;
                    }
                }
                const val = node.nodeValue;
                // Accept Devanagari text
                const hasDevanagari = /[\u0900-\u097F]/.test(val);
                // Accept romanized Nepali slang/keywords
                const hasRomanizedNepali = /\b(tw|chha|parchha|parne|pani|hola|banauna|bhanne|bhaneko|maile|taile|timi|haru|haroo|muji|randi|gede|kera|garni|garne|gahro|hunchha|hudaina|bhandina|aaijha|khuru|pardaina|garchhu|garchu|garnu|hoina|haina|timro|hamro|tero|teri|bauko|aamachikne|machikne|chakka|puti|lado|kukur|khate|saala|gidi|muzi|bho|bhayo|hoki|kasto|kina|baje|dai|bhai|sathi|yaar|solti)\b/i.test(val);
                // NEW: Accept English text containing high-confidence hate/threat signals
                const hasEnglishHate = ENGLISH_SCAN_RE.test(val);

                if (hasDevanagari || hasRomanizedNepali || hasEnglishHate) {
                    return NodeFilter.FILTER_ACCEPT;
                }
                return NodeFilter.FILTER_SKIP;
            }
        }
    );

    const nodes = [];
    let currentNode;
    while (currentNode = walker.nextNode()) {
        nodes.push(currentNode);
    }
    return nodes;
}


function highlightNode(node, result) {
    const parent = node.parentNode;
    if (!parent) return;

    const text = node.nodeValue;
    const label = result.label.toLowerCase(); // 'offensive' or 'hateful'

    if (isInstagram) {
        // Create Instagram wrapper structure
        const wrapper = document.createElement('span');
        wrapper.className = `sabdaai-inst-${label}`;
        
        const textSpan = document.createElement('span');
        textSpan.className = label === 'hateful' ? 'sabdaai-blur-text' : 'sabdaai-offensive-text';
        textSpan.textContent = text;

        wrapper.appendChild(textSpan);
        
        // Add click-to-reveal event listener
        wrapper.addEventListener('click', (e) => {
            e.stopPropagation();
            if (currentMode === 'parental') {
                return;
            }
            wrapper.classList.toggle('revealed');
        });

        parent.replaceChild(wrapper, node);
    } else {
        // Testing dashboard highlight behaviour
        const tokens = result.highlighted_tokens;
        if (!tokens || tokens.length === 0) {
            const span = document.createElement('span');
            span.className = `sabdaai-ext-highlight-${label}`;
            span.textContent = text;
            parent.replaceChild(span, node);
            return;
        }

        const sortedTokens = [...tokens].sort((a, b) => b.length - a.length);
        let htmlContent = esc(text);

        for (const token of sortedTokens) {
            if (!token.trim()) continue;
            const escToken = esc(token);
            const regex = new RegExp(`(${escapeRegExp(escToken)})`, 'gi');
            htmlContent = htmlContent.replace(regex, `<span class="sabdaai-ext-highlight-${label}">$1</span>`);
        }

        const wrapper = document.createElement('span');
        wrapper.innerHTML = htmlContent;
        parent.replaceChild(wrapper, node);
    }
}

function analyzeBatchViaBackground(texts) {
    return new Promise((resolve) => {
        chrome.runtime.sendMessage({ action: 'analyze-batch', texts }, (response) => {
            if (chrome.runtime.lastError) {
                console.error("Background message error:", chrome.runtime.lastError);
                resolve({ success: false, error: chrome.runtime.lastError.message });
            } else {
                resolve(response);
            }
        });
    });
}

async function scanPage() {
    if (!stats.enabled) return;

    const textNodes = findNepaliTextNodes();
    if (textNodes.length === 0) return;

    const unscanned = textNodes.filter(node => !node._sabdaaiScanned);
    if (unscanned.length === 0) return;

    unscanned.forEach(node => node._sabdaaiScanned = true);
    
    const BATCH_SIZE = 15;
    for (let i = 0; i < unscanned.length; i += BATCH_SIZE) {
        const batch = unscanned.slice(i, i + BATCH_SIZE);
        const texts = batch.map(n => n.nodeValue.trim());

        try {
            const response = await analyzeBatchViaBackground(texts);
            if (response && response.success) {
                const data = response.data;
                data.results.forEach((result, idx) => {
                    stats.scanned++;
                    if (result.label !== 'Normal') {
                        if (result.label === 'Offensive') stats.offensive++;
                        if (result.label === 'Hateful') stats.hateful++;
                        
                        highlightNode(batch[idx], result);
                    }
                });
            } else {
                console.error("Background API call failed:", response ? response.error : 'No response');
            }
        } catch (e) {
            console.error("SabdaAI Scanning Error:", e);
        }
    }
}

function esc(s) {
    return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// listen for scan requests from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'scan') {
        scanPage().then(() => {
            sendResponse(stats);
        });
        return true;
    }
    if (request.action === 'getStats') {
        sendResponse(stats);
        return false;
    }
    if (request.action === 'toggleShield') {
        stats.enabled = !stats.enabled;
        sendResponse(stats);
        return false;
    }
});

// auto-scan on start
setTimeout(scanPage, 1000);

// watch for infinite scroll loads
let observerTimeout;
const observer = new MutationObserver(() => {
    if (!stats.enabled) return;
    clearTimeout(observerTimeout);
    observerTimeout = setTimeout(scanPage, 1200);
});

observer.observe(document.body, {
    childList: true,
    subtree: true
});
