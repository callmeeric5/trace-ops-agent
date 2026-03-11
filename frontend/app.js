/* ===================================================================
   Sentinel-Ops AI — Dashboard Application Logic
   Handles SSE streaming, DOM updates, and user interactions
   =================================================================== */

const API_BASE = '/api';
let currentDiagnosisId = null;
let eventSource = null;
let streamingContent = '';
let stepCount = 0;
let evidenceCount = 0;
let pendingRecommendedAction = null;
let lastThoughtText = '';

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options,
    });
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`HTTP ${response.status}: ${text}`);
    }
    return response;
}

async function apiJson(path, options = {}) {
    const response = await apiRequest(path, options);
    return response.json();
}

// ---- Initialization -------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    loadHistory();
    updateConnectionStatus('ready');
});

// ---- Quick Triggers --------------------------------------------------------

function quickTrigger(text) {
    document.getElementById('alertInput').value = text;
    document.getElementById('alertInput').focus();
}

// ---- Start Diagnosis -------------------------------------------------------

async function startDiagnosis() {
    const input = document.getElementById('alertInput');
    const description = input.value.trim();
    if (!description) {
        input.focus();
        return;
    }

    const btn = document.getElementById('startBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Investigating…';

    // Reset panels
    resetPanels();
    updateConnectionStatus('streaming');

    try {
        // 1. Create the diagnosis
        const data = await apiJson('/diagnosis/', {
            method: 'POST',
            body: JSON.stringify({ description }),
        });
        currentDiagnosisId = data.diagnosis_id;
        loadHistory();

        // 2. Connect to SSE stream
        connectSSE(currentDiagnosisId);
    } catch (err) {
        addReasoningStep('error', `Failed to start diagnosis: ${err.message}`);
        resetButton();
        updateConnectionStatus('error');
    }
}

// ---- SSE Connection --------------------------------------------------------

function connectSSE(diagnosisId) {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource(`${API_BASE}/diagnosis/stream/${diagnosisId}`);

    eventSource.addEventListener('start', (e) => {
        const data = JSON.parse(e.data);
        addReasoningStep('start', data.content);
    });

    eventSource.addEventListener('stream', (e) => {
        const data = JSON.parse(e.data);
        appendStreamContent(data.content);
    });

    eventSource.addEventListener('action', (e) => {
        const data = JSON.parse(e.data);
        // Finalize any streaming thought
        finalizeStream();
        addReasoningStep('action', data.content, data.tool_name, data.tool_input);
    });

    eventSource.addEventListener('observation', (e) => {
        const data = JSON.parse(e.data);
        addReasoningStep('observation', data.content);
        extractEvidence(data.content);
    });

    eventSource.addEventListener('conclusion', (e) => {
        const data = JSON.parse(e.data);
        finalizeStream();
        addReasoningStep('conclusion', 'Investigation complete. See the full reasoning trace above.');
        showRecommendedActionPanel(extractRecommendedAction(lastThoughtText));
        checkForWriteActions();
        resetButton();
        updateConnectionStatus('ready');
        eventSource.close();
        eventSource = null;
        loadHistory();
    });

    eventSource.addEventListener('guardrail', (e) => {
        const data = JSON.parse(e.data);
        showApprovalPanel(data);
    });

    eventSource.addEventListener('error', (e) => {
        if (eventSource.readyState === EventSource.CLOSED) {
            finalizeStream();
            resetButton();
            updateConnectionStatus('ready');
        }
    });

    eventSource.onerror = () => {
        // SSE connection closed or errored
        finalizeStream();
        resetButton();
        updateConnectionStatus('ready');
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
    };
}

// ---- Streaming Content -----------------------------------------------------

function appendStreamContent(text) {
    streamingContent += text;
    const trace = document.getElementById('reasoningTrace');

    let streamEl = trace.querySelector('.step-card.streaming');
    if (!streamEl) {
        streamEl = document.createElement('div');
        streamEl.className = 'step-card thought streaming';
        streamEl.innerHTML = `
            <div class="step-label">💭 Thought</div>
            <div class="step-content streaming-cursor"></div>
        `;
        trace.appendChild(streamEl);
    }

    const contentEl = streamEl.querySelector('.step-content');
    contentEl.textContent = streamingContent;
    trace.scrollTop = trace.scrollHeight;
}

function finalizeStream() {
    if (!streamingContent) return;

    const trace = document.getElementById('reasoningTrace');
    const streamEl = trace.querySelector('.step-card.streaming');
    if (streamEl) {
        streamEl.classList.remove('streaming');
        const contentEl = streamEl.querySelector('.step-content');
        contentEl.classList.remove('streaming-cursor');

        // Parse markdown-like formatting in the content
        contentEl.innerHTML = formatContent(streamingContent);
        lastThoughtText = streamingContent;
        stepCount++;
        updateStepCounter();
    }
    streamingContent = '';
}

// ---- Add Reasoning Steps ---------------------------------------------------

function addReasoningStep(type, content, toolName, toolInput) {
    const trace = document.getElementById('reasoningTrace');

    // Remove empty state
    const emptyState = trace.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    const icons = {
        start: '🚀',
        thought: '💭',
        action: '⚡',
        observation: '👁️',
        conclusion: '✅',
        error: '❌',
        guardrail: '🛡️',
    };

    const labels = {
        start: 'Investigation Started',
        thought: 'Thought',
        action: 'Action',
        observation: 'Observation',
        conclusion: 'Conclusion',
        error: 'Error',
        guardrail: 'Guardrail',
    };

    const card = document.createElement('div');
    card.className = `step-card ${type}`;

    let html = `
        <div class="step-label">${icons[type] || '📌'} ${labels[type] || type}</div>
        <div class="step-content">${formatContent(content)}</div>
    `;

    if (toolName) {
        html += `<div class="step-tool-info">Tool: ${toolName}`;
        if (toolInput) {
            html += `\nInput: ${toolInput}`;
        }
        html += `</div>`;
    }

    card.innerHTML = html;
    trace.appendChild(card);
    trace.scrollTop = trace.scrollHeight;

    stepCount++;
    updateStepCounter();
}

// ---- Evidence Extraction ---------------------------------------------------

function normalizeLogId(rawId) {
    if (!rawId) return '';
    const trimmed = rawId.trim().replace(/[),.\]]+$/g, '');
    const uuidMatch = trimmed.match(/[0-9a-fA-F-]{36}/);
    return uuidMatch ? uuidMatch[0] : trimmed;
}

