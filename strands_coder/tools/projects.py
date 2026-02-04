"""GitHub Projects (v2) management tool for Strands Agents.

A comprehensive, production-ready GitHub Projects integration for autonomous coding agents.
Designed for systematic work tracking, progress monitoring, and workflow automation across
multiple repositories.

Features:
- Full CRUD for projects, items, fields, and views
- Bulk operations for efficient batch processing
- Draft issues for quick task creation
- Status updates and progress tracking
- Workflow automation control
- Repository and team linking
- Archive/unarchive support
- Item positioning and prioritization

Environment Variables:
- PAT_TOKEN or GITHUB_TOKEN: Required for GitHub API authentication
- STRANDS_CODER_PROJECT_ID: Default project ID for operations
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import requests
from strands import tool

# GitHub GraphQL API endpoint
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"


def _get_github_token() -> str | None:
    """Get GitHub token from environment variables."""
    return os.environ.get("PAT_TOKEN", os.environ.get("GITHUB_TOKEN", ""))


def _execute_graphql(
    query: str, variables: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Execute a GraphQL query against GitHub's API.

    Args:
        query: GraphQL query string
        variables: Optional variables for the query

    Returns:
        Dictionary containing the GraphQL response

    Raises:
        Exception: If the request fails or authentication is invalid
    """
    token = _get_github_token()
    if not token:
        raise ValueError(
            "GitHub token is required. Set PAT_TOKEN or GITHUB_TOKEN environment variable."
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
        "GraphQL-Features": "projects_next_graphql",
    }

    payload = {"query": query, "variables": variables or {}}

    response = requests.post(
        GITHUB_GRAPHQL_URL, headers=headers, json=payload, timeout=30
    )
    response.raise_for_status()

    data = response.json()

    if "errors" in data:
        error_messages = [err.get("message", "Unknown error") for err in data["errors"]]
        raise Exception(f"GraphQL errors: {', '.join(error_messages)}")

    return data


def _get_owner_id(owner: str) -> str:
    """Get the node ID for a user or organization."""
    # Try user first
    user_query = """
    query($login: String!) {
      user(login: $login) { id }
    }
    """
    try:
        result = _execute_graphql(user_query, {"login": owner})
        if result.get("data", {}).get("user"):
            return result["data"]["user"]["id"]
    except Exception:
        pass

    # Try organization
    org_query = """
    query($login: String!) {
      organization(login: $login) { id }
    }
    """
    try:
        result = _execute_graphql(org_query, {"login": owner})
        if result.get("data", {}).get("organization"):
            return result["data"]["organization"]["id"]
    except Exception:
        pass

    raise ValueError(f"Owner '{owner}' not found as user or organization")


def _get_repository_id(owner: str, name: str) -> str:
    """Get the node ID for a repository."""
    query = """
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) { id }
    }
    """
    result = _execute_graphql(query, {"owner": owner, "name": name})
    repo = result.get("data", {}).get("repository")
    if not repo:
        raise ValueError(f"Repository '{owner}/{name}' not found")
    return repo["id"]


def _get_issue_node_id(owner: str, repo: str, issue_number: int) -> str | None:
    """Get the node ID for an issue."""
    query = """
    query($owner: String!, $repo: String!, $number: Int!) {
      repository(owner: $owner, name: $repo) {
        issue(number: $number) { id }
      }
    }
    """
    result = _execute_graphql(
        query, {"owner": owner, "repo": repo, "number": issue_number}
    )
    issue = result.get("data", {}).get("repository", {}).get("issue")
    return issue.get("id") if issue else None


def _get_pr_node_id(owner: str, repo: str, pr_number: int) -> str | None:
    """Get the node ID for a pull request."""
    query = """
    query($owner: String!, $repo: String!, $number: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) { id }
      }
    }
    """
    result = _execute_graphql(
        query, {"owner": owner, "repo": repo, "number": pr_number}
    )
    pr = result.get("data", {}).get("repository", {}).get("pullRequest")
    return pr.get("id") if pr else None


def _parse_repository(repository: str) -> tuple[str, str]:
    """Parse 'owner/repo' format into (owner, repo) tuple."""
    parts = repository.split("/")
    if len(parts) != 2:
        raise ValueError(
            f"Repository must be in format 'owner/repo', got: {repository}"
        )
    return parts[0], parts[1]


# ============================================================================
# PROJECT OPERATIONS
# ============================================================================


