const BACKEND_URL = 'http://localhost:8000';

document.addEventListener('DOMContentLoaded', () => {
    checkBackendStatus();
    loadStats();

    const scanBtn = document.getElementById('scan-btn');
    if (scanBtn) {
        scanBtn.addEventListener('click', () => {
            chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
                if (tabs[0]) {
                    chrome.tabs.sendMessage(tabs[0].id, { action: 'scan' }, (response) => {
                        if (chrome.runtime.lastError) {
                            alert("Cannot scan this page. Refresh the page or ensure it is a valid website (not a chrome:// page).");
                            return;
                        }
                        if (response) {
                            updateUI(response);
                        }
                    });
                }
            });
        });
    }

    const toggleBtn = document.getElementById('toggle-shield-btn');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
                if (tabs[0]) {
                    chrome.tabs.sendMessage(tabs[0].id, { action: 'toggleShield' }, (response) => {
                        if (chrome.runtime.lastError) return;
                        if (response) {
                            const shieldStatus = document.getElementById('shield-status');
                            if (response.enabled) {
                                shieldStatus.textContent = "Active & Scanning";
                                shieldStatus.style.color = "var(--green)";
                                toggleBtn.textContent = "Pause Shield";
                            } else {
                                shieldStatus.textContent = "Shield Paused";
                                shieldStatus.style.color = "var(--text-3)";
                                toggleBtn.textContent = "Enable Shield";
                            }
                        }
                    });
                }
            });
        });
    }
});

async function checkBackendStatus() {
    const dot = document.getElementById('status-dot');
    try {
        const res = await fetch(`${BACKEND_URL}/api/status`);
        if (res.ok) {
            dot.className = 'dot live';
        } else {
            dot.className = 'dot offline';
        }
    } catch {
        dot.className = 'dot offline';
    }
}

function loadStats() {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs[0]) {
            chrome.tabs.sendMessage(tabs[0].id, { action: 'getStats' }, (response) => {
                if (chrome.runtime.lastError) return;
                if (response) {
                    updateUI(response);
                    
                    const shieldStatus = document.getElementById('shield-status');
                    const toggleBtn = document.getElementById('toggle-shield-btn');
                    if (response.enabled) {
                        shieldStatus.textContent = "Active & Scanning";
                        shieldStatus.style.color = "var(--green)";
                        toggleBtn.textContent = "Pause Shield";
                    } else {
                        shieldStatus.textContent = "Shield Paused";
                        shieldStatus.style.color = "var(--text-3)";
                        toggleBtn.textContent = "Enable Shield";
                    }
                }
            });
        }
    });
}

function updateUI(data) {
    document.getElementById('stat-scanned').textContent = data.scanned || 0;
    document.getElementById('stat-offensive').textContent = data.offensive || 0;
    document.getElementById('stat-hateful').textContent = data.hateful || 0;
}