function extractEvidence(observationText) {
    // Parse log entries from observation text (looking for [log_id=...] patterns)
    const logPattern = /\[log_id=([^\]]+)\]\s*([^\n]+)/g;
    let match;

    while ((match = logPattern.exec(observationText)) !== null) {
        const logId = normalizeLogId(match[1]);
        if (!logId) continue;
        const logLine = match[2].trim();

        // Parse level from the log line
        const levelMatch = logLine.match(/\[(ERROR|CRITICAL|WARNING|INFO|DEBUG)\]/);
        const level = levelMatch ? levelMatch[1] : 'INFO';

        // Parse service
        const serviceMatch = logLine.match(/([\w-]+service):/i);
        const service = serviceMatch ? serviceMatch[1] : '';

        // Extract message (after the service name)
        const msgMatch = logLine.match(/[\w-]+service:\s*(.+)/i);
        const message = msgMatch ? msgMatch[1] : logLine;

        addEvidenceItem(logId, level, service, message);
    }

    // Parse clustered log id lists: [log_ids=id1, id2 ...]
    const logIdsPattern = /\[log_ids=([^\]]+)\]/g;
    while ((match = logIdsPattern.exec(observationText)) !== null) {
        const rawIds = match[1]
            .replace(/\.\.\.\s*\(\+\d+\s*more\)/, '')
            .split(',')
            .map(id => id.trim())
            .filter(Boolean);
        for (const id of rawIds) {
            const logId = normalizeLogId(id);
            if (!logId || logId === 'unknown') continue;
            addEvidenceItem(logId, 'INFO', '', 'Clustered log (expand with get_log_by_id).');
        }
    }

    // Parse clustered log id lists: log_ids: [id1, id2 ...]
    const logIdsLegacyPattern = /log_ids:\s*\[([^\]]+)\]/g;
    while ((match = logIdsLegacyPattern.exec(observationText)) !== null) {
        const rawIds = match[1]
            .replace(/\.\.\.\s*\(\+\d+\s*more\)/, '')
            .split(',')
            .map(id => id.trim())
            .filter(Boolean);
        for (const id of rawIds) {
            const logId = normalizeLogId(id);
            if (!logId || logId === 'unknown') continue;
            addEvidenceItem(logId, 'INFO', '', 'Clustered log (expand with get_log_by_id).');
        }
    }

    // Also look for stack traces
    const stackMatch = observationText.match(/STACK_TRACE:\s*([\s\S]*?)(?=\n\[log_id|$)/);
    if (stackMatch) {
        // Stack traces are associated with the previous log_id
    }
}