def _list_projects(owner: str, limit: int = 20) -> list[dict[str, Any]]:
    """List projects for a user or organization."""
    # Try user
    user_query = """
    query($login: String!, $limit: Int!) {
      user(login: $login) {
        projectsV2(first: $limit, orderBy: {field: UPDATED_AT, direction: DESC}) {
          totalCount
          nodes {
            id
            number
            title
            shortDescription
            url
            closed
            public
            updatedAt
            items { totalCount }
          }
        }
      }
    }
    """
    try:
        result = _execute_graphql(user_query, {"login": owner, "limit": limit})
        data = result.get("data", {})
        if data.get("user") and data["user"].get("projectsV2"):
            return data["user"]["projectsV2"].get("nodes", [])
    except Exception:
        pass

    # Try organization
    org_query = """
    query($login: String!, $limit: Int!) {
      organization(login: $login) {
        projectsV2(first: $limit, orderBy: {field: UPDATED_AT, direction: DESC}) {
          totalCount
          nodes {
            id
            number
            title
            shortDescription
            url
            closed
            public
            updatedAt
            items { totalCount }
          }
        }
      }
    }
    """
    try:
        result = _execute_graphql(org_query, {"login": owner, "limit": limit})
        data = result.get("data", {})
        if data.get("organization") and data["organization"].get("projectsV2"):
            return data["organization"]["projectsV2"].get("nodes", [])
    except Exception:
        pass

    return []


