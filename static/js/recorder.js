class VoiceRecorder {
    constructor({ onStop, onTick, onAutoStop, maxSeconds = 180, silenceLimitMs = 4000 }) {
        this.onStop = onStop;
        this.onTick = onTick;
        this.onAutoStop = onAutoStop;
        this.maxSeconds = maxSeconds;
        this.silenceLimitMs = silenceLimitMs;
        this.chunks = [];
        this.mediaRecorder = null;
        this.audioCtx = null;
        this.analyser = null;
        this.silenceStart = null;
        this.startTime = null;
        this.hasSpokenOnce = false;
    }

    async start() {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
            ? "audio/webm;codecs=opus"
            : MediaRecorder.isTypeSupported("audio/webm")
            ? "audio/webm"
            : "audio/ogg";
        this.mediaRecorder = new MediaRecorder(stream, { mimeType });
        this.chunks = [];
        this.mediaRecorder.ondataavailable = e => { if (e.data && e.data.size > 0) this.chunks.push(e.data); };
        this.mediaRecorder.onstop = () => {
            const blob = new Blob(this.chunks, { type: mimeType });
            stream.getTracks().forEach(t => t.stop());
            cancelAnimationFrame(this._raf);
            if (this.audioCtx) this.audioCtx.close();
            this.onStop(blob);
        };
        this.mediaRecorder.start();
        this.startTime = Date.now();

        // --- Real-time level monitoring for silence + hard-cap detection ---
        this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const source = this.audioCtx.createMediaStreamSource(stream);
        this.analyser = this.audioCtx.createAnalyser();
        this.analyser.fftSize = 512;
        source.connect(this.analyser);
        this._monitor(stream);
    }

    _monitor(stream) {
        const buf = new Uint8Array(this.analyser.frequencyBinCount);
        const loop = () => {
            this.analyser.getByteTimeDomainData(buf);
            let sumSq = 0;
            for (let i = 0; i < buf.length; i++) {
                const v = (buf[i] - 128) / 128;
                sumSq += v * v;
            }
            const rms = Math.sqrt(sumSq / buf.length);
            const elapsedMs = Date.now() - this.startTime;
            const elapsedSec = Math.floor(elapsedMs / 1000);

            if (this.onTick) this.onTick({ elapsedSec, level: rms, remaining: this.maxSeconds - elapsedSec });

            const SPEECH_THRESHOLD = 0.02;
            if (rms > SPEECH_THRESHOLD) {
                this.hasSpokenOnce = true;
                this.silenceStart = null;
            } else if (this.hasSpokenOnce) {
                // only start silence countdown AFTER user has spoken at least once —
                // prevents cutting off someone who's still thinking at the very start
                if (!this.silenceStart) this.silenceStart = Date.now();
                if (Date.now() - this.silenceStart > this.silenceLimitMs) {
                    this.stop();
                    if (this.onAutoStop) this.onAutoStop("silence");
                    return;
                }
            }

            if (elapsedMs / 1000 >= this.maxSeconds) {
                this.stop();
                if (this.onAutoStop) this.onAutoStop("max_duration");
                return;
            }

            this._raf = requestAnimationFrame(loop);
        };
        this._raf = requestAnimationFrame(loop);
    }

    stop() {
        if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") this.mediaRecorder.stop();
    }
}