function addEvidenceItem(logId, level, service, message, stackTrace) {
    const list = document.getElementById('evidenceList');

    // Remove empty state
    const emptyState = list.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    // Avoid duplicate evidence
    if (list.querySelector(`[data-log-id="${logId}"]`)) return;

    const item = document.createElement('div');
    item.className = 'evidence-item';
    item.setAttribute('data-log-id', logId);

    let html = `
        <div>
            <span class="log-id">${logId}</span>
            <span class="log-level ${level}">${level}</span>
        </div>
        <div class="log-message">${escapeHtml(message)}</div>
    `;

    if (service) {
        html += `<div class="log-service">Service: ${service}</div>`;
    }

    if (stackTrace) {
        html += `<div class="stack-trace">${escapeHtml(stackTrace)}</div>`;
    }

    item.innerHTML = html;
    list.appendChild(item);

    evidenceCount++;
    updateEvidenceCounter();
}

// ---- Approval Workflow -----------------------------------------------------

function showApprovalPanel(data) {
    const panel = document.getElementById('approvalPanel');
    panel.classList.remove('hidden');
    document.getElementById('approvalDescription').textContent =
        data.content || 'The agent recommends a write action.';
    document.getElementById('approvalDetails').textContent =
        data.action || '';
}

async function approveAction() {
    if (!currentDiagnosisId) return;
    try {
        await apiRequest('/diagnosis/approve', {
            method: 'POST',
            body: JSON.stringify({
                diagnosis_id: currentDiagnosisId,
                approved: true,
            }),
        });
        addReasoningStep('guardrail', 'Action APPROVED by human reviewer.');
        document.getElementById('approvalPanel').classList.add('hidden');
        loadHistory();
    } catch (err) {
        console.error('Approval failed:', err);
    }
}

async function rejectAction() {
    if (!currentDiagnosisId) return;
    try {
        await apiRequest('/diagnosis/approve', {
            method: 'POST',
            body: JSON.stringify({
                diagnosis_id: currentDiagnosisId,
                approved: false,
            }),
        });
        addReasoningStep('guardrail', 'Action REJECTED by human reviewer.');
        document.getElementById('approvalPanel').classList.add('hidden');
        loadHistory();
    } catch (err) {
        console.error('Rejection failed:', err);
    }
}

// ---- Check for Write Actions in Conclusion ---------------------------------

function checkForWriteActions() {
    const trace = document.getElementById('reasoningTrace');
    const steps = trace.querySelectorAll('.step-content');
    const lastStep = steps[steps.length - 1];

    if (lastStep) {
        const text = lastStep.textContent;
        if (/\[WRITE\]/i.test(text)) {
            showApprovalPanel({
                content: 'The agent\'s recommendation includes a WRITE action that requires approval.',
                action: text,
            });
        }
    }
}

// ---- History ---------------------------------------------------------------