def _get_project(project_id: str, items_limit: int = 100) -> dict[str, Any]:
    """Get comprehensive project details."""
    query = """
    query($projectId: ID!, $itemsLimit: Int!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          id
          number
          title
          shortDescription
          readme
          url
          public
          closed
          template
          createdAt
          updatedAt
          creator { login }
          owner {
            ... on User { login }
            ... on Organization { login }
          }
          repositories(first: 20) {
            nodes { nameWithOwner }
          }
          teams(first: 10) {
            nodes { name slug }
          }
          views(first: 20) {
            nodes {
              id
              name
              number
              layout
              filter
            }
          }
          workflows(first: 20) {
            nodes {
              id
              name
              number
              enabled
            }
          }
          fields(first: 30) {
            nodes {
              ... on ProjectV2Field {
                id
                name
                dataType
              }
              ... on ProjectV2SingleSelectField {
                id
                name
                dataType
                options {
                  id
                  name
                  color
                  description
                }
              }
              ... on ProjectV2IterationField {
                id
                name
                dataType
                configuration {
                  duration
                  startDay
                  iterations {
                    id
                    title
                    startDate
                    duration
                  }
                }
              }
            }
          }
          items(first: $itemsLimit) {
            totalCount
            nodes {
              id
              type
              isArchived
              createdAt
              updatedAt
              content {
                ... on Issue {
                  id
                  number
                  title
                  state
                  url
                  repository { nameWithOwner }
                  labels(first: 10) { nodes { name color } }
                  assignees(first: 5) { nodes { login } }
                }
                ... on PullRequest {
                  id
                  number
                  title
                  state
                  url
                  repository { nameWithOwner }
                  labels(first: 10) { nodes { name color } }
                  assignees(first: 5) { nodes { login } }
                }
                ... on DraftIssue {
                  id
                  title
                  body
                }
              }
              fieldValues(first: 20) {
                nodes {
                  ... on ProjectV2ItemFieldTextValue {
                    text
                    field { ... on ProjectV2Field { name } }
                  }
                  ... on ProjectV2ItemFieldNumberValue {
                    number
                    field { ... on ProjectV2Field { name } }
                  }
                  ... on ProjectV2ItemFieldDateValue {
                    date
                    field { ... on ProjectV2Field { name } }
                  }
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    optionId
                    field { ... on ProjectV2SingleSelectField { name } }
                  }
                  ... on ProjectV2ItemFieldIterationValue {
                    title
                    startDate
                    duration
                    field { ... on ProjectV2IterationField { name } }
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    result = _execute_graphql(
        query, {"projectId": project_id, "itemsLimit": items_limit}
    )
    return result.get("data", {}).get("node", {})


def _create_project(owner: str, title: str, description: str = "") -> dict[str, Any]:
    """Create a new project."""
    owner_id = _get_owner_id(owner)

    mutation = """
    mutation($ownerId: ID!, $title: String!) {
      createProjectV2(input: {ownerId: $ownerId, title: $title}) {
        projectV2 {
          id
          number
          title
          url
        }
      }
    }
    """
    result = _execute_graphql(mutation, {"ownerId": owner_id, "title": title})
    project = result.get("data", {}).get("createProjectV2", {}).get("projectV2", {})

    # Update description if provided
    if description and project.get("id"):
        _update_project(project["id"], short_description=description)

    return project


def _update_project(
    project_id: str,
    title: str | None = None,
    short_description: str | None = None,
    readme: str | None = None,
    public: bool | None = None,
    closed: bool | None = None,
) -> dict[str, Any]:
    """Update project settings."""
    mutation = """
    mutation($projectId: ID!, $title: String, $shortDescription: String, $readme: String, $public: Boolean, $closed: Boolean) {
      updateProjectV2(input: {
        projectId: $projectId,
        title: $title,
        shortDescription: $shortDescription,
        readme: $readme,
        public: $public,
        closed: $closed
      }) {
        projectV2 {
          id
          title
          shortDescription
          readme
          public
          closed
        }
      }
    }
    """
    variables = {"projectId": project_id}
    if title is not None:
        variables["title"] = title
    if short_description is not None:
        variables["shortDescription"] = short_description
    if readme is not None:
        variables["readme"] = readme
    if public is not None:
        variables["public"] = public
    if closed is not None:
        variables["closed"] = closed

    result = _execute_graphql(mutation, variables)
    return result.get("data", {}).get("updateProjectV2", {}).get("projectV2", {})


def _delete_project(project_id: str) -> bool:
    """Delete a project."""
    mutation = """
    mutation($projectId: ID!) {
      deleteProjectV2(input: {projectId: $projectId}) {
        projectV2 { id }
      }
    }
    """
    _execute_graphql(mutation, {"projectId": project_id})
    return True


def _copy_project(
    project_id: str, owner: str, title: str, include_draft_issues: bool = True
) -> dict[str, Any]:
    """Copy/duplicate a project."""
    owner_id = _get_owner_id(owner)

    mutation = """
    mutation($projectId: ID!, $ownerId: ID!, $title: String!, $includeDraftIssues: Boolean!) {
      copyProjectV2(input: {
        projectId: $projectId,
        ownerId: $ownerId,
        title: $title,
        includeDraftIssues: $includeDraftIssues
      }) {
        projectV2 {
          id
          number
          title
          url
        }
      }
    }
    """
    result = _execute_graphql(
        mutation,
        {
            "projectId": project_id,
            "ownerId": owner_id,
            "title": title,
            "includeDraftIssues": include_draft_issues,
        },
    )
    return result.get("data", {}).get("copyProjectV2", {}).get("projectV2", {})


# ============================================================================
# ITEM OPERATIONS
# ============================================================================


def _add_item(project_id: str, content_id: str) -> dict[str, Any]:
    """Add an issue or PR to a project by node ID."""
    mutation = """
    mutation($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
        item {
          id
          type
          content {
            ... on Issue { id number title url }
            ... on PullRequest { id number title url }
          }
        }
      }
    }
    """
    result = _execute_graphql(
        mutation, {"projectId": project_id, "contentId": content_id}
    )
    return result.get("data", {}).get("addProjectV2ItemById", {}).get("item", {})


def _add_draft_issue(
    project_id: str, title: str, body: str = "", assignee_ids: list[str] | None = None
) -> dict[str, Any]:
    """Add a draft issue to a project."""
    mutation = """
    mutation($projectId: ID!, $title: String!, $body: String, $assigneeIds: [ID!]) {
      addProjectV2DraftIssue(input: {
        projectId: $projectId,
        title: $title,
        body: $body,
        assigneeIds: $assigneeIds
      }) {
        projectItem {
          id
          type
          content {
            ... on DraftIssue { id title body }
          }
        }
      }
    }
    """
    result = _execute_graphql(
        mutation,
        {
            "projectId": project_id,
            "title": title,
            "body": body,
            "assigneeIds": assignee_ids or [],
        },
    )
    return (
        result.get("data", {}).get("addProjectV2DraftIssue", {}).get("projectItem", {})
    )


def _convert_draft_to_issue(
    project_id: str, item_id: str, repository_id: str
) -> dict[str, Any]:
    """Convert a draft issue to a real issue."""
    mutation = """
    mutation($projectId: ID!, $itemId: ID!, $repositoryId: ID!) {
      convertProjectV2DraftIssueItemToIssue(input: {
        projectId: $projectId,
        itemId: $itemId,
        repositoryId: $repositoryId
      }) {
        item {
          id
          content {
            ... on Issue { id number title url }
          }
        }
      }
    }
    """
    result = _execute_graphql(
        mutation,
        {"projectId": project_id, "itemId": item_id, "repositoryId": repository_id},
    )
    return (
        result.get("data", {})
        .get("convertProjectV2DraftIssueItemToIssue", {})
        .get("item", {})
    )


def _delete_item(project_id: str, item_id: str) -> str:
    """Delete an item from a project."""
    mutation = """
    mutation($projectId: ID!, $itemId: ID!) {
      deleteProjectV2Item(input: {projectId: $projectId, itemId: $itemId}) {
        deletedItemId
      }
    }
    """
    result = _execute_graphql(mutation, {"projectId": project_id, "itemId": item_id})
    return (
        result.get("data", {}).get("deleteProjectV2Item", {}).get("deletedItemId", "")
    )


def _archive_item(project_id: str, item_id: str) -> dict[str, Any]:
    """Archive a project item."""
    mutation = """
    mutation($projectId: ID!, $itemId: ID!) {
      archiveProjectV2Item(input: {projectId: $projectId, itemId: $itemId}) {
        item { id isArchived }
      }
    }
    """
    result = _execute_graphql(mutation, {"projectId": project_id, "itemId": item_id})
    return result.get("data", {}).get("archiveProjectV2Item", {}).get("item", {})


def _unarchive_item(project_id: str, item_id: str) -> dict[str, Any]:
    """Unarchive a project item."""
    mutation = """
    mutation($projectId: ID!, $itemId: ID!) {
      unarchiveProjectV2Item(input: {projectId: $projectId, itemId: $itemId}) {
        item { id isArchived }
      }
    }
    """
    result = _execute_graphql(mutation, {"projectId": project_id, "itemId": item_id})
    return result.get("data", {}).get("unarchiveProjectV2Item", {}).get("item", {})


def _update_item_position(
    project_id: str, item_id: str, after_id: str | None = None
) -> dict[str, Any]:
    """Update item position in the project (for prioritization)."""
    mutation = """
    mutation($projectId: ID!, $itemId: ID!, $afterId: ID) {
      updateProjectV2ItemPosition(input: {
        projectId: $projectId,
        itemId: $itemId,
        afterId: $afterId
      }) {
        items { nodes { id } }
      }
    }
    """
    result = _execute_graphql(
        mutation, {"projectId": project_id, "itemId": item_id, "afterId": after_id}
    )
    return result.get("data", {}).get("updateProjectV2ItemPosition", {})


# ============================================================================
# FIELD OPERATIONS
# ============================================================================


def _update_item_field(
    project_id: str, item_id: str, field_id: str, value: Any, value_type: str
) -> dict[str, Any]:
    """Update a field value for a project item.

    Args:
        project_id: Project node ID
        item_id: Item node ID
        field_id: Field node ID
        value: The value to set
        value_type: One of: text, number, date, singleSelectOptionId, iterationId
    """
    value_mapping = {
        "text": "text",
        "number": "number",
        "date": "date",
        "singleSelectOptionId": "singleSelectOptionId",
        "iterationId": "iterationId",
    }

    if value_type not in value_mapping:
        raise ValueError(
            f"Invalid value_type: {value_type}. Must be one of: {list(value_mapping.keys())}"
        )

    mutation = f"""
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: {value_type.capitalize() if value_type != 'singleSelectOptionId' else 'String'}!) {{
      updateProjectV2ItemFieldValue(input: {{
        projectId: $projectId,
        itemId: $itemId,
        fieldId: $fieldId,
        value: {{{value_mapping[value_type]}: $value}}
      }}) {{
        projectV2Item {{ id }}
      }}
    }}
    """

    result = _execute_graphql(
        mutation,
        {
            "projectId": project_id,
            "itemId": item_id,
            "fieldId": field_id,
            "value": value,
        },
    )
    return (
        result.get("data", {})
        .get("updateProjectV2ItemFieldValue", {})
        .get("projectV2Item", {})
    )


def _clear_item_field(project_id: str, item_id: str, field_id: str) -> dict[str, Any]:
    """Clear a field value for a project item."""
    mutation = """
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!) {
      clearProjectV2ItemFieldValue(input: {
        projectId: $projectId,
        itemId: $itemId,
        fieldId: $fieldId
      }) {
        projectV2Item { id }
      }
    }
    """
    result = _execute_graphql(
        mutation, {"projectId": project_id, "itemId": item_id, "fieldId": field_id}
    )
    return (
        result.get("data", {})
        .get("clearProjectV2ItemFieldValue", {})
        .get("projectV2Item", {})
    )


def _create_field(
    project_id: str,
    name: str,
    data_type: str,
    options: list[str] | None = None,
) -> dict[str, Any]:
    """Create a custom field in a project.

    Args:
        project_id: Project node ID
        name: Field name
        data_type: Field type (TEXT, NUMBER, DATE, SINGLE_SELECT)
        options: Options for SINGLE_SELECT fields
    """
    if data_type == "SINGLE_SELECT" and options:
        mutation = """
        mutation($projectId: ID!, $name: String!, $dataType: ProjectV2CustomFieldType!, $options: [ProjectV2SingleSelectFieldOptionInput!]!) {
          createProjectV2Field(input: {
            projectId: $projectId,
            dataType: $dataType,
            name: $name,
            singleSelectOptions: $options
          }) {
            projectV2Field {
              ... on ProjectV2SingleSelectField {
                id
                name
                options { id name color }
              }
            }
          }
        }
        """
        option_inputs = [{"name": opt, "color": "GRAY"} for opt in options]
        result = _execute_graphql(
            mutation,
            {
                "projectId": project_id,
                "name": name,
                "dataType": data_type,
                "options": option_inputs,
            },
        )
    else:
        mutation = """
        mutation($projectId: ID!, $name: String!, $dataType: ProjectV2CustomFieldType!) {
          createProjectV2Field(input: {
            projectId: $projectId,
            dataType: $dataType,
            name: $name
          }) {
            projectV2Field {
              ... on ProjectV2Field { id name dataType }
            }
          }
        }
        """
        result = _execute_graphql(
            mutation, {"projectId": project_id, "name": name, "dataType": data_type}
        )

    return (
        result.get("data", {}).get("createProjectV2Field", {}).get("projectV2Field", {})
    )


def _delete_field(project_id: str, field_id: str) -> bool:
    """Delete a custom field from a project."""
    mutation = """
    mutation($fieldId: ID!) {
      deleteProjectV2Field(input: {fieldId: $fieldId}) {
        projectV2Field { id }
      }
    }
    """
    _execute_graphql(mutation, {"fieldId": field_id})
    return True


# ============================================================================
# STATUS UPDATE OPERATIONS
# ============================================================================


def _create_status_update(
    project_id: str,
    body: str,
    status: str = "ON_TRACK",
    start_date: str | None = None,
    target_date: str | None = None,
) -> dict[str, Any]:
    """Create a project status update.

    Args:
        project_id: Project node ID
        body: Status update message (markdown supported)
        status: One of: INACTIVE, ON_TRACK, AT_RISK, OFF_TRACK, COMPLETE
        start_date: Optional start date (YYYY-MM-DD)
        target_date: Optional target date (YYYY-MM-DD)
    """
    mutation = """
    mutation($projectId: ID!, $body: String!, $status: ProjectV2StatusUpdateStatus, $startDate: Date, $targetDate: Date) {
      createProjectV2StatusUpdate(input: {
        projectId: $projectId,
        body: $body,
        status: $status,
        startDate: $startDate,
        targetDate: $targetDate
      }) {
        statusUpdate {
          id
          body
          status
          createdAt
        }
      }
    }
    """
    result = _execute_graphql(
        mutation,
        {
            "projectId": project_id,
            "body": body,
            "status": status,
            "startDate": start_date,
            "targetDate": target_date,
        },
    )
    return (
        result.get("data", {})
        .get("createProjectV2StatusUpdate", {})
        .get("statusUpdate", {})
    )


# ============================================================================
# REPOSITORY/TEAM LINKING
# ============================================================================


def _link_repository(project_id: str, repository_id: str) -> bool:
    """Link a repository to a project."""
    mutation = """
    mutation($projectId: ID!, $repositoryId: ID!) {
      linkProjectV2ToRepository(input: {projectId: $projectId, repositoryId: $repositoryId}) {
        repository { nameWithOwner }
      }
    }
    """
    _execute_graphql(mutation, {"projectId": project_id, "repositoryId": repository_id})
    return True


def _unlink_repository(project_id: str, repository_id: str) -> bool:
    """Unlink a repository from a project."""
    mutation = """
    mutation($projectId: ID!, $repositoryId: ID!) {
      unlinkProjectV2FromRepository(input: {projectId: $projectId, repositoryId: $repositoryId}) {
        repository { nameWithOwner }
      }
    }
    """
    _execute_graphql(mutation, {"projectId": project_id, "repositoryId": repository_id})
    return True


# ============================================================================
# PROGRESS & ANALYTICS
# ============================================================================


def _get_progress(project_id: str) -> dict[str, Any]:
    """Get comprehensive project progress summary."""
    project = _get_project(project_id, items_limit=100)

    items = project.get("items", {}).get("nodes", [])
    total_count = project.get("items", {}).get("totalCount", 0)

    # Find Status field and options
    status_field = None
    for field in project.get("fields", {}).get("nodes", []):
        if field.get("name") == "Status":
            status_field = field
            break

    # Count by type and state
    issues_open = issues_closed = 0
    prs_open = prs_merged = prs_closed = 0
    drafts = 0
    archived = 0

    # Count by status
    status_counts: dict[str, int] = {}
    if status_field and "options" in status_field:
        for opt in status_field["options"]:
            status_counts[opt["name"]] = 0

    for item in items:
        if item.get("isArchived"):
            archived += 1
            continue

        content = item.get("content", {})
        item_type = item.get("type", "")

        if item_type == "ISSUE":
            state = content.get("state", "")
            if state == "OPEN":
                issues_open += 1
            else:
                issues_closed += 1
        elif item_type == "PULL_REQUEST":
            state = content.get("state", "")
            if state == "MERGED":
                prs_merged += 1
            elif state == "OPEN":
                prs_open += 1
            else:
                prs_closed += 1
        elif item_type == "DRAFT_ISSUE":
            drafts += 1

        # Count status
        for fv in item.get("fieldValues", {}).get("nodes", []):
            if fv.get("field", {}).get("name") == "Status" and fv.get("name"):
                status_counts[fv["name"]] = status_counts.get(fv["name"], 0) + 1

    return {
        "project": {
            "id": project.get("id"),
            "title": project.get("title"),
            "url": project.get("url"),
            "number": project.get("number"),
        },
        "summary": {
            "total_items": total_count,
            "active_items": total_count - archived,
            "archived_items": archived,
        },
        "issues": {
            "open": issues_open,
            "closed": issues_closed,
            "total": issues_open + issues_closed,
        },
        "pull_requests": {
            "open": prs_open,
            "merged": prs_merged,
            "closed": prs_closed,
            "total": prs_open + prs_merged + prs_closed,
        },
        "drafts": drafts,
        "by_status": status_counts,
        "workflows": [
            {"name": w.get("name"), "enabled": w.get("enabled")}
            for w in project.get("workflows", {}).get("nodes", [])
        ],
    }


# ============================================================================
# BULK OPERATIONS
# ============================================================================


def _bulk_add_items(
    project_id: str, content_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Add multiple items to a project."""
    results = {"success": [], "failed": []}
    for content_id in content_ids:
        try:
            item = _add_item(project_id, content_id)
            results["success"].append({"content_id": content_id, "item": item})
        except Exception as e:
            results["failed"].append({"content_id": content_id, "error": str(e)})
    return results


