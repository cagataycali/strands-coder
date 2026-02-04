"""Scheduler tool for managing cron-based and one-time job schedules via GitHub Action variables.

This module provides a scheduling system for autonomous agents, storing job configurations
in GitHub repository variables and checking which jobs should run at any given time.

Key Features:
1. Store schedules in GitHub Action variables (AGENT_SCHEDULES)
2. Cron expression support for recurring jobs
3. One-time scheduled jobs with run_at datetime
4. Job-specific configuration (system_prompt, tools, context, model)
5. Check which jobs should run now
6. Enable/disable jobs without deletion
7. Auto-cleanup of completed one-time jobs

Schedule Format (stored as JSON in AGENT_SCHEDULES variable):
{
    "jobs": {
        "daily_review": {
            "cron": "0 9 * * *",
            "enabled": true,
            "system_prompt": "You are a code reviewer...",
            "tools": "strands_tools:shell;strands_coder:use_github",
            "prompt": "Review open PRs and provide feedback",
            "model": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "max_tokens": 10000
        },
        "deploy_friday": {
            "run_at": "2024-01-19T15:00:00Z",
            "enabled": true,
            "prompt": "Deploy the release to production",
            "once": true
        }
    },
    "timezone": "UTC"
}

Usage Examples:
```python
from strands import Agent
from strands_coder.tools.scheduler import scheduler

agent = Agent(tools=[scheduler])

# List all scheduled jobs
result = agent.tool.scheduler(action="list")

# Add a recurring job (cron)
result = agent.tool.scheduler(
    action="add",
    job_id="daily_review",
    cron="0 9 * * *",
    prompt="Review open PRs",
    system_prompt="You are a code reviewer focused on best practices",
    tools="strands_tools:shell;strands_coder:use_github"
)

# Schedule a one-time job for a specific datetime
result = agent.tool.scheduler(
    action="add",
    job_id="deploy_v2",
    run_at="2024-01-20T14:00:00Z",
    prompt="Deploy version 2.0 to production",
    once=True  # Auto-remove after execution
)

# Check which jobs should run now
result = agent.tool.scheduler(action="check")

# Enable/disable a job
result = agent.tool.scheduler(action="disable", job_id="daily_review")
result = agent.tool.scheduler(action="enable", job_id="daily_review")

# Remove a job
result = agent.tool.scheduler(action="remove", job_id="daily_review")
```
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import requests
from strands import tool

# GitHub API endpoint
GITHUB_API_URL = "https://api.github.com"

# Default variable name for schedules
SCHEDULES_VARIABLE = "AGENT_SCHEDULES"


def _get_github_token() -> str:
    """Get GitHub token from environment variables."""
    return os.environ.get("PAT_TOKEN", os.environ.get("GITHUB_TOKEN", ""))


def _get_repository() -> str:
    """Get repository from environment."""
    return os.environ.get("GITHUB_REPOSITORY", "")


def _get_github_variable(repository: str, name: str, token: str) -> dict[str, Any]:
    """Fetch a GitHub repository variable."""
    url = f"{GITHUB_API_URL}/repos/{repository}/actions/variables/{name}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            return {"success": True, "value": response.json().get("value", "{}")}
        elif response.status_code == 404:
            return {"success": True, "value": "{}"}  # Variable doesn't exist yet
        else:
            return {
                "success": False,
                "message": f"HTTP {response.status_code}: {response.text}",
            }
    except Exception as e:
        return {"success": False, "message": str(e)}


def _set_github_variable(
    repository: str, name: str, value: str, token: str
) -> dict[str, Any]:
    """Create or update a GitHub repository variable."""
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Try to update first
    url = f"{GITHUB_API_URL}/repos/{repository}/actions/variables/{name}"
    response = requests.patch(
        url, headers=headers, json={"name": name, "value": value}, timeout=30
    )

    if response.status_code == 204:
        return {"success": True, "message": f"Variable {name} updated"}

    # If not found, create it
    if response.status_code == 404:
        url = f"{GITHUB_API_URL}/repos/{repository}/actions/variables"
        response = requests.post(
            url, headers=headers, json={"name": name, "value": value}, timeout=30
        )
        if response.status_code == 201:
            return {"success": True, "message": f"Variable {name} created"}

    return {
        "success": False,
        "message": f"HTTP {response.status_code}: {response.text}",
    }


def _parse_cron(cron_expr: str) -> dict[str, Any]:
    """Parse cron expression into components.

    Format: minute hour day_of_month month day_of_week
    Supports: *, specific values, ranges (1-5), steps (*/15), lists (1,3,5)
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr} (expected 5 fields)")

    return {
        "minute": parts[0],
        "hour": parts[1],
        "day_of_month": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }


