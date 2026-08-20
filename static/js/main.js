const el = id => document.getElementById(id);
const tabs = document.querySelectorAll(".tab");
const statusMsg = el("statusMsg"), skeleton = el("skeletonLoader"), emptyState = el("emptyState"), reportCard = el("reportCard");
const reportView = el("reportView");
let lastMarkdown = "";

// Tab switching
tabs.forEach(t => t.addEventListener("click", () => {
    tabs.forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.add("hidden"));
    el("tab-" + t.dataset.tab).classList.remove("hidden");
}));

function showError(msg) {
    statusMsg.textContent = msg; statusMsg.className = "status-msg error";
}
function clearStatus() { statusMsg.className = "status-msg hidden"; }

function showLoading(text) {
    emptyState.classList.add("hidden"); reportCard.classList.add("hidden");
    skeleton.classList.remove("hidden"); el("skStatusText").textContent = text;
}
function showReport(data) {
    skeleton.classList.add("hidden"); emptyState.classList.add("hidden");
    reportCard.classList.remove("hidden");
    reportView.innerHTML = data.final_report_html;
    lastMarkdown = data.final_report;
}

function getSettings() {
    return { prefix: el("prefixInput").value, context: el("contextInput").value };
}

// ---- TEXT FLOW ----
el("generateBtn").addEventListener("click", async () => {
    clearStatus();
    const text = el("textInput").value.trim();
    if (!text) return showError("Please enter your update first.");
    const { prefix, context } = getSettings();
    showLoading("✨ Structuring your day...");
    try {
        const res = await fetch("/api/generate/text", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, prefix, context, style_note: el("styleNote").value })
        });
        const data = await res.json();
        if (!res.ok) return showError(data.error), emptyState.classList.remove("hidden"), skeleton.classList.add("hidden");
        showReport(data);
    } catch { showError("Network error. Please try again."); emptyState.classList.remove("hidden"); skeleton.classList.add("hidden"); }
});

// ---- VOICE FLOW ----
const recordBtn = el("recordBtn"), orbIcon = el("orbIcon"), recordStatus = el("recordStatus"), waveform = el("waveform");
let recorder, isRecording = false;
waveform.innerHTML = Array.from({ length: 20 }).map((_, i) => `<span style="animation-delay:${i * 0.05}s"></span>`).join("");

recordBtn.addEventListener("click", async () => {
    clearStatus();
    if (!isRecording) {
        recorder = new VoiceRecorder(async (blob) => {
            showLoading("🧩 Understanding your update...");
            const { prefix, context } = getSettings();
            const form = new FormData();
            form.append("audio", blob, "audio.wav");
            form.append("prefix", prefix); form.append("context", context);
            try {
                const res = await fetch("/api/generate/voice", { method: "POST", body: form });
                const data = await res.json();
                if (!res.ok) return showError(data.error), emptyState.classList.remove("hidden"), skeleton.classList.add("hidden");
                showReport(data);
            } catch { showError("Network error. Please try again."); emptyState.classList.remove("hidden"); skeleton.classList.add("hidden"); }
        });
        await recorder.start();
        isRecording = true; recordBtn.classList.add("recording"); orbIcon.textContent = "⏹️";
        recordStatus.textContent = "Listening... tap to stop"; waveform.style.display = "flex";
    } else {
        recorder.stop(); isRecording = false; recordBtn.classList.remove("recording"); orbIcon.textContent = "🎙️";
        recordStatus.textContent = "Processing...";
    }
});

// ---- RICH COPY (bold/headers preserved, no # or *) ----
el("copyRichBtn").addEventListener("click", async () => {
    const html = reportView.innerHTML;
    const plain = reportView.innerText;
    try {
        const item = new ClipboardItem({
            "text/html": new Blob([html], { type: "text/html" }),
            "text/plain": new Blob([plain], { type: "text/plain" })
        });
        await navigator.clipboard.write([item]);
        flashButton("copyRichBtn", "✅ Copied!");
    } catch { await navigator.clipboard.writeText(plain); flashButton("copyRichBtn", "✅ Copied!"); }
});

el("copyMdBtn").addEventListener("click", async () => {
    await navigator.clipboard.writeText(lastMarkdown);
    flashButton("copyMdBtn", "✅ Copied!");
});

function flashButton(id, text) {
    const btn = el(id); const original = btn.textContent;
    btn.textContent = text; setTimeout(() => btn.textContent = original, 1500);
}

// ---- EDIT MODE ----
let editing = false;
el("editBtn").addEventListener("click", async () => {
    if (!editing) {
        reportView.contentEditable = "true"; reportView.focus();
        el("editBtn").textContent = "💾 Save"; editing = true;
    } else {
        reportView.contentEditable = "false";
        const res = await fetch("/api/edit", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ report: reportView.innerText })
        });
        const data = await res.json();
        reportView.innerHTML = data.final_report_html;
        lastMarkdown = data.final_report;
        el("editBtn").textContent = "✏️ Edit"; editing = false;
    }
});

// ---- DOWNLOAD ----
el("downloadBtn").addEventListener("click", () => {
    const blob = new Blob([lastMarkdown], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `eod_status_${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}.md`;
    a.click();
});