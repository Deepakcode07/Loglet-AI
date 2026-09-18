import os
import uuid
import logging
from datetime import datetime, date
from config import Config

logger = logging.getLogger("loglet_ai.supabase")

class LocalMockStore:
    """In-memory + JSON fallback store when Supabase credentials are not configured."""
    def __init__(self):
        self.projects = {}
        self.users = {}
        self.daily_updates = []
        self.executive_digests = {}
        self.appraisal_entries = []

    def create_project(self, name, target_team_size, manager_email):
        proj_id = str(uuid.uuid4())
        invite_code = f"LOGLET-{uuid.uuid4().hex[:6].upper()}"
        project = {
            "id": proj_id,
            "name": name,
            "target_team_size": int(target_team_size),
            "invite_code": invite_code,
            "manager_email": manager_email,
            "created_at": datetime.now().isoformat()
        }
        self.projects[proj_id] = project
        self.projects[invite_code] = project
        logger.info(f"Mock DB: Created project {name} with code {invite_code}")
        return project

    def get_project_by_invite(self, invite_code):
        return self.projects.get(invite_code.strip().upper())

    def get_project_by_id(self, project_id):
        return self.projects.get(project_id)

    def join_project(self, email, name, invite_code, github_username=""):
        project = self.get_project_by_invite(invite_code)
        if not project:
            raise ValueError(f"Invalid invite code: {invite_code}")
        
        user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, email.lower()))
        user = {
            "id": user_id,
            "email": email.lower(),
            "name": name,
            "role": "developer" if email != project["manager_email"] else "manager",
            "project_id": project["id"],
            "github_username": github_username,
            "joined_at": datetime.now().isoformat()
        }
        self.users[user_id] = user
        self.users[email.lower()] = user
        logger.info(f"Mock DB: User {name} ({email}) joined project {project['name']}")
        return user, project

    def get_project_members(self, project_id):
        return [u for u in self.users.values() if isinstance(u, dict) and u.get("project_id") == project_id]

    def save_daily_update(self, user_id, project_id, user_name, raw_transcript, final_report_md, 
                          completed_tasks=None, in_progress_tasks=None, blockers=None, git_activity=None, impact_score=65):
        today_str = date.today().isoformat()
        update_id = str(uuid.uuid4())
        entry = {
            "id": update_id,
            "user_id": user_id or "anon-user",
            "project_id": project_id or "default-project",
            "user_name": user_name or "Engineer",
            "date": today_str,
            "raw_transcript": raw_transcript,
            "final_report_md": final_report_md,
            "completed_tasks": completed_tasks or [],
            "in_progress_tasks": in_progress_tasks or [],
            "blockers": blockers or [],
            "git_activity": git_activity or [],
            "impact_score": impact_score,
            "created_at": datetime.now().isoformat()
        }
        self.daily_updates.append(entry)
        logger.info(f"Mock DB: Saved daily update for {user_name} (Score: {impact_score})")
        return entry

    def get_team_daily_updates(self, project_id, date_str=None):
        if not date_str:
            date_str = date.today().isoformat()
        return [u for u in self.daily_updates if u.get("project_id") == project_id and u.get("date") == date_str]

    def get_user_daily_updates(self, user_id):
        return [u for u in self.daily_updates if u.get("user_id") == user_id]

    def save_executive_digest(self, project_id, date_str, digest_md, total_submissions, completion_rate):
        key = f"{project_id}:{date_str}"
        digest = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "date": date_str,
            "digest_md": digest_md,
            "total_submissions": total_submissions,
            "completion_rate": completion_rate,
            "created_at": datetime.now().isoformat()
        }
        self.executive_digests[key] = digest
        return digest

    def get_executive_digest(self, project_id, date_str=None):
        if not date_str:
            date_str = date.today().isoformat()
        key = f"{project_id}:{date_str}"
        return self.executive_digests.get(key)

    def save_appraisal_entry(self, user_id, quarter, target_ladder, impact_summary, portfolio_md):
        entry = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "quarter": quarter,
            "target_ladder": target_ladder,
            "impact_summary": impact_summary or {},
            "generated_portfolio_md": portfolio_md,
            "created_at": datetime.now().isoformat()
        }
        self.appraisal_entries.append(entry)
        return entry

    def get_user_appraisal_entries(self, user_id):
        return [e for e in self.appraisal_entries if e.get("user_id") == user_id]


