import logging
from flask import Flask, render_template, request, jsonify
from config import Config
from services.llm_service import LLMService
from services.audio_service import AudioProcessor
from services.report_pipeline import ReportPipeline
from services.security import Sanitizer
from services.formatter import RichTextFormatter

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("loglet_ai")

Config.validate()

app = Flask(__name__)
llm_service = LLMService()
audio_processor = AudioProcessor()
pipeline = ReportPipeline(llm_service)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/generate/text", methods=["POST"])
def generate_from_text():
    data = request.get_json(force=True)
    try:
        raw_text = Sanitizer.text(data.get("text", ""), Config.MAX_INPUT_CHARS)
        prefix = Sanitizer.prefix(data.get("prefix", ""), Config.MAX_PREFIX_CHARS)
        context = Sanitizer.text(data.get("context", ""), Config.MAX_CONTEXT_CHARS)
        style_note = Sanitizer.text(data.get("style_note", ""), 300)

        if not raw_text.strip():
            return jsonify({"error": "Please enter your update first."}), 400

        result = pipeline.run(raw_text, context, prefix, style_note)
        result["final_report_html"] = RichTextFormatter.to_html(result["final_report"])
        return jsonify(result)
    except RuntimeError:
        return jsonify({"error": "We couldn't generate your report right now. Please try again in a moment."}), 502
    except Exception:
        logger.exception("Unexpected error in text flow")
        return jsonify({"error": "Something unexpected happened. Please try again."}), 500


@app.route("/api/generate/voice", methods=["POST"])
def generate_from_voice():
    try:
        audio_file = request.files.get("audio")
        if not audio_file:
            return jsonify({"error": "No audio received."}), 400

        prefix = Sanitizer.prefix(request.form.get("prefix", ""), Config.MAX_PREFIX_CHARS)
        context = Sanitizer.text(request.form.get("context", ""), Config.MAX_CONTEXT_CHARS)

        raw_bytes = audio_file.read()
        cleaned_bytes = audio_processor.clean(raw_bytes)

        transcript = llm_service.transcribe(
            cleaned_bytes, prompt_hint=f"Professional IT update, mentions tickets like {prefix}"
        )
        transcript = Sanitizer.text(transcript, Config.MAX_INPUT_CHARS)

        result = pipeline.run(transcript, context, prefix, "")
        result["transcript"] = transcript
        result["final_report_html"] = RichTextFormatter.to_html(result["final_report"])
        return jsonify(result)
    except RuntimeError as e:
        msg = "We couldn't hear that clearly, please try again." if "transcription" in str(e) else \
              "We couldn't generate your report right now. Please try again in a moment."
        return jsonify({"error": msg}), 502
    except Exception:
        logger.exception("Unexpected error in voice flow")
        return jsonify({"error": "Something unexpected happened. Please try again."}), 500


@app.route("/api/edit", methods=["POST"])
def edit_report():
    """Lets user submit a manually-edited report; just re-renders rich HTML."""
    data = request.get_json(force=True)
    edited = Sanitizer.text(data.get("report", ""), 8000)
    return jsonify({
        "final_report": edited,
        "final_report_html": RichTextFormatter.to_html(edited)
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)