async function loadHistory() {
    try {
        const payload = await apiJson('/diagnosis/');
        const diagnoses = normalizeDiagnoses(payload);

        const list = document.getElementById('historyList');
        if (diagnoses.length === 0) {
            list.innerHTML = '<p class="muted">No previous investigations.</p>';
            return;
        }

        list.innerHTML = diagnoses.map(d => `
            <div class="history-item" onclick="viewDiagnosis('${d.id}')">
                <span class="history-desc">${escapeHtml(d.trigger_description || d.summary || 'Investigation')}</span>
                <span class="history-status ${d.status}">${String(d.status || 'unknown').replace('_', ' ')}</span>
                <span class="history-time">${formatTime(d.updated_at || d.created_at || '')}</span>
            </div>
        `).join('');
    } catch (err) {
        console.error('Failed to load history:', err);
    }
}

async function viewDiagnosis(id) {
    try {
        resetPanels();
        updateConnectionStatus('ready');
        currentDiagnosisId = id;

        const diag = await apiJson(`/diagnosis/${id}`);
        const steps = await apiJson(`/diagnosis/${id}/steps`);

        const title = diag.trigger_description || 'Investigation';
        addReasoningStep('start', `Investigation: ${title}`);

        for (const step of steps) {
            if (step.step_type === 'thought') {
                addReasoningStep('thought', step.content);
            } else if (step.step_type === 'action') {
                let toolName = '';
                let toolInput = '';
                let content = 'Calling tool';
                try {
                    const payload = JSON.parse(step.content);
                    toolName = payload.tool_name || '';
                    toolInput = payload.tool_input ? JSON.stringify(payload.tool_input) : '';
                    if (toolName) content = `Calling tool: ${toolName}`;
                } catch {
                    content = step.content;
                }
                addReasoningStep('action', content, toolName, toolInput);
            } else if (step.step_type === 'observation') {
                addReasoningStep('observation', step.content);
                extractEvidence(step.content);
            }
        }

        if (diag.conclusion) {
            addReasoningStep('conclusion', diag.conclusion);
        }

        updateStepCounter();
        updateEvidenceCounter();
    } catch (err) {
        addReasoningStep('error', `Failed to load diagnosis: ${err.message}`);
    }
}

// ---- Helpers ---------------------------------------------------------------

function resetPanels() {
    stepCount = 0;
    evidenceCount = 0;
    streamingContent = '';
    pendingRecommendedAction = null;
    lastThoughtText = '';

    document.getElementById('reasoningTrace').innerHTML = '';
    document.getElementById('evidenceList').innerHTML = '';
    document.getElementById('approvalPanel').classList.add('hidden');
    document.getElementById('actionPanel').classList.add('hidden');

    updateStepCounter();
    updateEvidenceCounter();
}

