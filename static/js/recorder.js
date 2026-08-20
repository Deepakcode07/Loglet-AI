class VoiceRecorder {
    constructor(onStop) { this.onStop = onStop; this.chunks = []; this.mediaRecorder = null; }

    async start() {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.mediaRecorder = new MediaRecorder(stream);
        this.chunks = [];
        this.mediaRecorder.ondataavailable = e => this.chunks.push(e.data);
        this.mediaRecorder.onstop = () => {
            const blob = new Blob(this.chunks, { type: "audio/wav" });
            stream.getTracks().forEach(t => t.stop());
            this.onStop(blob);
        };
        this.mediaRecorder.start();
    }

    stop() { if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") this.mediaRecorder.stop(); }
}