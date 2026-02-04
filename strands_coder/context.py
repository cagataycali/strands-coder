#!/usr/bin/env python3
"""
Context building for Strands Coder agent.

Handles:
- GitHub event context fetching (issues, PRs, discussions)
- GitHub Project context fetching
- Self-awareness (own code injection)
- System prompt assembly
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def get_own_source_code() -> str:
    """
    Read own source code for self-awareness.

    Returns formatted source code of key agent files for injection into system prompt.
    This enables the agent to understand its own implementation and capabilities.
    """
    source_parts = []

    # Get the strands_coder package directory
    package_dir = Path(__file__).parent

    # Key files for self-awareness
    key_files = [
        ("agent_runner.py", "Main agent runner - execution entry point"),
        ("context.py", "Context building - system prompt assembly"),
    ]

    for filename, description in key_files:
        file_path = package_dir / filename
        try:
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                source_parts.append(f"""### {filename}
*{description}*

```python
{content}
```
""")
        except Exception as e:
            source_parts.append(f"### {filename}\nError reading: {e}\n")

    if source_parts:
        return f"""
---
## 🧠 SELF-AWARENESS: Your Own Implementation

**Package Path:** `{package_dir}`
**Last Updated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

You have full access to your own source code. Use this for:
- Understanding your capabilities and limitations
- Debugging your own behavior
- Proposing improvements to yourself

{"".join(source_parts)}
---
"""
    return ""


def fetch_github_event_context() -> str:
    """
    Fetch rich GitHub event context based on the triggering event.

    Extracts and enriches context from GITHUB_CONTEXT env var:
    - Issue events → Full issue thread with comments
    - PR events → Reviews, comments, linked issues
    - Comment events → Full conversation thread
    - Discussion events → Thread and replies

    Returns formatted markdown with complete context.
    """
    import requests

    github_context_json = os.environ.get("GITHUB_CONTEXT", "{}")
    if not github_context_json or github_context_json == "{}":
        return ""

    try:
        github_context = json.loads(github_context_json)
    except json.JSONDecodeError:
        print("⚠ Failed to parse GITHUB_CONTEXT")
        return ""

    token = os.environ.get("PAT_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
    if not token:
        print("⚠ No GitHub token available for context fetch")
        return ""

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
    }

    event_name = github_context.get("event_name", "")
    event = github_context.get("event", {})
    repo_name = github_context.get("repository", "")

    context_parts = []

    # Add raw GITHUB_CONTEXT at the beginning
    context_parts.append(f"""
## 📋 RAW GITHUB_CONTEXT

**Event Type:** `{event_name}`
**Repository:** `{repo_name}`
**Action:** `{event.get('action', 'N/A')}`
**Actor:** `{github_context.get('actor', 'N/A')}`
**Workflow:** `{github_context.get('workflow', 'N/A')}`
**Run ID:** `{github_context.get('run_id', 'N/A')}`

<details>
<summary>Full GitHub Context (Click to expand)</summary>

```json
{json.dumps(github_context, indent=2)}
```

</details>
""")

    try:
        # Issue events (opened, edited, commented, etc.)
        if event_name in ["issues", "issue_comment"]:
            issue = event.get("issue", {})
            if not issue:
                return ""

            issue_number = issue.get("number")
            issue_title = issue.get("title", "")
            issue_body = issue.get("body", "")
            issue_state = issue.get("state", "")
            issue_author = issue.get("user", {}).get("login", "")
            issue_created = issue.get("created_at", "")
            issue_url = issue.get("html_url", "")

            context_parts.append(f"""
## 🎫 ISSUE CONTEXT

**Issue:** #{issue_number}: {issue_title}
**State:** {issue_state}
**Author:** @{issue_author}
**Created:** {issue_created}
**URL:** {issue_url}