function resetButton() {
    const btn = document.getElementById('startBtn');
    btn.disabled = false;
    btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 2L13 8L3 14V2Z" fill="currentColor"/>
        </svg>
        Start Diagnosis
    `;
}

function updateStepCounter() {
    document.getElementById('iterationCounter').textContent = `Steps: ${stepCount}`;
}

function updateEvidenceCounter() {
    document.getElementById('evidenceCounter').textContent = `Items: ${evidenceCount}`;
}

function updateConnectionStatus(status) {
    const dot = document.querySelector('.status-dot');
    const text = document.querySelector('.status-text');

    dot.className = 'status-dot';

    switch (status) {
        case 'ready':
            dot.classList.add('connected');
            text.textContent = 'Connected';
            break;
        case 'streaming':
            dot.classList.add('streaming');
            text.textContent = 'Investigating…';
            break;
        case 'error':
            text.textContent = 'Error';
            break;
        default:
            text.textContent = 'Disconnected';
    }
}

function formatContent(text) {
    if (!text) return '';
    // Basic formatting: code blocks, bold, log references
    let html = escapeHtml(text);
    // Highlight log_id references
    html = html.replace(
        /\[evidence:\s*log_id=([^\]]+)\]/g,
        '<code>[evidence: log_id=$1]</code>'
    );
    html = html.replace(
        /\[log_id=([^\]]+)\]/g,
        '<code>[log_id=$1]</code>'
    );
    // Bold **text**
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Inline code `text`
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Headings ### text
    html = html.replace(/^###\s+(.+)$/gm, '<strong style="color:var(--text-primary)">$1</strong>');
    return html;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTime(isoString) {
    try {
        if (!isoString) return '';
        const hasZone = /Z$|[+-]\d{2}:\d{2}$/.test(isoString);
        const safeIso = hasZone ? isoString : `${isoString}Z`;
        const date = new Date(safeIso);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);

        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) return `${diffHours}h ago`;
        return date.toLocaleDateString();
    } catch {
        return '';
    }
}

// ---- Recommended Action (Human-in-the-Loop Mock) --------------------------

function extractRecommendedAction(text) {
    if (!text) return null;
    const match = text.match(/Recommended Action\s*([\s\S]*)/i);
    if (match && match[1]) {
        return match[1].trim();
    }

    const lines = text.split('\n').map((line) => line.trim());
    const actionLines = lines.filter((line) => /\[(READ|WRITE)\]/i.test(line));
    if (actionLines.length > 0) {
        return actionLines.join('\n');
    }

    return null;
}

function showRecommendedActionPanel(actionText) {
    const panel = document.getElementById('actionPanel');
    const details = document.getElementById('actionDetails');
    pendingRecommendedAction = actionText || 'No explicit action parsed. Use this to simulate human approval.';
    details.textContent = pendingRecommendedAction;
    panel.classList.remove('hidden');
    persistRecommendedAction(pendingRecommendedAction);
}

async function approveRecommendedAction() {
    if (!currentDiagnosisId) return;
    try {
        await apiRequest('/diagnosis/approve', {
            method: 'POST',
            body: JSON.stringify({
                diagnosis_id: currentDiagnosisId,
                approved: true,
            }),
        });
        addReasoningStep('guardrail', 'Human approved the recommended action (mock).');
        document.getElementById('actionPanel').classList.add('hidden');
        pendingRecommendedAction = null;
        loadHistory();
    } catch (err) {
        console.error('Approval failed:', err);
    }
}

async function rejectRecommendedAction() {
    if (!currentDiagnosisId) return;
    try {
        await apiRequest('/diagnosis/approve', {
            method: 'POST',
            body: JSON.stringify({
                diagnosis_id: currentDiagnosisId,
                approved: false,
            }),
        });
        addReasoningStep('guardrail', 'Human rejected the recommended action (mock).');
        document.getElementById('actionPanel').classList.add('hidden');
        pendingRecommendedAction = null;
        loadHistory();
    } catch (err) {
        console.error('Rejection failed:', err);
    }
}

async function remindRecommendedActionLater() {
    if (!currentDiagnosisId) return;
    try {
        await apiRequest('/diagnosis/remind-later', {
            method: 'POST',
            body: JSON.stringify({
                diagnosis_id: currentDiagnosisId,
                approved: false,
            }),
        });
        addReasoningStep('guardrail', 'Reminder set. Action left in progress.');
        document.getElementById('actionPanel').classList.add('hidden');
        pendingRecommendedAction = null;
        loadHistory();
    } catch (err) {
        console.error('Remind later failed:', err);
    }
}

async function persistRecommendedAction(actionText) {
    if (!currentDiagnosisId) return;
    try {
        await apiRequest('/diagnosis/recommended-action', {
            method: 'POST',
            body: JSON.stringify({
                diagnosis_id: currentDiagnosisId,
                action_text: actionText,
                action_type: 'write',
            }),
        });
        loadHistory();
    } catch (err) {
        console.error('Failed to persist recommended action:', err);
    }
}

function normalizeDiagnoses(payload) {
    if (Array.isArray(payload)) {
        return payload.map((d) => ({
            ...d,
            status: normalizeStatus(d.status),
        }));
    }
    if (payload && Array.isArray(payload.sessions)) {
        return payload.sessions.map((s) => ({
            id: s.diagnosis_id,
            status: normalizeStatus(s.status),
            trigger_description: s.summary || s.alert_message || '',
            created_at: s.created_at || s.completed_at || '',
        }));
    }
    return [];
}

function normalizeStatus(status) {
    if (!status) return 'in_progress';
    if (status === 'failed') return 'rejected';
    return status;
}