def _cron_field_matches(field: str, value: int, max_value: int) -> bool:
    """Check if a cron field matches a given value."""
    if field == "*":
        return True

    # Handle step values like */15
    if field.startswith("*/"):
        step = int(field[2:])
        return value % step == 0

    # Handle ranges like 1-5
    if "-" in field and "/" not in field:
        start, end = field.split("-")
        return int(start) <= value <= int(end)

    # Handle range with step like 0-30/5
    if "-" in field and "/" in field:
        range_part, step = field.split("/")
        start, end = range_part.split("-")
        if int(start) <= value <= int(end):
            return (value - int(start)) % int(step) == 0
        return False

    # Handle lists like 1,3,5
    if "," in field:
        return value in [int(v) for v in field.split(",")]

    # Direct match
    return int(field) == value


def _cron_matches(cron_expr: str, dt: datetime) -> bool:
    """Check if a cron expression matches a given datetime."""
    try:
        cron = _parse_cron(cron_expr)

        # Check each field
        if not _cron_field_matches(cron["minute"], dt.minute, 59):
            return False
        if not _cron_field_matches(cron["hour"], dt.hour, 23):
            return False
        if not _cron_field_matches(cron["day_of_month"], dt.day, 31):
            return False
        if not _cron_field_matches(cron["month"], dt.month, 12):
            return False

        # day_of_week: 0=Sunday in cron, but Python's weekday() has 0=Monday
        # Convert Python weekday to cron format (Sunday=0)
        python_weekday = dt.weekday()  # 0=Monday, 6=Sunday
        cron_weekday = (python_weekday + 1) % 7  # Convert to 0=Sunday

        if not _cron_field_matches(cron["day_of_week"], cron_weekday, 6):
            return False

        return True
    except Exception:
        return False


def _run_at_matches(run_at: str, now: datetime) -> bool:
    """Check if a run_at datetime should trigger now.

    A job matches if:
    - run_at time has passed (is in the past or within the current hour)
    - We check within a 60-minute window to handle hourly control loop

    Args:
        run_at: ISO format datetime string (e.g., "2024-01-20T14:00:00Z")
        now: Current UTC datetime

    Returns:
        True if the job should run now
    """
    try:
        # Parse run_at (handle various formats)
        run_at_str = run_at.replace("Z", "+00:00")
        if "+" not in run_at_str and "-" not in run_at_str[10:]:
            # No timezone, assume UTC
            run_at_dt = datetime.fromisoformat(run_at_str)
        else:
            run_at_dt = datetime.fromisoformat(run_at_str)
            # Convert to naive UTC for comparison
            run_at_dt = run_at_dt.replace(tzinfo=None)

        # Check if run_at is in the past or within the next minute
        # This gives a 60-minute window for hourly checks
        diff_minutes = (now - run_at_dt).total_seconds() / 60

        # Job should run if run_at is in the past (up to 60 min ago) or right now
        return -1 <= diff_minutes <= 60
    except Exception:
        return False


def _get_schedules(repository: str, token: str) -> dict[str, Any]:
    """Get current schedules from GitHub variable."""
    result = _get_github_variable(repository, SCHEDULES_VARIABLE, token)
    if not result["success"]:
        return {"jobs": {}, "timezone": "UTC"}

    try:
        return (
            json.loads(result["value"])
            if result["value"]
            else {"jobs": {}, "timezone": "UTC"}
        )
    except json.JSONDecodeError:
        return {"jobs": {}, "timezone": "UTC"}


def _save_schedules(
    repository: str, schedules: dict[str, Any], token: str
) -> dict[str, Any]:
    """Save schedules to GitHub variable."""
    return _set_github_variable(
        repository, SCHEDULES_VARIABLE, json.dumps(schedules, indent=2), token
    )


