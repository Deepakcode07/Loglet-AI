import logging
import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from config import Config
from services.llm_service import LLMService
from services.audio_service import AudioProcessor
from services.report_pipeline import ReportPipeline
from services.security import Sanitizer
from services.formatter import RichTextFormatter
from services.supabase_service import SupabaseService
from services.git_service import GitSyncService
from services.pulse_aggregator import PulseAggregatorAgent
from services.vault_service import CareerVaultService
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("loglet_ai")

Config.validate()

app = Flask(__name__)
llm_service = LLMService()
audio_processor = AudioProcessor()
pipeline = ReportPipeline(llm_service)
supabase_service = SupabaseService()
git_service = GitSyncService()
pulse_aggregator = PulseAggregatorAgent(llm_service)
vault_service = CareerVaultService(llm_service)

app.config["MAX_CONTENT_LENGTH"] = Config.MAX_AUDIO_BYTES
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["500 per hour"])


# ==================== HTML VIEW ROUTES ====================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/pulse")
def pulse_view():
    return render_template("pulse.html")

@app.route("/teams")
@app.route("/join")
def teams_view():
    return render_template("teams.html")

@app.route("/vault")
def vault_view():
    return render_template("vault.html")

@app.route("/guide")
def guide_view():
    return render_template("guide.html")

@app.route("/health")
@app.route("/healthz")
@app.route("/_stcore/health")
@limiter.exempt
def health_check():
    return jsonify({
        "status": "healthy",
        "supabase_connected": supabase_service.is_connected()
    }), 200


# ==================== CORE REPORT GENERATION ====================

@app.route("/api/generate/text", methods=["POST"])
@limiter.limit("500 per hour")
def generate_from_text():
    data = request.get_json(force=True)
    try:
        raw_text = Sanitizer.text(data.get("text", ""), Config.MAX_INPUT_CHARS)
        prefix = Sanitizer.prefix(data.get("prefix", ""), Config.MAX_PREFIX_CHARS)
        context = Sanitizer.text(data.get("context", ""), Config.MAX_CONTEXT_CHARS)
        style_note = Sanitizer.text(data.get("style_note", ""), 300)
        
        user_name = Sanitizer.text(data.get("user_name", "Engineer"), 50)
        project_id = data.get("project_id", "default-project")
        user_id = data.get("user_id", "anon-user")
        git_items = data.get("git_items", [])

        if not raw_text.strip():
            return jsonify({"error": "Please enter your update first."}), 400

        # Append GitSync context if provided
        effective_text = raw_text
        if git_items and isinstance(git_items, list):
            git_summary = "\n".join([f"- Git Activity: {g.get('message', g.get('title', ''))}" for g in git_items[:5]])
            effective_text += f"\n\n[GIT ACTIVITY DETECTED TODAY]:\n{git_summary}"

        result = pipeline.run(effective_text, context, prefix, style_note)
        report_html = RichTextFormatter.to_html(result["final_report"])
        result["final_report_html"] = report_html

        # Calculate Impact Score & Save update into DB
        impact_score = vault_service.calculate_impact_score(result["final_report"], git_items)
        db_entry = supabase_service.save_daily_update(
            user_id=user_id,
            project_id=project_id,
            user_name=user_name,
            raw_transcript=raw_text,
            final_report_md=result["final_report"],
            git_activity=git_items,
            impact_score=impact_score
        )
        result["impact_score"] = impact_score
        result["update_id"] = db_entry.get("id")

        return jsonify(result)
    except RuntimeError:
        return jsonify({"error": "We couldn't generate your report right now. Please try again in a moment."}), 502
    except Exception:
        logger.exception("Unexpected error in text flow")
        return jsonify({"error": "Something unexpected happened. Please try again."}), 500


@app.route("/api/generate/voice", methods=["POST"])
@limiter.limit("500 per hour")
def generate_from_voice():
    try:
        audio_file = request.files.get("audio")
        if not audio_file:
            return jsonify({"error": "No audio received."}), 400

        prefix = Sanitizer.prefix(request.form.get("prefix", ""), Config.MAX_PREFIX_CHARS)
        context = Sanitizer.text(request.form.get("context", ""), Config.MAX_CONTEXT_CHARS)
        user_name = Sanitizer.text(request.form.get("user_name", "Engineer"), 50)
        project_id = request.form.get("project_id", "default-project")
        user_id = request.form.get("user_id", "anon-user")

        raw_bytes = audio_file.read()
        ratio = audio_processor.speech_ratio(raw_bytes)
        if ratio < Config.MIN_SPEECH_RATIO:
            return jsonify({
                "error": "We couldn't detect enough speech in that recording. "
                         "Make sure you're speaking clearly and try again."
            }), 422
        cleaned_bytes = audio_processor.clean(raw_bytes)

        transcript = llm_service.transcribe(
            cleaned_bytes, prompt_hint=f"Professional IT update, mentions tickets like {prefix}"
        )
        transcript = Sanitizer.text(transcript, Config.MAX_INPUT_CHARS)
        if len(transcript.split()) < Config.MIN_TRANSCRIPT_WORDS:
            return jsonify({
                "error": "That update was too short to summarize. Try adding a bit more detail."
            }), 422

        result = pipeline.run(transcript, context, prefix, "")
        result["transcript"] = transcript
        result["final_report_html"] = RichTextFormatter.to_html(result["final_report"])

        impact_score = vault_service.calculate_impact_score(result["final_report"], [])
        db_entry = supabase_service.save_daily_update(
            user_id=user_id,
            project_id=project_id,
            user_name=user_name,
            raw_transcript=transcript,
            final_report_md=result["final_report"],
            impact_score=impact_score
        )
        result["impact_score"] = impact_score
        result["update_id"] = db_entry.get("id")

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
    data = request.get_json(force=True)
    edited = Sanitizer.text(data.get("report", ""), 8000)
    return jsonify({
        "final_report": edited,
        "final_report_html": RichTextFormatter.to_html(edited)
    })


