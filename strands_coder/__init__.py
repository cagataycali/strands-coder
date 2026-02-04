"""Strands GitHub Action - Transform your GitHub repository with intelligent AI automation in just one line of YAML.

This package provides the core functionality for the Strands GitHub Action,
enabling intelligent repository automation through AI agents.
"""

__version__ = "0.1.0"

from .agent_runner import run_agent
from .tools.create_subagent import create_subagent
from .tools.projects import projects
from .tools.scheduler import scheduler
from .tools.github_tools import (
    add_issue_comment,
    create_issue,
    create_pull_request,
    get_issue,
    get_issue_comments,
    get_pr_review_and_comments,
    get_pull_request,
    list_issues,
    list_pull_requests,
    reply_to_review_comment,
    update_issue,
    update_pull_request,
)
from .tools.store_in_kb import store_in_kb
from .tools.system_prompt import system_prompt
from .tools.use_github import use_github

__all__ = [
    "run_agent",
    "__version__",
    # Tools
    "projects",
    "create_subagent",
    "scheduler",
    "store_in_kb",
    "system_prompt",
    "use_github",
    "list_pull_requests",
    "list_issues",
    "add_issue_comment",
    "create_issue",
    "get_issue",
    "create_pull_request",
    "get_pull_request",
    "update_pull_request",
    "get_pr_review_and_comments",
    "reply_to_review_comment",
    "update_issue",
    "get_issue_comments",
]