### Original Issue Body
```markdown
{issue_body or '(empty)'}
```
""")

            # Fetch all comments on the issue
            query = """
            query($owner: String!, $name: String!, $number: Int!) {
              repository(owner: $owner, name: $name) {
                issue(number: $number) {
                  comments(first: 100) {
                    totalCount
                    nodes {
                      id
                      author { login }
                      body
                      createdAt
                      updatedAt
                      url
                    }
                  }
                  timelineItems(first: 50, itemTypes: [CROSS_REFERENCED_EVENT, REFERENCED_EVENT]) {
                    nodes {
                      ... on CrossReferencedEvent {
                        source {
                          ... on PullRequest {
                            number
                            title
                            state
                            url
                          }
                          ... on Issue {
                            number
                            title
                            state
                            url
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            """

            owner, name = repo_name.split("/")
            response = requests.post(
                "https://api.github.com/graphql",
                headers=headers,
                json={
                    "query": query,
                    "variables": {"owner": owner, "name": name, "number": issue_number},
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                print(f"⚠ GraphQL errors: {data['errors']}")
            else:
                issue_data = data.get("data", {}).get("repository", {}).get("issue", {})

                # Comments
                comments = issue_data.get("comments", {}).get("nodes", [])
                total_comments = issue_data.get("comments", {}).get("totalCount", 0)

                if comments:
                    context_parts.append(
                        f"\n### 💬 Comments ({total_comments} total)\n"
                    )
                    for idx, comment in enumerate(comments, 1):
                        author = comment.get("author", {}).get("login", "unknown")
                        body = comment.get("body", "")
                        created = comment.get("createdAt", "")
                        context_parts.append(f"""
**Comment #{idx}** by @{author} at {created}:
```markdown
{body}
```
""")

                # Linked PRs/Issues
                timeline = issue_data.get("timelineItems", {}).get("nodes", [])
                linked_items = []
                for item in timeline:
                    source = item.get("source", {})
                    if source:
                        num = source.get("number")
                        title = source.get("title")
                        state = source.get("state")
                        url = source.get("url")
                        if num and title:
                            linked_items.append(
                                f"  - #{num}: {title} ({state}) - {url}"
                            )

                if linked_items:
                    context_parts.append(
                        f"\n### 🔗 Linked Items\n" + "\n".join(linked_items)
                    )

        # Pull Request events
        elif event_name in [
            "pull_request",
            "pull_request_review",
            "pull_request_review_comment",
        ]:
            pr = event.get("pull_request", {})
            if not pr:
                return ""

            pr_number = pr.get("number")
            pr_title = pr.get("title", "")
            pr_body = pr.get("body", "")
            pr_state = pr.get("state", "")
            pr_author = pr.get("user", {}).get("login", "")
            pr_created = pr.get("created_at", "")
            pr_url = pr.get("html_url", "")
            pr_base = pr.get("base", {}).get("ref", "")
            pr_head = pr.get("head", {}).get("ref", "")

            context_parts.append(f"""
## 🔀 PULL REQUEST CONTEXT

**PR:** #{pr_number}: {pr_title}
**State:** {pr_state}
**Author:** @{pr_author}
**Created:** {pr_created}
**Branches:** {pr_head} → {pr_base}
**URL:** {pr_url}

### Original PR Body
```markdown
{pr_body or '(empty)'}
```
""")

            # Fetch reviews, comments, and linked issues
            query = """
            query($owner: String!, $name: String!, $number: Int!) {
              repository(owner: $owner, name: $name) {
                pullRequest(number: $number) {
                  reviews(first: 50) {
                    totalCount
                    nodes {
                      id
                      author { login }
                      state
                      body
                      createdAt
                      url
                    }
                  }
                  comments(first: 100) {
                    totalCount
                    nodes {
                      id
                      author { login }
                      body
                      createdAt
                      url
                    }
                  }
                  reviewThreads(first: 50) {
                    totalCount
                    nodes {
                      isResolved
                      comments(first: 10) {
                        nodes {
                          author { login }
                          body
                          createdAt
                          path
                          line
                        }
                      }
                    }
                  }
                  closingIssuesReferences(first: 10) {
                    totalCount
                    nodes {
                      number
                      title
                      state
                      url
                    }
                  }
                }
              }
            }
            """

            owner, name = repo_name.split("/")
            response = requests.post(
                "https://api.github.com/graphql",
                headers=headers,
                json={
                    "query": query,
                    "variables": {"owner": owner, "name": name, "number": pr_number},
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                print(f"⚠ GraphQL errors: {data['errors']}")
            else:
                pr_data = (
                    data.get("data", {}).get("repository", {}).get("pullRequest", {})
                )

                # Reviews
                reviews = pr_data.get("reviews", {}).get("nodes", [])
                total_reviews = pr_data.get("reviews", {}).get("totalCount", 0)

                if reviews:
                    context_parts.append(f"\n### ✅ Reviews ({total_reviews} total)\n")
                    for idx, review in enumerate(reviews, 1):
                        author = review.get("author", {}).get("login", "unknown")
                        state = review.get("state", "")
                        body = review.get("body", "")
                        created = review.get("createdAt", "")
                        context_parts.append(f"""
**Review #{idx}** by @{author} - {state} at {created}:
```markdown
{body or '(no comment)'}
```
""")

                # Comments
                comments = pr_data.get("comments", {}).get("nodes", [])
                total_comments = pr_data.get("comments", {}).get("totalCount", 0)

                if comments:
                    context_parts.append(
                        f"\n### 💬 Comments ({total_comments} total)\n"
                    )
                    for idx, comment in enumerate(comments, 1):
                        author = comment.get("author", {}).get("login", "unknown")
                        body = comment.get("body", "")
                        created = comment.get("createdAt", "")
                        context_parts.append(f"""
**Comment #{idx}** by @{author} at {created}:
```markdown
{body}
```
""")

                # Review Threads (code comments)
                threads = pr_data.get("reviewThreads", {}).get("nodes", [])
                total_threads = pr_data.get("reviewThreads", {}).get("totalCount", 0)

                if threads:
                    context_parts.append(
                        f"\n### 🧵 Code Review Threads ({total_threads} total)\n"
                    )
                    for idx, thread in enumerate(threads, 1):
                        is_resolved = thread.get("isResolved", False)
                        thread_comments = thread.get("comments", {}).get("nodes", [])

                        if thread_comments:
                            first_comment = thread_comments[0]
                            author = first_comment.get("author", {}).get(
                                "login", "unknown"
                            )
                            body = first_comment.get("body", "")
                            path = first_comment.get("path", "")
                            line = first_comment.get("line")

                            status = "✅ Resolved" if is_resolved else "🔴 Unresolved"
                            context_parts.append(f"""
**Thread #{idx}** [{status}] by @{author} on `{path}:{line}`:
```markdown
{body}
```
""")

                            # Follow-up comments in thread
                            if len(thread_comments) > 1:
                                for reply in thread_comments[1:]:
                                    reply_author = reply.get("author", {}).get(
                                        "login", "unknown"
                                    )
                                    reply_body = reply.get("body", "")
                                    context_parts.append(
                                        f"  ↳ @{reply_author}: {reply_body}\n"
                                    )

                # Linked issues (Fixes #N)
                closing_issues = pr_data.get("closingIssuesReferences", {}).get(
                    "nodes", []
                )
                if closing_issues:
                    context_parts.append(f"\n### 🎫 Linked Issues\n")
                    for issue in closing_issues:
                        num = issue.get("number")
                        title = issue.get("title")
                        state = issue.get("state")
                        url = issue.get("url")
                        context_parts.append(
                            f"  - Fixes #{num}: {title} ({state}) - {url}\n"
                        )

        # Discussion events
        elif event_name in ["discussion", "discussion_comment"]:
            discussion = event.get("discussion", {})
            if not discussion:
                return ""

            disc_number = discussion.get("number")
            disc_title = discussion.get("title", "")
            disc_body = discussion.get("body", "")
            disc_author = discussion.get("user", {}).get("login", "")
            disc_created = discussion.get("created_at", "")
            disc_url = discussion.get("html_url", "")

            context_parts.append(f"""
## 💭 DISCUSSION CONTEXT

**Discussion:** #{disc_number}: {disc_title}
**Author:** @{disc_author}
**Created:** {disc_created}
**URL:** {disc_url}

### Original Post
```markdown
{disc_body or '(empty)'}
```
""")

            # Fetch discussion comments via GraphQL
            query = """
            query($owner: String!, $name: String!, $number: Int!) {
              repository(owner: $owner, name: $name) {
                discussion(number: $number) {
                  comments(first: 100) {
                    totalCount
                    nodes {
                      id
                      author { login }
                      body
                      createdAt
                      url
                    }
                  }
                }
              }
            }
            """

            owner, name = repo_name.split("/")
            response = requests.post(
                "https://api.github.com/graphql",
                headers=headers,
                json={
                    "query": query,
                    "variables": {"owner": owner, "name": name, "number": disc_number},
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                print(f"⚠ GraphQL errors: {data['errors']}")
            else:
                disc_data = (
                    data.get("data", {}).get("repository", {}).get("discussion", {})
                )
                comments = disc_data.get("comments", {}).get("nodes", [])
                total_comments = disc_data.get("comments", {}).get("totalCount", 0)

                if comments:
                    context_parts.append(f"\n### 💬 Replies ({total_comments} total)\n")
                    for idx, comment in enumerate(comments, 1):
                        author = comment.get("author", {}).get("login", "unknown")
                        body = comment.get("body", "")
                        created = comment.get("createdAt", "")
                        context_parts.append(f"""
**Reply #{idx}** by @{author} at {created}:
```markdown
{body}
```
""")

        if context_parts:
            full_context = "\n".join(context_parts)
            print(f"✓ GitHub event context loaded ({event_name})")
            return f"\n---\n{full_context}\n---\n"
        else:
            return ""

    except Exception as e:
        print(f"⚠ GitHub event context fetch failed: {e}")
        import traceback

        traceback.print_exc()
        return ""


def fetch_project_context(project_id: str) -> str:
    """
    Fetch GitHub Project context for pre-loading into agent.

    Uses direct GraphQL API call to avoid circular tool dependencies.
    Returns formatted markdown with project state.
    """
    import requests

    token = os.environ.get("PAT_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
    if not token or not project_id:
        return ""

    query = """
    query($projectId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          id
          title
          number
          url
          fields(first: 20) {
            nodes {
              ... on ProjectV2SingleSelectField {
                name
                options { id name }
              }
            }
          }
          items(first: 50) {
            totalCount
            nodes {
              id
              type
              isArchived
              content {
                ... on Issue {
                  number
                  title
                  state
                  repository { nameWithOwner }
                }
                ... on PullRequest {
                  number
                  title
                  state
                  repository { nameWithOwner }
                }
                ... on DraftIssue {
                  title
                }
              }
              fieldValues(first: 10) {
                nodes {
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field { ... on ProjectV2SingleSelectField { name } }
                  }
                }
              }
            }
          }
        }
      }
    }
    """

    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        }

        response = requests.post(
            "https://api.github.com/graphql",
            headers=headers,
            json={"query": query, "variables": {"projectId": project_id}},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            print(f"⚠ Project fetch errors: {data['errors']}")
            return ""

        project = data.get("data", {}).get("node", {})
        if not project:
            return ""

        # Build context
        items = project.get("items", {}).get("nodes", [])
        total = project.get("items", {}).get("totalCount", 0)

        # Count by status
        status_counts = {"Todo": 0, "In Progress": 0, "Done": 0}
        item_list = []

        for item in items:
            if item.get("isArchived"):
                continue

            content = item.get("content", {})
            item_type = item.get("type", "")

            # Get status
            status = "Todo"
            for fv in item.get("fieldValues", {}).get("nodes", []):
                if fv.get("field", {}).get("name") == "Status" and fv.get("name"):
                    status = fv["name"]
                    break

            status_counts[status] = status_counts.get(status, 0) + 1

            # Format item
            if item_type == "DRAFT_ISSUE":
                item_list.append(
                    f"  - 📝 Draft: {content.get('title')} [{status}] (ID: {item.get('id')})"
                )
            else:
                repo = content.get("repository", {}).get("nameWithOwner", "")
                num = content.get("number", "?")
                title = content.get("title", "")
                state = content.get("state", "")
                item_list.append(
                    f"  - #{num}: {title} [{status}] ({repo}, {state}) (ID: {item.get('id')})"
                )

        context = f"""
---
## 📊 PROJECT CONTEXT (Pre-loaded)

**Project:** {project.get('title')} (#{project.get('number')})
**ID:** `{project.get('id')}`
**URL:** {project.get('url')}

### Status Summary
- Todo: {status_counts.get('Todo', 0)}
- In Progress: {status_counts.get('In Progress', 0)}
- Done: {status_counts.get('Done', 0)}
- **Total:** {total}

### Current Items ({len(item_list)} shown)
{chr(10).join(item_list) if item_list else '  No items yet'}

**Note:** Use `projects(action="update_item", item_id="PVTI_...", field_name="Status", field_value="In Progress")` to update status.
---
"""
        print(f"✓ Project context loaded: {project.get('title')} ({total} items)")
        return context

    except Exception as e:
        print(f"⚠ Project context fetch failed: {e}")
        return ""


def extract_user_message() -> str:
    """
    Extract the actual user message from GITHUB_CONTEXT for use in the prompt.

    This extracts the most recent user action that triggered the workflow:
    - Issue/PR opened → body
    - Comment created → comment body
    - Discussion post → discussion body
    - PR review → review body

    Returns the user's message for semantic matching (e.g., for retrieve tool).
    """
    github_context_json = os.environ.get("GITHUB_CONTEXT", "{}")
    if not github_context_json or github_context_json == "{}":
        return ""

    try:
        github_context = json.loads(github_context_json)
    except json.JSONDecodeError:
        return ""

    event_name = github_context.get("event_name", "")
    event = github_context.get("event", {})
    action = event.get("action", "")

    # Issue comment created
    if event_name == "issue_comment" and action in ["created", "edited"]:
        comment = event.get("comment", {})
        return comment.get("body", "")

    # Issue opened/edited
    elif event_name == "issues" and action in ["opened", "edited", "reopened"]:
        issue = event.get("issue", {})
        return issue.get("body", "")

    # PR opened/edited
    elif event_name == "pull_request" and action in ["opened", "edited", "reopened"]:
        pr = event.get("pull_request", {})
        return pr.get("body", "")

    # PR review submitted
    elif event_name == "pull_request_review" and action == "submitted":
        review = event.get("review", {})
        return review.get("body", "")

    # PR review comment
    elif event_name == "pull_request_review_comment" and action in [
        "created",
        "edited",
    ]:
        comment = event.get("comment", {})
        return comment.get("body", "")

    # Discussion created/edited
    elif event_name == "discussion" and action in ["created", "edited"]:
        discussion = event.get("discussion", {})
        return discussion.get("body", "")

    # Discussion comment
    elif event_name == "discussion_comment" and action in ["created", "edited"]:
        comment = event.get("comment", {})
        return comment.get("body", "")

    # Default: return empty (workflow_dispatch, labels, etc.)
    return ""


def build_system_prompt() -> str:
    """Build comprehensive system prompt from environment variables and context."""
    # Base system prompt
    base_prompt = os.getenv("SYSTEM_PROMPT", "")
    if not base_prompt:
        base_prompt = (
            "You are an autonomous GitHub agent powered by Strands Agents SDK."
        )

    # Add input system prompt if provided
    input_system_prompt = os.getenv("INPUT_SYSTEM_PROMPT", "")
    if input_system_prompt:
        base_prompt = f"{base_prompt}\n\n{input_system_prompt}"

    # Add rich GitHub event context (issue threads, PR reviews, etc.)
    github_event_context = fetch_github_event_context()
    if github_event_context:
        base_prompt = f"{base_prompt}\n\n{github_event_context}"

    # Add Project context if configured
    project_id = os.getenv("STRANDS_CODER_PROJECT_ID")
    if project_id:
        project_context = fetch_project_context(project_id)
        if project_context:
            base_prompt = f"{base_prompt}\n\n{project_context}"

    # Add self-awareness (own code) if enabled
    if os.getenv("STRANDS_SELF_AWARE", "true").lower() == "true":
        own_code = get_own_source_code()
        if own_code:
            base_prompt = f"{base_prompt}\n\n{own_code}"
            print("✓ Self-awareness enabled (own code injected)")

    return base_prompt