# ==================== GITSYNC RADARS API ====================

@app.route("/api/gitsync", methods=["GET"])
def gitsync_radar():
    username = request.args.get("username", "")
    if not username:
        return jsonify({"error": "GitHub username is required"}), 400
    res = git_service.fetch_today_activity(username)
    return jsonify(res)


# ==================== LOGLET TEAMS & INVITES API ====================

@app.route("/api/teams/create", methods=["POST"])
def create_team_project():
    data = request.get_json(force=True)
    name = Sanitizer.text(data.get("name", ""), 100)
    target_size = data.get("target_team_size", 5)
    manager_email = Sanitizer.text(data.get("manager_email", ""), 100)

    if not name or not manager_email:
        return jsonify({"error": "Project name and manager email are required"}), 400

    project = supabase_service.create_project(name, target_size, manager_email)
    return jsonify({
        "message": "Project created successfully",
        "project": project,
        "invite_url": f"{request.host_url}join?code={project['invite_code']}"
    })

@app.route("/api/teams/invite/<code>", methods=["GET"])
def get_invite_info(code):
    project = supabase_service.get_project_by_invite(code)
    if not project:
        return jsonify({"error": "Invalid or expired invite link"}), 404
    return jsonify({"project": project})

@app.route("/api/teams/join", methods=["POST"])
def join_team():
    data = request.get_json(force=True)
    email = Sanitizer.text(data.get("email", ""), 100)
    name = Sanitizer.text(data.get("name", ""), 100)
    code = Sanitizer.text(data.get("invite_code", ""), 50)
    github_user = Sanitizer.text(data.get("github_username", ""), 50)

    if not email or not name or not code:
        return jsonify({"error": "Email, name, and invite code are required"}), 400

    try:
        user, project = supabase_service.join_project(email, name, code, github_user)
        return jsonify({
            "message": f"Successfully joined project '{project['name']}'",
            "user": user,
            "project": project
        })
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

@app.route("/api/teams/<project_id>/members", methods=["GET"])
def get_team_members(project_id):
    members = supabase_service.get_project_members(project_id)
    return jsonify({"members": members})


# ==================== LOGLET PULSE DIGEST API ====================

@app.route("/api/pulse/generate", methods=["POST"])
def generate_pulse_digest():
    data = request.get_json(force=True)
    project_id = data.get("project_id")
    project_name = data.get("project_name", "Engineering Team")
    target_team_size = int(data.get("target_team_size", 10))

    if not project_id:
        return jsonify({"error": "project_id is required"}), 400

    updates = supabase_service.get_team_daily_updates(project_id)
    pulse_res = pulse_aggregator.aggregate(project_name, target_team_size, updates)
    pulse_res["digest_html"] = RichTextFormatter.to_html(pulse_res["digest_md"])

    # Save to Supabase DB
    supabase_service.save_executive_digest(
        project_id,
        date_str=pulse_res.get("date", ""),
        digest_md=pulse_res["digest_md"],
        total_submissions=pulse_res["total_submissions"],
        completion_rate=pulse_res["completion_rate"]
    )

    return jsonify(pulse_res)

@app.route("/api/pulse/<project_id>", methods=["GET"])
def get_pulse_digest(project_id):
    digest = supabase_service.get_executive_digest(project_id)
    if not digest:
        return jsonify({"found": False, "message": "No pulse digest generated for today yet."})
    digest["digest_html"] = RichTextFormatter.to_html(digest["digest_md"])
    return jsonify({"found": True, "digest": digest})


# ==================== CAREERVAULT APPRAISAL API ====================

@app.route("/api/vault/generate", methods=["POST"])
def generate_vault_portfolio():
    data = request.get_json(force=True)
    user_id = data.get("user_id", "anon-user")
    user_name = Sanitizer.text(data.get("user_name", "Developer"), 50)
    quarter = Sanitizer.text(data.get("quarter", "Q3 2026"), 20)
    target_ladder = Sanitizer.text(data.get("target_ladder", "L4_TO_L5"), 20)

    updates = supabase_service.get_user_daily_updates(user_id)
    vault_res = vault_service.generate_promotion_portfolio(user_name, quarter, target_ladder, updates)
    vault_res["portfolio_html"] = RichTextFormatter.to_html(vault_res["portfolio_md"])

    # Save portfolio entry
    supabase_service.save_appraisal_entry(
        user_id, quarter, target_ladder, {"avg_score": vault_res["avg_impact_score"]}, vault_res["portfolio_md"]
    )

    return jsonify(vault_res)

@app.route("/api/vault/<user_id>", methods=["GET"])
def get_vault_entries(user_id):
    entries = supabase_service.get_user_appraisal_entries(user_id)
    updates = supabase_service.get_user_daily_updates(user_id)
    for e in entries:
        e["generated_portfolio_html"] = RichTextFormatter.to_html(e.get("generated_portfolio_md", ""))
    return jsonify({
        "entries": entries,
        "total_updates_logged": len(updates),
        "recent_updates": updates[-5:]
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)