def _bulk_update_status(
    project_id: str, item_ids: list[str], status_field_id: str, status_option_id: str
) -> dict[str, list[str]]:
    """Update status for multiple items."""
    results = {"success": [], "failed": []}
    for item_id in item_ids:
        try:
            _update_item_field(
                project_id,
                item_id,
                status_field_id,
                status_option_id,
                "singleSelectOptionId",
            )
            results["success"].append(item_id)
        except Exception as e:
            results["failed"].append(f"{item_id}: {e}")
    return results


def _bulk_archive(project_id: str, item_ids: list[str]) -> dict[str, list[str]]:
    """Archive multiple items."""
    results = {"success": [], "failed": []}
    for item_id in item_ids:
        try:
            _archive_item(project_id, item_id)
            results["success"].append(item_id)
        except Exception as e:
            results["failed"].append(f"{item_id}: {e}")
    return results


# ============================================================================
# MAIN TOOL FUNCTION
# ============================================================================


@tool
def projects(
    action: str,
    project_id: str | None = None,
    owner: str | None = None,
    title: str | None = None,
    description: str | None = None,
    content_id: str | None = None,
    item_id: str | None = None,
    field_name: str | None = None,
    field_value: str | None = None,
    field_type: str | None = None,
    field_options: list[str] | None = None,
    repository: str | None = None,
    issue_number: int | None = None,
    pr_number: int | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Manage GitHub Projects (v2) for cross-repository issue and PR tracking.

    This tool provides comprehensive GitHub Projects integration for autonomous agents,
    enabling systematic work tracking, progress monitoring, and workflow automation.

    Actions:
        - "list_projects": List projects for a user or organization
        - "get_project": Get project details and items
        - "create_project": Create a new project
        - "add_item": Add issue or PR to project
        - "update_item": Update project item field value
        - "create_field": Create custom field in project
        - "get_progress": Get project progress summary
        - "add_issue": Add issue by repository and number (convenience method)
        - "add_pr": Add PR by repository and number (convenience method)

    Args:
        action: The action to perform (see Actions above)
        project_id: Project node ID (PVT_...) - defaults to STRANDS_CODER_PROJECT_ID env var
        owner: GitHub username or organization (required for list_projects, create_project)
        title: Project title (required for create_project)
        description: Project description (optional for create_project)
        content_id: Issue or PR node ID (required for add_item)
        item_id: Project item ID (PVTI_...) (required for update_item)
        field_name: Custom field name (required for update_item, create_field)
        field_value: New field value (required for update_item)
        field_type: Field type for create_field (TEXT, NUMBER, DATE, SINGLE_SELECT)
        field_options: List of options for SINGLE_SELECT fields
        repository: Repository in format "owner/repo" (for add_issue, add_pr)
        issue_number: Issue number (for add_issue)
        pr_number: PR number (for add_pr)
        limit: Maximum items to return (for list_projects, get_project)

    Returns:
        Dict containing status and operation results

    Examples:
        ```python
        # List all projects
        result = agent.tool.projects(
            action="list_projects",
            owner="cagataycali"
        )

        # Create project
        result = agent.tool.projects(
            action="create_project",
            owner="cagataycali",
            title="Strands-Coder Work Tracker",
            description="Autonomous agent work tracking"
        )

        # Add issue to project (by node ID)
        result = agent.tool.projects(
            action="add_item",
            project_id="PVT_...",
            content_id="I_..."
        )

        # Add issue to project (by repository and number)
        result = agent.tool.projects(
            action="add_issue",
            project_id="PVT_...",
            repository="strands-agents/sdk-python",
            issue_number=42
        )

        # Create custom field
        result = agent.tool.projects(
            action="create_field",
            project_id="PVT_...",
            field_name="Priority",
            field_type="SINGLE_SELECT",
            field_options=["High", "Medium", "Low"]
        )

        # Update item status
        result = agent.tool.projects(
            action="update_item",
            project_id="PVT_...",
            item_id="PVTI_...",
            field_name="Status",
            field_value="In Progress"
        )

        # Get progress summary
        result = agent.tool.projects(
            action="get_progress",
            project_id="PVT_..."
        )
        ```
    """
    try:
        # Use default project ID from environment if not provided
        if not project_id and action not in ["list_projects", "create_project"]:
            project_id = os.environ.get("STRANDS_CODER_PROJECT_ID")
            if not project_id:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": "Error: project_id is required. Set STRANDS_CODER_PROJECT_ID env var or provide project_id parameter."
                        }
                    ],
                }

        # ----------------------------------------------------------------
        # PROJECT OPERATIONS
        # ----------------------------------------------------------------

        if action == "list_projects":
            if not owner:
                return {
                    "status": "error",
                    "content": [{"text": "Error: owner parameter is required"}],
                }

            projects_list = _list_projects(owner, limit)

            if not projects_list:
                return {
                    "status": "success",
                    "content": [{"text": f"No projects found for {owner}"}],
                }

            lines = [f"Found {len(projects_list)} project(s) for {owner}:\n"]
            for proj in projects_list:
                lines.append(
                    f"• **{proj.get('title')}** (#{proj.get('number')})\n"
                    f"  ID: `{proj.get('id')}`\n"
                    f"  Items: {proj.get('items', {}).get('totalCount', 0)} | "
                    f"Public: {proj.get('public', False)} | Closed: {proj.get('closed', False)}\n"
                    f"  URL: {proj.get('url')}\n"
                )

            return {"status": "success", "content": [{"text": "\n".join(lines)}]}

        elif action == "get_project":
            project = _get_project(project_id, items_limit=limit)

            if not project:
                return {
                    "status": "error",
                    "content": [{"text": f"Project {project_id} not found"}],
                }

            # Format fields
            fields_info = []
            for field in project.get("fields", {}).get("nodes", []):
                field_str = f"  • {field.get('name')} ({field.get('dataType')})"
                if "options" in field:
                    opts = ", ".join([o.get("name") for o in field.get("options", [])])
                    field_str += f": [{opts}]"
                fields_info.append(field_str)

            # Format items
            items = project.get("items", {}).get("nodes", [])
            items_info = []
            for item in items[:20]:
                content = item.get("content", {})
                item_type = item.get("type", "")
                archived = "📦" if item.get("isArchived") else ""

                # Get status
                status = ""
                for fv in item.get("fieldValues", {}).get("nodes", []):
                    if fv.get("field", {}).get("name") == "Status":
                        status = f" [{fv.get('name')}]"
                        break

                if item_type == "DRAFT_ISSUE":
                    items_info.append(
                        f"  • {archived}📝 Draft: {content.get('title')}"
                        f"  (ID: {item.get('id')})"
                    )
                else:
                    repo = content.get("repository", {}).get("nameWithOwner", "")
                    items_info.append(
                        f"  • {archived}#{content.get('number')}: {content.get('title')}{status}\n"
                        f"    Repo: {repo} | State: {content.get('state')} | Item ID: `{item.get('id')}`"
                    )

            # Format workflows
            workflows_info = []
            for wf in project.get("workflows", {}).get("nodes", []):
                status_icon = "✅" if wf.get("enabled") else "❌"
                workflows_info.append(f"  • {status_icon} {wf.get('name')}")

            summary = f"""
## Project: {project.get('title')} (#{project.get('number')})

**ID:** `{project.get('id')}`
**URL:** {project.get('url')}
**Owner:** {project.get('owner', {}).get('login', 'N/A')}
**Public:** {project.get('public', False)} | **Closed:** {project.get('closed', False)}
**Description:** {project.get('shortDescription') or 'N/A'}

### Fields ({len(fields_info)}):
{chr(10).join(fields_info)}

### Workflows ({len(workflows_info)}):
{chr(10).join(workflows_info) if workflows_info else '  None configured'}

### Items ({project.get('items', {}).get('totalCount', 0)} total, showing {len(items_info)}):
{chr(10).join(items_info) if items_info else '  No items yet'}
"""

            return {"status": "success", "content": [{"text": summary}]}

        elif action == "create_project":
            if not owner or not title:
                return {
                    "status": "error",
                    "content": [
                        {"text": "Error: owner and title parameters are required"}
                    ],
                }

            project = _create_project(owner, title, description or "")

            summary = f"""
✅ **Project created successfully!**

• **Title:** {project.get('title')}
• **Number:** #{project.get('number')}
• **ID:** `{project.get('id')}`
• **URL:** {project.get('url')}

💡 To set as default, run:
```
export STRANDS_CODER_PROJECT_ID="{project.get('id')}"
```
"""

            return {"status": "success", "content": [{"text": summary}]}

        # ----------------------------------------------------------------
        # ITEM OPERATIONS
        # ----------------------------------------------------------------

        elif action == "add_item":
            if not content_id:
                return {
                    "status": "error",
                    "content": [{"text": "Error: content_id parameter is required"}],
                }

            item = _add_item(project_id, content_id)
            content = item.get("content", {})

            summary = f"""
✅ **Item added to project!**

• **Item ID:** `{item.get('id')}`
• **Type:** {item.get('type')}
• **Content:** #{content.get('number')}: {content.get('title')}
• **URL:** {content.get('url')}
"""

            return {"status": "success", "content": [{"text": summary}]}

        elif action == "add_issue":
            if not repository or issue_number is None:
                return {
                    "status": "error",
                    "content": [
                        {"text": "Error: repository and issue_number are required"}
                    ],
                }

            repo_owner, repo_name = _parse_repository(repository)
            issue_id = _get_issue_node_id(repo_owner, repo_name, issue_number)

            if not issue_id:
                return {
                    "status": "error",
                    "content": [
                        {"text": f"Issue #{issue_number} not found in {repository}"}
                    ],
                }

            item = _add_item(project_id, issue_id)
            content = item.get("content", {})

            summary = f"""
✅ **Issue added to project!**

• **Issue:** {repository}#{content.get('number')}: {content.get('title')}
• **Item ID:** `{item.get('id')}`
• **URL:** {content.get('url')}
"""

            return {"status": "success", "content": [{"text": summary}]}

        elif action == "add_pr":
            if not repository or pr_number is None:
                return {
                    "status": "error",
                    "content": [
                        {"text": "Error: repository and pr_number are required"}
                    ],
                }

            repo_owner, repo_name = _parse_repository(repository)
            pr_id = _get_pr_node_id(repo_owner, repo_name, pr_number)

            if not pr_id:
                return {
                    "status": "error",
                    "content": [{"text": f"PR #{pr_number} not found in {repository}"}],
                }

            item = _add_item(project_id, pr_id)
            content = item.get("content", {})

            summary = f"""
✅ **Pull Request added to project!**

• **PR:** {repository}#{content.get('number')}: {content.get('title')}
• **Item ID:** `{item.get('id')}`
• **URL:** {content.get('url')}
"""

            return {"status": "success", "content": [{"text": summary}]}

        elif action == "update_item":
            if not item_id or not field_name or field_value is None:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": "Error: item_id, field_name, and field_value are required"
                        }
                    ],
                }

            # Get project to find field ID and options
            project = _get_project(project_id, items_limit=1)
            fields = project.get("fields", {}).get("nodes", [])

            # Find matching field
            target_field = None
            for field in fields:
                if field.get("name") == field_name:
                    target_field = field
                    break

            if not target_field:
                available = ", ".join([f.get("name") for f in fields])
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"Field '{field_name}' not found. Available: {available}"
                        }
                    ],
                }

            field_id = target_field.get("id")
            data_type = target_field.get("dataType")

            # Handle different field types
            if data_type == "SINGLE_SELECT":
                # Find option ID
                option_id = None
                for option in target_field.get("options", []):
                    if option.get("name") == field_value:
                        option_id = option.get("id")
                        break

                if not option_id:
                    available_opts = [
                        o.get("name") for o in target_field.get("options", [])
                    ]
                    return {
                        "status": "error",
                        "content": [
                            {
                                "text": f"Option '{field_value}' not found. Available: {', '.join(available_opts)}"
                            }
                        ],
                    }

                _update_item_field(
                    project_id, item_id, field_id, option_id, "singleSelectOptionId"
                )

            elif data_type == "NUMBER":
                _update_item_field(
                    project_id, item_id, field_id, float(field_value), "number"
                )

            elif data_type == "DATE":
                _update_item_field(project_id, item_id, field_id, field_value, "date")

            else:  # TEXT, TITLE, etc.
                _update_item_field(project_id, item_id, field_id, field_value, "text")

            summary = f"""
✅ **Item updated!**

• **Item ID:** `{item_id}`
• **Field:** {field_name}
• **New Value:** {field_value}
"""

            return {"status": "success", "content": [{"text": summary}]}

        elif action == "create_field":
            if not field_name or not field_type:
                return {
                    "status": "error",
                    "content": [
                        {"text": "Error: field_name and field_type are required"}
                    ],
                }

            field = _create_field(project_id, field_name, field_type, field_options)

            summary = f"""
✅ **Field created!**

• **Field ID:** `{field.get('id')}`
• **Name:** {field.get('name')}
• **Type:** {field_type}
"""

            if field_options and "options" in field:
                opts_list = "\n".join(
                    [
                        f"  • {o.get('name')} (ID: {o.get('id')})"
                        for o in field.get("options", [])
                    ]
                )
                summary += f"\n**Options:**\n{opts_list}"

            return {"status": "success", "content": [{"text": summary}]}

        elif action == "get_progress":
            progress = _get_progress(project_id)

            proj = progress["project"]
            summary_data = progress["summary"]
            issues = progress["issues"]
            prs = progress["pull_requests"]
            by_status = progress["by_status"]
            workflows = progress["workflows"]

            # Status breakdown
            status_lines = []
            for status, count in by_status.items():
                status_lines.append(f"  • {status}: {count}")

            # Workflow status
            workflow_lines = []
            for wf in workflows:
                icon = "✅" if wf["enabled"] else "❌"
                workflow_lines.append(f"  • {icon} {wf['name']}")

            summary = f"""
## 📊 Project Progress: {proj['title']} (#{proj['number']})

**URL:** {proj['url']}

### Summary
• **Total Items:** {summary_data['total_items']}
• **Active:** {summary_data['active_items']} | **Archived:** {summary_data['archived_items']}
• **Draft Issues:** {progress['drafts']}

### Issues ({issues['total']})
• Open: {issues['open']}
• Closed: {issues['closed']}

### Pull Requests ({prs['total']})
• Open: {prs['open']}
• Merged: {prs['merged']}
• Closed: {prs['closed']}

### By Status
{chr(10).join(status_lines) if status_lines else '  No status data'}

### Workflows
{chr(10).join(workflow_lines) if workflow_lines else '  No workflows configured'}
"""

            return {"status": "success", "content": [{"text": summary}]}

        else:
            valid_actions = [
                "list_projects",
                "get_project",
                "create_project",
                "add_item",
                "add_issue",
                "add_pr",
                "update_item",
                "create_field",
                "get_progress",
            ]
            return {
                "status": "error",
                "content": [
                    {
                        "text": f"Error: Unknown action '{action}'. Valid actions: {', '.join(valid_actions)}"
                    }
                ],
            }

    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}
