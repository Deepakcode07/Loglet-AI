import logging
from services.llm_service import LLMService

logger = logging.getLogger("loglet_ai.vault")

LADDER_DESCRIPTIONS = {
    "L3_TO_L4": "Mid-Level Software Engineer (L4) — Demonstrates ownership, independent execution of complex features, solid code quality, and consistent delivery.",
    "L4_TO_L5": "Senior Software Engineer (L5) — Demonstrates technical leadership, architectural influence, unblocking peers, driving system reliability, and mentoring team members.",
    "L5_TO_L6": "Staff / Principal Software Engineer (L6) — Demonstrates cross-team strategic impact, organization-wide technical vision, high-consequence system architecture, and technical mentorship."
}

class CareerVaultService:
    """CareerVault Promotion Portfolio & Performance Appraisal Generator."""

    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    def calculate_impact_score(self, report_md: str, git_items: list):
        """Calculates a daily impact score (1-100) based on work complexity signal."""
        base_score = 65
        text_len = len(report_md)
        if text_len > 300:
            base_score += 10
        if "blocker" in report_md.lower() or "unblock" in report_md.lower():
            base_score += 10
        if "architecture" in report_md.lower() or "migration" in report_md.lower() or "refactor" in report_md.lower():
            base_score += 10
        if git_items:
            base_score += min(len(git_items) * 3, 10)
        return min(base_score, 98)

    def generate_promotion_portfolio(self, user_name: str, quarter: str, target_ladder: str, updates: list):
        """Compiles historical daily updates into a structured Promotion Portfolio Brag Document."""

        ladder_info = LADDER_DESCRIPTIONS.get(target_ladder, LADDER_DESCRIPTIONS["L4_TO_L5"])
        total_updates = len(updates)

        if not updates:
            # Fallback sample portfolio if user has no updates saved yet
            updates = [
                {"date": "2026-09-01", "final_report_md": "## Completed Today\n- **Task - 1042** Designed resilient Supabase integration architecture with automatic mock fallback.\n- Merged PR #42 for session security.", "impact_score": 85},
                {"date": "2026-09-10", "final_report_md": "## Completed Today\n- **Task - 1105** Refactored authentication pipeline reducing latency by 40%.\n- Unblocked 2 frontend engineers on API contracts.", "impact_score": 92}
            ]

        # Aggregate updates text
        combined_logs = []
        scores = []
        for u in updates:
            d = u.get("date", "2026")
            report = u.get("final_report_md", u.get("raw_transcript", ""))
            score = u.get("impact_score", 70)
            scores.append(score)
            combined_logs.append(f"--- Log [{d}] (Impact Score: {score}) ---\n{report}\n")

        avg_score = round(sum(scores) / max(len(scores), 1), 1)
        joined_logs = "\n".join(combined_logs)

        prompt = f"""
# ROLE
You are a Principal Engineering Director & Career Coach writing an official Promotion Portfolio & Annual Appraisal Brag Document for {user_name}.
This document will be presented to the Engineering Promotion Committee and VP of Engineering.

# TARGET PROMOTION LEVEL
Target Transition: {target_ladder}
Level Competency Target: {ladder_info}
Timeframe: {quarter}
Total Recorded Work Updates: {total_updates}
Average Career Impact Score: {avg_score} / 100

# HISTORICAL WORK LOGS & IMPACT DATA:
<WORK_LOGS>
{joined_logs}
</WORK_LOGS>

# DOCUMENT STRUCTURE & INSTRUCTIONS
Synthesize the work logs into a compelling, evidence-backed Promotion Portfolio formatted in clean Markdown:

# 🏆 Promotion Portfolio & Appraisal Vault — {user_name}
**Target Level:** {target_ladder.replace('_', ' ')} | **Timeframe:** {quarter} | **Avg Impact Score:** {avg_score} / 100

---

## 📈 Executive Summary & Impact Overview
Write a powerful 3-paragraph summary highlighting why {user_name} is performing at the target level. Quantify achievements, consistency, and technical ownership.

## 🏛️ Key Architectural & Technical Contributions
Group major engineering accomplishments, system migrations, database designs, and performance optimizations. Highlight ticket/task numbers (**Task - N**, **PR #N**).

## 🚀 Execution Reliability & Delivery Track Record
Detail consistent feature delivery, bug resolutions, and high-consequence code changes merged into production.

## 🤝 Technical Leadership, Mentorship & Unblocking Peers
Highlight instances where {user_name} unblocked colleagues, streamlined team processes, or resolved systemic team bottlenecks.

## 🎯 Engineering Ladder Rubric Alignment ({target_ladder})
Provide a table evaluating performance against 4 standard engineering competencies:
| Competency Rubric | Performance Evidence | Level Status |
| --- | --- | --- |
| **Technical Ownership** | ... | ✅ Meets / Exceeds |
| **System Architecture** | ... | ✅ Meets / Exceeds |
| **Execution Velocity** | ... | ✅ Meets / Exceeds |
| **Team Unblocking** | ... | ✅ Meets / Exceeds |

# HARD CONSTRAINTS
- Professional, persuasive, and data-backed tone.
- Preserve all ticket numbers and PR references.
- No filler phrases; frame every achievement with clear impact.
"""

        try:
            portfolio_md, provider = self.llm.generate(prompt)
            return {
                "portfolio_md": portfolio_md,
                "avg_impact_score": avg_score,
                "total_updates": total_updates,
                "provider": provider
            }
        except Exception as e:
            logger.error(f"Error generating Promotion Portfolio: {e}")
            fallback_md = f"# 🏆 Promotion Portfolio — {user_name}\n\nGenerated for timeframe: {quarter}.\nProcessed {total_updates} work updates with avg impact score {avg_score}."
            return {
                "portfolio_md": fallback_md,
                "avg_impact_score": avg_score,
                "total_updates": total_updates,
                "provider": "fallback"
            }
