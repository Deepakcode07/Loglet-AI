const el = id => document.getElementById(id);
const tabs = document.querySelectorAll(".tab");
const statusMsg = el("statusMsg"), skeleton = el("skeletonLoader"), emptyState = el("emptyState"), reportCard = el("reportCard");
const reportView = el("reportView");
let lastMarkdown = "";
let currentGitItems = [];

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

    if (data.impact_score) {
        el("impactScoreVal").textContent = data.impact_score;
        el("impactScoreBadge").classList.remove("hidden");
    }
}

function getSettings() {
    return {
        prefix: el("prefixInput").value,
        context: el("contextInput").value,
        user_name: localStorage.getItem("loglet_user_name") || "Engineer",
        project_id: localStorage.getItem("loglet_project_id") || "default-project",
        user_id: localStorage.getItem("loglet_user_id") || "anon-user"
    };
}

// ---- GITSYNC RADAR FLOW ----
const githubInput = el("githubUserInput"), fetchGitBtn = el("fetchGitBtn"), gitsyncResult = el("gitsyncResult");
const storedGithub = localStorage.getItem("loglet_github");
if (storedGithub && githubInput) {
    githubInput.value = storedGithub;
}

if (fetchGitBtn) {
    fetchGitBtn.addEventListener("click", async () => {
        const username = githubInput.value.trim();
        if (!username) return alert("Please enter a GitHub username.");

        localStorage.setItem("loglet_github", username);
        el("gitsyncStatusBadge").textContent = "Scanning...";

        try {
            const res = await fetch(`/api/gitsync?username=${encodeURIComponent(username)}`);
            const data = await res.json();
            el("gitsyncStatusBadge").textContent = data.has_activity ? "Active" : "No Activity";
            gitsyncResult.classList.remove("hidden");

            el("gitsyncSummaryText").textContent = data.summary;
            currentGitItems = [...(data.commits || []), ...(data.prs || [])];

            let itemsHtml = "";
            if (data.commits && data.commits.length) {
                itemsHtml += `<div><strong>Commits Pushed Today:</strong> ${data.commits.map(c => `<span class="gitsync-badge">${c.sha}</span> ${c.message}`).join(", ")}</div>`;
            }
            if (data.prs && data.prs.length) {
                itemsHtml += `<div style="margin-top:4px;"><strong>Pull Requests:</strong> ${data.prs.map(p => `PR #${p.number}: ${p.title}`).join(", ")}</div>`;
            }
            el("gitsyncItemsList").innerHTML = itemsHtml;
        } catch {
            el("gitsyncStatusBadge").textContent = "Error";
        }
    });
}

// ---- TEXT FLOW ----
el("generateBtn").addEventListener("click", async () => {
    clearStatus();
    const text = el("textInput").value.trim();
    if (!text) return showError("Please enter your update first.");
    const { prefix, context, user_name, project_id, user_id } = getSettings();
    showLoading("✨ Structuring your day...");

    const includeGit = el("includeGitCheck") && el("includeGitCheck").checked;
    const git_items = includeGit ? currentGitItems : [];

    try {
        const res = await fetch("/api/generate/text", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                text, prefix, context, style_note: el("styleNote").value,
                user_name, project_id, user_id, git_items
            })
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
        recorder = new VoiceRecorder({
            maxSeconds: 180,
            silenceLimitMs: 4000,
            onTick: ({ elapsedSec, remaining }) => {
                recordStatus.textContent = remaining <= 10
                    ? `⏳ Auto-stopping in ${remaining}s...`
                    : `Listening... ${elapsedSec}s (tap to stop)`;
            },
            onAutoStop: (reason) => {
                recordStatus.textContent = reason === "silence"
                    ? "Stopped — no speech detected for a while."
                    : "Stopped — reached the 3 minute limit.";
                isRecording = false; recordBtn.classList.remove("recording"); orbIcon.textContent = "🎙️";
            },
            onStop: async (blob) => {
                showLoading("🧩 Understanding your update...");
                const { prefix, context, user_name, project_id, user_id } = getSettings();
                const form = new FormData();
                const ext = (blob.type && blob.type.includes("webm")) ? "audio.webm" : (blob.type && blob.type.includes("ogg")) ? "audio.ogg" : "audio.wav";
                form.append("audio", blob, ext);
                form.append("prefix", prefix);
                form.append("context", context);
                form.append("user_name", user_name);
                form.append("project_id", project_id);
                form.append("user_id", user_id);

                try {
                    const res = await fetch("/api/generate/voice", { method: "POST", body: form });
                    const data = await res.json();
                    if (!res.ok) { showError(data.error); emptyState.classList.remove("hidden"); skeleton.classList.add("hidden"); return; }
                    showReport(data);
                } catch { showError("Network error. Please try again."); emptyState.classList.remove("hidden"); skeleton.classList.add("hidden"); }
            }
        });
        await recorder.start();
        isRecording = true; recordBtn.classList.add("recording"); orbIcon.textContent = "⏹️";
        waveform.style.display = "flex";
    } else {
        recorder.stop(); isRecording = false; recordBtn.classList.remove("recording"); orbIcon.textContent = "🎙️";
        recordStatus.textContent = "Processing...";
    }
});

// ---- RICH COPY ----
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