import logging
from datetime import date
from services.llm_service import LLMService

logger = logging.getLogger("loglet_ai.pulse")

class PulseAggregatorAgent:
    """Aggregator Agent that synthesizes individual daily status updates into an Executive Sprint Health Digest."""

    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    def aggregate(self, project_name: str, target_team_size: int, updates: list):
        """Runs the LLM aggregation pass across all team member status updates for today."""

        total_submitted = len(updates)
        completion_rate = round((total_submitted / max(target_team_size, 1)) * 100, 1)
        today_str = date.today().strftime("%B %d, %Y")

        if not updates:
            empty_digest = f"""# 📊 Loglet Pulse Digest — {project_name}
**Date:** {today_str} | **Team Submissions:** 0 / {target_team_size} (0.0%)

---

### ⚪ Status
No team updates have been recorded for today yet. Team members can record their 30-second voice notes or text updates to generate the Executive Sprint Health Digest.
"""
            return {
                "digest_md": empty_digest,
                "total_submissions": 0,
                "completion_rate": 0.0
            }

        # Format individual updates for LLM input
        team_updates_block = []
        for idx, u in enumerate(updates, 1):
            name = u.get("user_name", f"Developer {idx}")
            report = u.get("final_report_md", u.get("raw_transcript", ""))
            git = u.get("git_activity", [])
            git_str = f" [Git: {len(git)} items attached]" if git else ""
            team_updates_block.append(f"--- UPDATE {idx} BY: {name}{git_str} ---\n{report}\n")

        joined_updates = "\n".join(team_updates_block)

        prompt = f"""
# ROLE
You are an Executive Engineering Director & Staff Architect synthesizing daily team updates for {project_name}.
Your job is to read all individual engineer updates submitted today and create a top-tier "Executive Sprint Health Digest" for C-suite and Product Leadership.

# INPUT STATS
Project: {project_name}
Submissions: {total_submitted} out of {target_team_size} engineers ({completion_rate}% completion rate)
Date: {today_str}

# TEAM UPDATES SUBMITTED TODAY:
<TEAM_UPDATES>
{joined_updates}
</TEAM_UPDATES>

# SYNTHESIS INSTRUCTIONS
Structure your output into EXACTLY these markdown sections:

# 🎙️ Executive Sprint Health Digest — {project_name}
**Date:** {today_str} | **Team Participation:** {total_submitted}/{target_team_size} ({completion_rate}%)

---

## 🔴 Critical Blockers & Escalations
Identify any urgent blockers affecting engineers (e.g., IAM permissions, broken staging environments, third-party API outages, unblocking peer code reviews). Be specific on WHO is blocked and ON WHAT. If zero blockers exist, output "🟢 No critical blockers reported today."

## 🟡 Risk Assessment & Sprint Scope Watch
Identify tickets or features moving slower than expected, technical debt traps, complex refactoring risks, or potential deadline slips. If none, write "🟢 All work progressing within normal velocity parameters."

## 🟢 Shipped & Completed Today
Consolidate all merged PRs, resolved tickets, bug fixes, and key achievements delivered today across the team. Group related tasks logically.

## 📊 Executive Summary & Action Items
Give a 2-sentence bottom-line verdict on overall sprint velocity, plus 2-3 high-impact action items for the Engineering Lead tomorrow morning.

# HARD CONSTRAINTS
- Be concise, authoritative, and sharp.
- Preserves exact ticket numbers (Task - N, PR #N, Story #N) mentioned by developers.
- Do NOT invent facts or guess unstated details.
- Use clean Markdown with bullet points.
"""

        try:
            digest_md, provider = self.llm.generate(prompt)
            return {
                "digest_md": digest_md,
                "total_submissions": total_submitted,
                "completion_rate": completion_rate,
                "provider": provider
            }
        except Exception as e:
            logger.error(f"Error generating Pulse Digest: {e}")
            fallback_md = f"""# 🎙️ Executive Sprint Health Digest — {project_name}
**Date:** {today_str} | **Team Participation:** {total_submitted}/{target_team_size} ({completion_rate}%)

---

## 🔴 Critical Blockers
- Active updates processed. Please review individual developer cards below.

## 🟢 Shipped Today
- {total_submitted} developer updates recorded today.
"""
            return {
                "digest_md": fallback_md,
                "total_submissions": total_submitted,
                "completion_rate": completion_rate,
                "provider": "fallback"
            }
