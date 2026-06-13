const BACKEND_URL = 'http://localhost:8000';

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'analyze-batch') {
        fetch(`${BACKEND_URL}/api/analyze-batch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ texts: request.texts })
        })
        .then(res => {
            if (!res.ok) throw new Error('API response not OK');
            return res.json();
        })
        .then(data => {
            sendResponse({ success: true, data });
        })
        .catch(err => {
            console.error('Fetch error in background script:', err);
            sendResponse({ success: false, error: err.message });
        });
        return true; // Keep message channel open for async response
    }
});