@tool
def scheduler(
    action: str,
    job_id: str | None = None,
    cron: str | None = None,
    run_at: str | None = None,
    once: bool = False,
    prompt: str | None = None,
    system_prompt: str | None = None,
    tools: str | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
    context: str | None = None,
    repository: str | None = None,
) -> dict[str, Any]:
    """Manage scheduled jobs for the autonomous agent.

    This tool manages a schedule of jobs stored in GitHub Action variables.
    Jobs can be recurring (cron) or one-time (run_at).
    The control loop workflow checks this schedule hourly and dispatches jobs.

    Actions:
        - "list": List all scheduled jobs
        - "check": Check which jobs should run now (returns jobs to dispatch)
        - "add": Add or update a job
        - "remove": Remove a job
        - "enable": Enable a disabled job
        - "disable": Disable a job without removing it
        - "get": Get details of a specific job

    Args:
        action: The action to perform
        job_id: Job identifier (required for add, remove, enable, disable, get)
        cron: Cron expression for recurring jobs - format: "minute hour day month weekday"
        run_at: ISO datetime for one-time jobs - format: "2024-01-20T14:00:00Z"
        once: If True, auto-remove job after execution (for one-time jobs)
        prompt: The prompt to run for this job
        system_prompt: Custom system prompt for this job
        tools: Tool configuration string (format: pkg:tool1,tool2;pkg2:tool3)
        model: Model ID to use for this job
        max_tokens: Max tokens for model response
        context: Additional context to include in the prompt
        repository: GitHub repository (defaults to GITHUB_REPOSITORY env var)

    Returns:
        Dict with status and operation results

    Examples:
        ```python
        # List all jobs
        scheduler(action="list")

        # Add a recurring daily code review job at 9 AM UTC
        scheduler(
            action="add",
            job_id="daily_review",
            cron="0 9 * * *",
            prompt="Review all open PRs and provide feedback",
            system_prompt="You are a senior code reviewer",
            tools="strands_tools:shell;strands_coder:use_github"
        )

        # Schedule a one-time deployment for a specific time
        scheduler(
            action="add",
            job_id="deploy_v2",
            run_at="2024-01-20T14:00:00Z",
            prompt="Deploy version 2.0 to production and verify health checks",
            once=True  # Auto-remove after execution
        )

        # Schedule a reminder (one-time, keeps in history)
        scheduler(
            action="add",
            job_id="team_meeting_reminder",
            run_at="2024-01-19T09:00:00Z",
            prompt="Remind the team about the standup meeting"
        )

        # Check which jobs should run now (used by control loop)
        scheduler(action="check")

        # Disable a job temporarily
        scheduler(action="disable", job_id="daily_review")
        ```

    Cron Expression Format (for recurring jobs):
        minute (0-59)
        hour (0-23)
        day of month (1-31)
        month (1-12)
        day of week (0-6, Sunday=0)

        Special characters:
        * = any value
        */N = every N (e.g., */15 = every 15 minutes)
        N-M = range (e.g., 1-5 = Monday to Friday)
        N,M,O = list (e.g., 1,3,5)

        Examples:
        - "0 * * * *" = every hour at minute 0
        - "0 9 * * *" = daily at 9:00 AM
        - "0 9 * * 1-5" = weekdays at 9:00 AM
        - "*/30 * * * *" = every 30 minutes
        - "0 10 * * 1" = Mondays at 10:00 AM

    Run At Format (for one-time jobs):
        ISO 8601 datetime format
        Examples:
        - "2024-01-20T14:00:00Z" = January 20, 2024 at 2:00 PM UTC
        - "2024-01-20T09:30:00" = January 20, 2024 at 9:30 AM (assumes UTC)
    """
    try:
        repo = repository or _get_repository()
        if not repo:
            return {
                "status": "error",
                "content": [
                    {
                        "text": "Error: Repository not specified and GITHUB_REPOSITORY not set"
                    }
                ],
            }

        token = _get_github_token()
        if not token:
            return {
                "status": "error",
                "content": [
                    {
                        "text": "Error: GitHub token not available (PAT_TOKEN or GITHUB_TOKEN)"
                    }
                ],
            }

        # LIST - Show all jobs
        if action == "list":
            schedules = _get_schedules(repo, token)
            jobs = schedules.get("jobs", {})

            if not jobs:
                return {
                    "status": "success",
                    "content": [{"text": f"No scheduled jobs found in {repo}"}],
                }

            lines = [f"## Scheduled Jobs ({len(jobs)} total)\n"]
            lines.append(f"**Repository:** {repo}")
            lines.append(f"**Timezone:** {schedules.get('timezone', 'UTC')}\n")

            for jid, job in jobs.items():
                enabled = "✅" if job.get("enabled", True) else "❌"
                job_type = "🔄" if job.get("cron") else "📅"
                lines.append(f"### {enabled} {job_type} `{jid}`")

                if job.get("cron"):
                    lines.append(f"- **Cron:** `{job['cron']}` (recurring)")
                if job.get("run_at"):
                    once_marker = " (once, auto-remove)" if job.get("once") else ""
                    lines.append(f"- **Run At:** `{job['run_at']}`{once_marker}")

                lines.append(f"- **Prompt:** {job.get('prompt', 'N/A')[:100]}...")
                if job.get("system_prompt"):
                    lines.append(f"- **System Prompt:** {job['system_prompt'][:50]}...")
                if job.get("tools"):
                    lines.append(f"- **Tools:** {job['tools']}")
                if job.get("model"):
                    lines.append(f"- **Model:** {job['model']}")
                lines.append("")

            return {"status": "success", "content": [{"text": "\n".join(lines)}]}

        # CHECK - Find jobs that should run now
        elif action == "check":
            schedules = _get_schedules(repo, token)
            jobs = schedules.get("jobs", {})
            now = datetime.utcnow()

            jobs_to_run = []
            jobs_to_remove = []  # For once=True jobs

            for jid, job in jobs.items():
                if not job.get("enabled", True):
                    continue

                should_run = False

                # Check cron expression (recurring jobs)
                cron_expr = job.get("cron")
                if cron_expr and _cron_matches(cron_expr, now):
                    should_run = True

                # Check run_at datetime (one-time jobs)
                run_at_str = job.get("run_at")
                if run_at_str and _run_at_matches(run_at_str, now):
                    should_run = True
                    # Mark for removal if once=True
                    if job.get("once"):
                        jobs_to_remove.append(jid)

                if should_run:
                    jobs_to_run.append(
                        {
                            "job_id": jid,
                            "prompt": job.get("prompt", ""),
                            "system_prompt": job.get("system_prompt"),
                            "tools": job.get("tools"),
                            "model": job.get("model"),
                            "max_tokens": job.get("max_tokens"),
                            "context": job.get("context"),
                            "once": job.get("once", False),
                        }
                    )

            # Remove once=True jobs that have been triggered
            if jobs_to_remove:
                for jid in jobs_to_remove:
                    del schedules["jobs"][jid]
                _save_schedules(repo, schedules, token)

            if not jobs_to_run:
                return {
                    "status": "success",
                    "content": [
                        {
                            "text": f"No jobs scheduled to run at {now.strftime('%Y-%m-%d %H:%M')} UTC"
                        }
                    ],
                    "jobs_to_run": [],
                }

            lines = [f"## Jobs to Run ({len(jobs_to_run)} jobs)\n"]
            lines.append(f"**Current Time:** {now.strftime('%Y-%m-%d %H:%M')} UTC\n")

            for job in jobs_to_run:
                once_note = " 🗑️ (will be removed)" if job.get("once") else ""
                lines.append(f"### `{job['job_id']}`{once_note}")
                lines.append(f"- **Prompt:** {job['prompt'][:100]}...")
                if job.get("tools"):
                    lines.append(f"- **Tools:** {job['tools']}")
                lines.append("")

            if jobs_to_remove:
                lines.append(
                    f"\n*Removed {len(jobs_to_remove)} one-time job(s): {', '.join(jobs_to_remove)}*"
                )

            return {
                "status": "success",
                "content": [{"text": "\n".join(lines)}],
                "jobs_to_run": jobs_to_run,
            }

        # ADD - Add or update a job
        elif action == "add":
            if not job_id:
                return {
                    "status": "error",
                    "content": [{"text": "Error: job_id is required"}],
                }
            if not cron and not run_at:
                return {
                    "status": "error",
                    "content": [{"text": "Error: Either cron or run_at is required"}],
                }
            if not prompt:
                return {
                    "status": "error",
                    "content": [{"text": "Error: prompt is required"}],
                }

            # Validate cron expression if provided
            if cron:
                try:
                    _parse_cron(cron)
                except ValueError as e:
                    return {"status": "error", "content": [{"text": f"Error: {e}"}]}

            # Validate run_at format if provided
            if run_at:
                try:
                    # Basic validation
                    run_at_str = run_at.replace("Z", "+00:00")
                    if "+" not in run_at_str and "-" not in run_at_str[10:]:
                        datetime.fromisoformat(run_at_str)
                    else:
                        datetime.fromisoformat(run_at_str)
                except ValueError:
                    return {
                        "status": "error",
                        "content": [
                            {
                                "text": f"Error: Invalid run_at format. Use ISO 8601 (e.g., 2024-01-20T14:00:00Z)"
                            }
                        ],
                    }

            schedules = _get_schedules(repo, token)
            if "jobs" not in schedules:
                schedules["jobs"] = {}

            is_update = job_id in schedules["jobs"]

            schedules["jobs"][job_id] = {
                "prompt": prompt,
                "enabled": True,
            }

            # Set schedule type
            if cron:
                schedules["jobs"][job_id]["cron"] = cron
            if run_at:
                schedules["jobs"][job_id]["run_at"] = run_at
                if once:
                    schedules["jobs"][job_id]["once"] = True

            if system_prompt:
                schedules["jobs"][job_id]["system_prompt"] = system_prompt
            if tools:
                schedules["jobs"][job_id]["tools"] = tools
            if model:
                schedules["jobs"][job_id]["model"] = model
            if max_tokens:
                schedules["jobs"][job_id]["max_tokens"] = max_tokens
            if context:
                schedules["jobs"][job_id]["context"] = context

            result = _save_schedules(repo, schedules, token)
            if not result["success"]:
                return {
                    "status": "error",
                    "content": [{"text": f"Failed to save: {result['message']}"}],
                }

            action_word = "updated" if is_update else "added"
            schedule_info = f"**Cron:** `{cron}`" if cron else f"**Run At:** `{run_at}`"
            once_info = " (once, auto-remove)" if once else ""

            return {
                "status": "success",
                "content": [
                    {
                        "text": f"✅ Job `{job_id}` {action_word} successfully\n\n{schedule_info}{once_info}\n**Prompt:** {prompt[:100]}..."
                    }
                ],
            }

        # REMOVE - Delete a job
        elif action == "remove":
            if not job_id:
                return {
                    "status": "error",
                    "content": [{"text": "Error: job_id is required"}],
                }

            schedules = _get_schedules(repo, token)
            jobs = schedules.get("jobs", {})

            if job_id not in jobs:
                return {
                    "status": "error",
                    "content": [{"text": f"Job `{job_id}` not found"}],
                }

            del schedules["jobs"][job_id]
            result = _save_schedules(repo, schedules, token)

            if not result["success"]:
                return {
                    "status": "error",
                    "content": [{"text": f"Failed to save: {result['message']}"}],
                }

            return {
                "status": "success",
                "content": [{"text": f"✅ Job `{job_id}` removed successfully"}],
            }

        # ENABLE/DISABLE - Toggle job status
        elif action in ["enable", "disable"]:
            if not job_id:
                return {
                    "status": "error",
                    "content": [{"text": "Error: job_id is required"}],
                }

            schedules = _get_schedules(repo, token)
            jobs = schedules.get("jobs", {})

            if job_id not in jobs:
                return {
                    "status": "error",
                    "content": [{"text": f"Job `{job_id}` not found"}],
                }

            schedules["jobs"][job_id]["enabled"] = action == "enable"
            result = _save_schedules(repo, schedules, token)

            if not result["success"]:
                return {
                    "status": "error",
                    "content": [{"text": f"Failed to save: {result['message']}"}],
                }

            status = "enabled" if action == "enable" else "disabled"
            return {
                "status": "success",
                "content": [{"text": f"✅ Job `{job_id}` {status}"}],
            }

        # GET - Get job details
        elif action == "get":
            if not job_id:
                return {
                    "status": "error",
                    "content": [{"text": "Error: job_id is required"}],
                }

            schedules = _get_schedules(repo, token)
            jobs = schedules.get("jobs", {})

            if job_id not in jobs:
                return {
                    "status": "error",
                    "content": [{"text": f"Job `{job_id}` not found"}],
                }

            job = jobs[job_id]
            job_type = "🔄 Recurring" if job.get("cron") else "📅 One-time"
            lines = [f"## Job: `{job_id}` ({job_type})\n"]
            lines.append(f"**Enabled:** {'✅' if job.get('enabled', True) else '❌'}")

            if job.get("cron"):
                lines.append(f"**Cron:** `{job['cron']}`")
            if job.get("run_at"):
                once_marker = " (once, auto-remove)" if job.get("once") else ""
                lines.append(f"**Run At:** `{job['run_at']}`{once_marker}")

            lines.append(f"**Prompt:** {job.get('prompt', 'N/A')}")
            if job.get("system_prompt"):
                lines.append(f"**System Prompt:** {job['system_prompt']}")
            if job.get("tools"):
                lines.append(f"**Tools:** {job['tools']}")
            if job.get("model"):
                lines.append(f"**Model:** {job['model']}")
            if job.get("max_tokens"):
                lines.append(f"**Max Tokens:** {job['max_tokens']}")
            if job.get("context"):
                lines.append(f"**Context:** {job['context']}")

            return {
                "status": "success",
                "content": [{"text": "\n".join(lines)}],
                "job": job,
            }

        else:
            return {
                "status": "error",
                "content": [
                    {
                        "text": f"Unknown action: {action}. Valid: list, check, add, remove, enable, disable, get"
                    }
                ],
            }

    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}
