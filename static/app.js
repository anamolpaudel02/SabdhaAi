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

// Boot
window.addEventListener('DOMContentLoaded', () => {
    checkStatus();

    input.addEventListener('input', () => {
        const n = input.value.length;
        ctr.textContent = n;
        ctr.style.color = n >= 450 ? '#fb4d6d' : n >= 350 ? '#fbbf24' : '#4b5a72';
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
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
        } catch (err) {
            console.error(err);
            alert('Backend unreachable. Make sure uvicorn is running.');
        } finally {
            btn.classList.remove('loading');
            btn.disabled = false;
        }
    });
});

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

// Tab switch
window.switchTab = function(name, el) {
    document.querySelectorAll('.tp').forEach(x => x.classList.remove('on'));
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('on'));
    document.getElementById(`tab-${name}`).classList.add('on');
    el.classList.add('on');
};

// Load a preset into the textarea
window.load = function(text) {
    input.value = text;
    ctr.textContent = text.length;
    switchTab('single', document.querySelector('.tab'));
    input.focus();
};

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

    const card = document.createElement('div');
    card.className = `rcard ${shortClass}`;
    card.innerHTML = `
        <div class="rcard-top">
            <span class="rbadge ${shortClass}">${res.label}</span>
            <div class="conf">
                <span>${res.confidence}% confidence</span>
                <div class="conf-bar-wrap">
                    <div class="conf-fill ${shortClass}" style="width:${res.confidence}%"></div>
                </div>
            </div>
        </div>
        <div class="rcomment">${esc(res.text)}</div>
        <div class="rreason">
            <span class="rlabel">Why:</span>
            <span>${esc(res.reason)}</span>
        </div>
    `;
    results.insertBefore(card, results.firstChild);
}

window.clearAll = function() {
    total = normal = offensive = hateful = 0;
    sTotal.textContent = sNormal.textContent = sOffensive.textContent = sHateful.textContent = 0;
    results.innerHTML = '';
    emptyState.style.display = 'flex';
};

function esc(s) {
    return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