class SupabaseService:
    """Supabase client wrapper with seamless local fallback."""
    def __init__(self):
        self.url = Config.SUPABASE_URL
        self.key = Config.SUPABASE_KEY
        self.client = None
        self.mock = LocalMockStore()
        
        if self.url and self.key:
            try:
                from supabase import create_client
                self.client = create_client(self.url, self.key)
                logger.info("Supabase client initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize Supabase client: {e}. Operating in resilient local mock mode.")
        else:
            logger.info("No Supabase URL/KEY configured. Operating in resilient local mock mode.")

    def is_connected(self):
        return self.client is not None

    def create_project(self, name, target_team_size, manager_email):
        if not self.client:
            return self.mock.create_project(name, target_team_size, manager_email)
        try:
            invite_code = f"LOGLET-{uuid.uuid4().hex[:6].upper()}"
            data = {
                "name": name,
                "target_team_size": int(target_team_size),
                "invite_code": invite_code,
                "manager_email": manager_email
            }
            res = self.client.table("projects").insert(data).execute()
            return res.data[0] if res.data else self.mock.create_project(name, target_team_size, manager_email)
        except Exception as e:
            logger.error(f"Supabase error in create_project: {e}")
            return self.mock.create_project(name, target_team_size, manager_email)

    def get_project_by_invite(self, invite_code):
        if not self.client:
            return self.mock.get_project_by_invite(invite_code)
        try:
            res = self.client.table("projects").select("*").eq("invite_code", invite_code.strip().upper()).execute()
            if res.data:
                return res.data[0]
            return self.mock.get_project_by_invite(invite_code)
        except Exception as e:
            logger.error(f"Supabase error in get_project_by_invite: {e}")
            return self.mock.get_project_by_invite(invite_code)

    def join_project(self, email, name, invite_code, github_username=""):
        if not self.client:
            return self.mock.join_project(email, name, invite_code, github_username)
        try:
            project = self.get_project_by_invite(invite_code)
            if not project:
                raise ValueError("Invalid invite code")
            role = "developer" if email != project.get("manager_email") else "manager"
            user_data = {
                "email": email.lower(),
                "name": name,
                "role": role,
                "project_id": project["id"],
                "github_username": github_username
            }
            res = self.client.table("users").upsert(user_data, on_conflict="email").execute()
            user = res.data[0] if res.data else {}
            return user, project
        except Exception as e:
            logger.error(f"Supabase error in join_project: {e}")
            return self.mock.join_project(email, name, invite_code, github_username)

    def get_project_members(self, project_id):
        if not self.client:
            return self.mock.get_project_members(project_id)
        try:
            res = self.client.table("users").select("*").eq("project_id", project_id).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"Supabase error in get_project_members: {e}")
            return self.mock.get_project_members(project_id)

    def save_daily_update(self, user_id, project_id, user_name, raw_transcript, final_report_md, 
                          completed_tasks=None, in_progress_tasks=None, blockers=None, git_activity=None, impact_score=65):
        if not self.client:
            return self.mock.save_daily_update(user_id, project_id, user_name, raw_transcript, final_report_md,
                                                completed_tasks, in_progress_tasks, blockers, git_activity, impact_score)
        try:
            today_str = date.today().isoformat()
            data = {
                "user_id": user_id,
                "project_id": project_id,
                "user_name": user_name,
                "date": today_str,
                "raw_transcript": raw_transcript,
                "final_report_md": final_report_md,
                "completed_tasks": completed_tasks or [],
                "in_progress_tasks": in_progress_tasks or [],
                "blockers": blockers or [],
                "git_activity": git_activity or [],
                "impact_score": impact_score
            }
            res = self.client.table("daily_updates").insert(data).execute()
            return res.data[0] if res.data else self.mock.save_daily_update(
                user_id, project_id, user_name, raw_transcript, final_report_md, 
                completed_tasks, in_progress_tasks, blockers, git_activity, impact_score
            )
        except Exception as e:
            logger.error(f"Supabase error in save_daily_update: {e}")
            return self.mock.save_daily_update(
                user_id, project_id, user_name, raw_transcript, final_report_md, 
                completed_tasks, in_progress_tasks, blockers, git_activity, impact_score
            )

    def get_team_daily_updates(self, project_id, date_str=None):
        if not date_str:
            date_str = date.today().isoformat()
        if not self.client:
            return self.mock.get_team_daily_updates(project_id, date_str)
        try:
            res = self.client.table("daily_updates").select("*").eq("project_id", project_id).eq("date", date_str).execute()
            return res.data or self.mock.get_team_daily_updates(project_id, date_str)
        except Exception as e:
            logger.error(f"Supabase error in get_team_daily_updates: {e}")
            return self.mock.get_team_daily_updates(project_id, date_str)

    def get_user_daily_updates(self, user_id):
        if not self.client:
            return self.mock.get_user_daily_updates(user_id)
        try:
            res = self.client.table("daily_updates").select("*").eq("user_id", user_id).execute()
            return res.data or self.mock.get_user_daily_updates(user_id)
        except Exception as e:
            logger.error(f"Supabase error in get_user_daily_updates: {e}")
            return self.mock.get_user_daily_updates(user_id)

    def save_executive_digest(self, project_id, date_str, digest_md, total_submissions, completion_rate):
        if not self.client:
            return self.mock.save_executive_digest(project_id, date_str, digest_md, total_submissions, completion_rate)
        try:
            data = {
                "project_id": project_id,
                "date": date_str,
                "digest_md": digest_md,
                "total_submissions": total_submissions,
                "completion_rate": float(completion_rate)
            }
            res = self.client.table("executive_digests").upsert(data, on_conflict="project_id,date").execute()
            return res.data[0] if res.data else self.mock.save_executive_digest(project_id, date_str, digest_md, total_submissions, completion_rate)
        except Exception as e:
            logger.error(f"Supabase error in save_executive_digest: {e}")
            return self.mock.save_executive_digest(project_id, date_str, digest_md, total_submissions, completion_rate)

    def get_executive_digest(self, project_id, date_str=None):
        if not date_str:
            date_str = date.today().isoformat()
        if not self.client:
            return self.mock.get_executive_digest(project_id, date_str)
        try:
            res = self.client.table("executive_digests").select("*").eq("project_id", project_id).eq("date", date_str).execute()
            if res.data:
                return res.data[0]
            return self.mock.get_executive_digest(project_id, date_str)
        except Exception as e:
            logger.error(f"Supabase error in get_executive_digest: {e}")
            return self.mock.get_executive_digest(project_id, date_str)

    def save_appraisal_entry(self, user_id, quarter, target_ladder, impact_summary, portfolio_md):
        if not self.client:
            return self.mock.save_appraisal_entry(user_id, quarter, target_ladder, impact_summary, portfolio_md)
        try:
            data = {
                "user_id": user_id,
                "quarter": quarter,
                "target_ladder": target_ladder,
                "impact_summary": impact_summary or {},
                "generated_portfolio_md": portfolio_md
            }
            res = self.client.table("appraisal_vault_entries").insert(data).execute()
            return res.data[0] if res.data else self.mock.save_appraisal_entry(user_id, quarter, target_ladder, impact_summary, portfolio_md)
        except Exception as e:
            logger.error(f"Supabase error in save_appraisal_entry: {e}")
            return self.mock.save_appraisal_entry(user_id, quarter, target_ladder, impact_summary, portfolio_md)

    def get_user_appraisal_entries(self, user_id):
        if not self.client:
            return self.mock.get_user_appraisal_entries(user_id)
        try:
            res = self.client.table("appraisal_vault_entries").select("*").eq("user_id", user_id).execute()
            return res.data or self.mock.get_user_appraisal_entries(user_id)
        except Exception as e:
            logger.error(f"Supabase error in get_user_appraisal_entries: {e}")
            return self.mock.get_user_appraisal_entries(user_id)
