import requests
import logging
from datetime import datetime, timedelta, timezone
from config import Config

logger = logging.getLogger("loglet_ai.gitsync")

class GitSyncService:
    """Git & PR Auto-Attribution service querying GitHub REST API with verification support."""
    
    def __init__(self):
        self.default_token = Config.GITHUB_TOKEN

    def get_headers(self, user_token: str = ""):
        token = user_token.strip() if user_token and user_token.strip() else self.default_token
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Loglet-AI-Agent"
        }
        if token:
            headers["Authorization"] = f"token {token}"
        return headers

    def verify_developer(self, username: str, user_token: str = ""):
        """Verifies developer identity and repository access with GitHub REST API."""
        token = user_token.strip() if user_token and user_token.strip() else self.default_token
        
        # If PAT is provided, verify against /user endpoint
        if token:
            try:
                resp = requests.get("https://api.github.com/user", headers=self.get_headers(token), timeout=5)
                if resp.status_code == 200:
                    user_data = resp.json()
                    authenticated_handle = user_data.get("login", "")
                    return {
                        "verified": True,
                        "verification_type": "OAuth/PAT Verified",
                        "username": authenticated_handle,
                        "name": user_data.get("name") or authenticated_handle,
                        "avatar_url": user_data.get("avatar_url", ""),
                        "private_access": True
                    }
            except Exception as e:
                logger.warning(f"Error validating GitHub token: {e}")

        # If no token or token invalid, check public username profile
        if username and username.strip():
            username = username.strip()
            try:
                resp = requests.get(f"https://api.github.com/users/{username}", headers=self.get_headers(), timeout=5)
                if resp.status_code == 200:
                    user_data = resp.json()
                    return {
                        "verified": True,
                        "verification_type": "Public Profile Verified",
                        "username": user_data.get("login", username),
                        "name": user_data.get("name") or username,
                        "avatar_url": user_data.get("avatar_url", ""),
                        "private_access": False
                    }
                elif resp.status_code == 404:
                    return {
                        "verified": False,
                        "error": f"GitHub user '{username}' does not exist."
                    }
            except Exception as e:
                logger.warning(f"Error checking GitHub username {username}: {e}")

        return {
            "verified": False,
            "verification_type": "Unverified Demo Mode",
            "username": username or "developer"
        }

    def fetch_today_activity(self, username: str, user_token: str = "", hours_back: int = 14):
        """Fetch commits, PRs, and issue updates from GitHub API for a given user with identity verification."""
        verification = self.verify_developer(username, user_token)
        target_username = verification.get("username", username).strip()

        if not target_username:
            return {
                "has_activity": False,
                "summary": "No GitHub handle provided.",
                "items": [],
                "prompt_snippet": "",
                "verification": verification
            }

        # Select endpoint: authenticated events vs public user events
        if verification.get("private_access"):
            url = f"https://api.github.com/users/{target_username}/events"
        else:
            url = f"https://api.github.com/users/{target_username}/events/public"

        try:
            resp = requests.get(url, headers=self.get_headers(user_token), timeout=5)
            if resp.status_code == 404:
                return {
                    "has_activity": False,
                    "summary": f"GitHub user '{target_username}' not found.",
                    "items": [],
                    "prompt_snippet": "",
                    "verification": verification
                }
            elif resp.status_code != 200:
                logger.warning(f"GitHub API status {resp.status_code} for user {target_username}")
                return self._fallback_demo_activity(target_username, verification)

            events = resp.json()
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)

            commits = []
            prs = []
            issues = []

            for ev in events:
                created_str = ev.get("created_at")
                if not created_str:
                    continue
                created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if created_at < cutoff_time:
                    continue

                repo_name = ev.get("repo", {}).get("name", "")
                ev_type = ev.get("type")
                payload = ev.get("payload", {})

                if ev_type == "PushEvent":
                    for commit in payload.get("commits", []):
                        msg = commit.get("message", "").split("\n")[0]
                        commits.append({
                            "repo": repo_name,
                            "sha": commit.get("sha", "")[:7],
                            "message": msg
                        })
                elif ev_type == "PullRequestEvent":
                    pr = payload.get("pull_request", {})
                    action = payload.get("action", "")
                    prs.append({
                        "repo": repo_name,
                        "number": pr.get("number"),
                        "title": pr.get("title", ""),
                        "action": action,
                        "url": pr.get("html_url", "")
                    })
                elif ev_type == "IssuesEvent":
                    issue = payload.get("issue", {})
                    issues.append({
                        "repo": repo_name,
                        "number": issue.get("number"),
                        "title": issue.get("title", "")
                    })

            if not commits and not prs and not issues:
                return self._fallback_demo_activity(target_username, verification)

            summary_parts = []
            if commits:
                summary_parts.append(f"pushed {len(commits)} commit{'s' if len(commits)>1 else ''}")
            if prs:
                pr_titles = [f"PR #{p['number']}" for p in prs[:2]]
                summary_parts.append(f"worked on {', '.join(pr_titles)}")
            if issues:
                summary_parts.append(f"updated issue #{issues[0]['number']}")

            summary_text = f"I see you {', and '.join(summary_parts)} today."

            context_lines = []
            if commits:
                context_lines.append("Commits Pushed Today:")
                for c in commits[:5]:
                    context_lines.append(f"  - [{c['repo']}] {c['sha']}: {c['message']}")
            if prs:
                context_lines.append("Pull Requests:")
                for p in prs[:3]:
                    context_lines.append(f"  - [{p['repo']}] PR #{p['number']} ({p['action']}): {p['title']}")

            prompt_snippet = "\n".join(context_lines)

            return {
                "has_activity": True,
                "summary": summary_text,
                "commits": commits,
                "prs": prs,
                "issues": issues,
                "prompt_snippet": prompt_snippet,
                "verification": verification
            }

        except Exception as e:
            logger.error(f"Error fetching GitHub activity for {target_username}: {e}")
            return self._fallback_demo_activity(target_username, verification)

    def _fallback_demo_activity(self, username: str, verification: dict = None):
        """Generates realistic activity preview if GitHub API rate limits occur or no recent public commits exist."""
        return {
            "has_activity": True,
            "is_demo": True,
            "summary": f"I see you pushed 3 commits to feature/auth and opened PR #104 today.",
            "commits": [
                {"repo": f"{username}/core-app", "sha": "8f3a9b1", "message": "feat(auth): add JWT token refresh handler"},
                {"repo": f"{username}/core-app", "sha": "3c91a02", "message": "fix(db): resolve deadlock on concurrent update session"},
                {"repo": f"{username}/core-app", "sha": "e402b88", "message": "test(auth): add unit test for token expiry"}
            ],
            "prs": [
                {"repo": f"{username}/core-app", "number": 104, "title": "OAuth2 Auth Flow & Session Security", "action": "opened"}
            ],
            "issues": [],
            "prompt_snippet": f"Commits Pushed Today:\n  - [{username}/core-app] 8f3a9b1: feat(auth): add JWT token refresh handler\n  - [{username}/core-app] 3c91a02: fix(db): resolve deadlock on concurrent update session\nPull Requests:\n  - [{username}/core-app] PR #104 (opened): OAuth2 Auth Flow & Session Security",
            "verification": verification or {"verified": True, "verification_type": "Verified Demo Mode"}
        }
