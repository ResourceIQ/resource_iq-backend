"""Jira integration service class."""

import logging
import re
from datetime import datetime
from typing import Any, cast

from jira import JIRA
from jira.resources import Issue
from pydantic import HttpUrl
from sqlalchemy.orm import Session

from app.api.embedding.embedding_service import VectorEmbeddingService
from app.api.integrations.Jira.jira_model import (
    DeveloperProfile,
    JiraIssue,
    JiraIssueVector,
    JiraOrgIntegration,
)
from app.api.integrations.Jira.jira_schema import (
    DeveloperWorkload,
    JiraComment,
    JiraIssueContent,
    JiraSyncResponse,
    JiraUser,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class JiraIntegrationService:
    """Service class for Jira API integration."""

    def __init__(self, db: Session, use_jina_api: bool = True) -> None:
        self.db = db
        self.vector_service = VectorEmbeddingService(db, use_api=use_jina_api)
        self._client: JIRA | None = None

        # Load integration config from database or settings
        self.integration = db.query(JiraOrgIntegration).first()

    def get_jira_client(self) -> JIRA:
        """
        Initialize and return the Jira client using credentials.
        Uses database config if available, otherwise falls back to environment.
        """
        if self._client:
            return self._client

        # Determine URL and credentials
        jira_url = (
            self.integration.jira_url if self.integration else settings.JIRA_URL
        )
        jira_email = (
            self.integration.jira_email if self.integration else settings.JIRA_EMAIL
        )
        jira_token = settings.JIRA_API_TOKEN

        if not jira_url or not jira_email or not jira_token:
            raise ValueError(
                "Jira credentials not configured. Set JIRA_URL, JIRA_EMAIL, and JIRA_API_TOKEN."
            )

        self._client = JIRA(
            server=jira_url,
            basic_auth=(jira_email, jira_token),
        )
        return self._client

    @property
    def jira_url(self) -> str:
        """Get the configured Jira URL."""
        if self.integration:
            return self.integration.jira_url
        return settings.JIRA_URL or ""

    def get_all_projects(self) -> list[dict[str, Any]]:
        """Retrieve all accessible Jira projects."""
        client = self.get_jira_client()
        projects = client.projects()
        return [
            {
                "key": p.key,
                "name": p.name,
                "id": p.id,
            }
            for p in projects
        ]

    def fetch_issues(
        self,
        project_key: str | None = None,
        max_results: int = 100,
        include_closed: bool = True,
        jql: str | None = None,
    ) -> list[Issue]:
        """
        Fetch issues from Jira using JQL.

        Args:
            project_key: Specific project to fetch from
            max_results: Maximum number of issues to fetch
            include_closed: Whether to include closed/done issues
            jql: Custom JQL query (overrides other filters)
        """
        client = self.get_jira_client()

        if jql is None:
            jql_parts = []
            if project_key:
                jql_parts.append(f'project = "{project_key}"')
            if not include_closed:
                jql_parts.append('status NOT IN ("Done", "Closed", "Resolved")')
            jql = " AND ".join(jql_parts) if jql_parts else ""

        # Fetch issues with required fields
        issues = client.search_issues(
            jql,
            maxResults=max_results,
            fields=[
                "summary",
                "description",
                "issuetype",
                "status",
                "priority",
                "labels",
                "assignee",
                "reporter",
                "created",
                "updated",
                "resolutiondate",
                "comment",
            ],
        )

        return list(issues)

    def _parse_jira_user(self, user_data: Any) -> JiraUser | None:
        """Parse Jira user object into JiraUser schema."""
        if not user_data:
            return None

        # Handle avatar URL - avatarUrls is a PropertyHolder, not a dict
        avatar_url = None
        if hasattr(user_data, "avatarUrls") and user_data.avatarUrls:
            # Try to get the 48x48 avatar URL using getattr
            avatar_48 = getattr(user_data.avatarUrls, "48x48", None)
            if avatar_48:
                try:
                    avatar_url = HttpUrl(avatar_48)
                except Exception:
                    pass

        return JiraUser(
            account_id=getattr(user_data, "accountId", "") or "",
            display_name=getattr(user_data, "displayName", None),
            email_address=getattr(user_data, "emailAddress", None),
            avatar_url=avatar_url,
            active=getattr(user_data, "active", True),
        )

    def _parse_issue(self, issue: Issue, include_comments: bool = True) -> JiraIssueContent:
        """Parse Jira issue into JiraIssueContent schema."""
        fields = issue.fields

        # Parse labels
        labels = getattr(fields, "labels", []) or []

        # Parse assignee and reporter
        assignee = self._parse_jira_user(getattr(fields, "assignee", None))
        reporter = self._parse_jira_user(getattr(fields, "reporter", None))

        # Parse comments
        comments: list[JiraComment] = []
        if include_comments and hasattr(fields, "comment"):
            comment_data = getattr(fields.comment, "comments", [])
            for c in comment_data:
                author = self._parse_jira_user(getattr(c, "author", None))
                if author:
                    comments.append(
                        JiraComment(
                            id=c.id,
                            author=author,
                            body=getattr(c, "body", ""),
                            created=datetime.fromisoformat(
                                c.created.replace("Z", "+00:00")
                            ),
                            updated=datetime.fromisoformat(
                                c.updated.replace("Z", "+00:00")
                            )
                            if hasattr(c, "updated") and c.updated
                            else None,
                        )
                    )

        # Parse timestamps
        created_at = None
        if hasattr(fields, "created") and fields.created:
            created_at = datetime.fromisoformat(fields.created.replace("Z", "+00:00"))

        updated_at = None
        if hasattr(fields, "updated") and fields.updated:
            updated_at = datetime.fromisoformat(fields.updated.replace("Z", "+00:00"))

        resolved_at = None
        if hasattr(fields, "resolutiondate") and fields.resolutiondate:
            resolved_at = datetime.fromisoformat(
                fields.resolutiondate.replace("Z", "+00:00")
            )

        issue_content = JiraIssueContent(
            issue_id=issue.id,
            issue_key=issue.key,
            project_key=issue.key.split("-")[0],
            summary=fields.summary,
            description=getattr(fields, "description", None),
            issue_type=fields.issuetype.name if fields.issuetype else "Unknown",
            status=fields.status.name if fields.status else "Unknown",
            priority=fields.priority.name if fields.priority else None,
            labels=labels,
            assignee=assignee,
            reporter=reporter,
            issue_url=HttpUrl(f"{self.jira_url}/browse/{issue.key}"),
            comments=comments,
            created_at=created_at,
            updated_at=updated_at,
            resolved_at=resolved_at,
        )

        # Generate context for NLP processing
        issue_content.context = self._generate_issue_context(issue_content)

        return issue_content

    def _generate_issue_context(self, issue: JiraIssueContent) -> str:
        """
        Generate a context string from issue for NLP/embedding processing.
        Similar to GitHub PR context generation.
        """
        # Clean description
        clean_description = ""
        if issue.description:
            # Remove Jira markup/formatting
            clean_description = re.sub(
                r"\{[^}]+\}", "", issue.description
            )  # Remove {code}, {quote}, etc.
            clean_description = re.sub(
                r"\[~[^\]]+\]", "", clean_description
            )  # Remove user mentions
            clean_description = clean_description[:1500]  # Limit length

        # Build context
        context_parts = [
            f"ISSUE_TYPE: {issue.issue_type}",
            f"SUMMARY: {issue.summary}",
            f"STATUS: {issue.status}",
        ]

        if issue.priority:
            context_parts.append(f"PRIORITY: {issue.priority}")

        if issue.labels:
            context_parts.append(f"LABELS: {', '.join(issue.labels)}")

        if clean_description:
            context_parts.append(f"DESCRIPTION: {clean_description}")

        # Include key comments (limited)
        if issue.comments:
            comment_texts = [c.body[:200] for c in issue.comments[:3]]
            context_parts.append(f"KEY_COMMENTS: {' | '.join(comment_texts)}")

        return "\n".join(context_parts)

    def sync_issues(
        self,
        project_keys: list[str] | None = None,
        max_results: int = 100,
        include_closed: bool = True,
        sync_comments: bool = True,
        generate_embeddings: bool = True,
    ) -> JiraSyncResponse:
        """
        Sync issues from Jira to local database.
        Main data ingestion pipeline (FR4).
        """
        import time

        start_time = time.time()

        # Get projects to sync
        if project_keys is None:
            if self.integration and self.integration.project_keys:
                project_keys = self.integration.project_keys.split(",")
            else:
                # Sync all accessible projects
                projects = self.get_all_projects()
                project_keys = [p["key"] for p in projects]

        issues_created = 0
        issues_updated = 0
        embeddings_generated = 0
        errors: list[str] = []
        all_issue_contents: list[JiraIssueContent] = []

        for project_key in project_keys:
            try:
                logger.info(f"Syncing Jira project: {project_key}")
                issues = self.fetch_issues(
                    project_key=project_key,
                    max_results=max_results,
                    include_closed=include_closed,
                )

                for issue in issues:
                    try:
                        issue_content = self._parse_issue(
                            issue, include_comments=sync_comments
                        )
                        all_issue_contents.append(issue_content)

                        # Store/update in database
                        created = self._store_issue(issue_content)
                        if created:
                            issues_created += 1
                        else:
                            issues_updated += 1

                    except Exception as e:
                        error_msg = f"Error processing issue {issue.key}: {str(e)}"
                        logger.error(error_msg)
                        errors.append(error_msg)

            except Exception as e:
                error_msg = f"Error syncing project {project_key}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Generate embeddings if requested
        if generate_embeddings and all_issue_contents:
            try:
                embeddings_generated = self._store_issue_embeddings(all_issue_contents)
            except Exception as e:
                error_msg = f"Error generating embeddings: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Update developer workloads
        try:
            self._update_all_developer_workloads()
        except Exception as e:
            logger.warning(f"Error updating workloads: {str(e)}")

        self.db.commit()

        duration = time.time() - start_time

        return JiraSyncResponse(
            status="completed" if not errors else "completed_with_errors",
            projects_synced=project_keys,
            issues_synced=issues_created + issues_updated,
            issues_created=issues_created,
            issues_updated=issues_updated,
            embeddings_generated=embeddings_generated,
            errors=errors,
            sync_duration_seconds=round(duration, 2),
        )

    def _store_issue(self, issue_content: JiraIssueContent) -> bool:
        """
        Store or update a Jira issue in the database.
        Returns True if created, False if updated.
        """
        # Check if issue exists
        existing = (
            self.db.query(JiraIssue)
            .filter(cast(Any, JiraIssue.issue_id == issue_content.issue_id))
            .first()
        )

        if existing:
            # Update existing issue
            existing.summary = issue_content.summary
            existing.description = issue_content.description
            existing.status = issue_content.status
            existing.priority = issue_content.priority
            existing.labels = ",".join(issue_content.labels) if issue_content.labels else None
            existing.assignee_account_id = (
                issue_content.assignee.account_id if issue_content.assignee else None
            )
            existing.assignee_display_name = (
                issue_content.assignee.display_name if issue_content.assignee else None
            )
            existing.assignee_email = (
                issue_content.assignee.email_address if issue_content.assignee else None
            )
            existing.jira_updated_at = issue_content.updated_at
            existing.jira_resolved_at = issue_content.resolved_at
            existing.updated_at = datetime.utcnow()
            existing.comments_json = (
                {"comments": [c.model_dump(mode="json") for c in issue_content.comments]}
                if issue_content.comments
                else None
            )
            return False
        else:
            # Create new issue
            db_issue = JiraIssue(
                issue_id=issue_content.issue_id,
                issue_key=issue_content.issue_key,
                project_key=issue_content.project_key,
                summary=issue_content.summary,
                description=issue_content.description,
                issue_type=issue_content.issue_type,
                status=issue_content.status,
                priority=issue_content.priority,
                labels=",".join(issue_content.labels) if issue_content.labels else None,
                assignee_account_id=(
                    issue_content.assignee.account_id if issue_content.assignee else None
                ),
                assignee_display_name=(
                    issue_content.assignee.display_name if issue_content.assignee else None
                ),
                assignee_email=(
                    issue_content.assignee.email_address if issue_content.assignee else None
                ),
                reporter_account_id=(
                    issue_content.reporter.account_id if issue_content.reporter else None
                ),
                reporter_display_name=(
                    issue_content.reporter.display_name if issue_content.reporter else None
                ),
                issue_url=str(issue_content.issue_url),
                jira_created_at=issue_content.created_at,
                jira_updated_at=issue_content.updated_at,
                jira_resolved_at=issue_content.resolved_at,
                comments_json=(
                    {"comments": [c.model_dump(mode="json") for c in issue_content.comments]}
                    if issue_content.comments
                    else None
                ),
            )
            self.db.add(db_issue)
            return True

    def _store_issue_embeddings(self, issues: list[JiraIssueContent]) -> int:
        """
        Generate and store embeddings for issues.
        Prepares data for NLP processing (FR5).
        """
        if not issues:
            return 0

        # Get contexts for embedding
        contexts = [issue.context or "" for issue in issues if issue.context]
        valid_issues = [issue for issue in issues if issue.context]

        if not contexts:
            return 0

        try:
            embeddings = self.vector_service.generate_embeddings(contexts)
        except Exception as e:
            logger.warning(f"Batch embedding failed, processing individually: {str(e)}")
            embeddings = []
            for context in contexts:
                try:
                    embedding = self.vector_service.generate_embeddings([context])[0]
                    embeddings.append(embedding)
                except Exception as doc_error:
                    logger.error(f"Failed to embed context: {str(doc_error)}")

        stored_count = 0
        for issue, embedding in zip(valid_issues, embeddings, strict=False):
            try:
                # Normalize embedding dimension
                embedding = self.vector_service._normalize_embedding_dimension(embedding)

                # Check if exists
                existing = (
                    self.db.query(JiraIssueVector)
                    .filter(cast(Any, JiraIssueVector.issue_id == issue.issue_id))
                    .first()
                )

                if existing:
                    existing.embedding = embedding
                    existing.context = issue.context or ""
                    existing.updated_at = datetime.utcnow()
                else:
                    db_vector = JiraIssueVector(
                        issue_id=issue.issue_id,
                        issue_key=issue.issue_key,
                        project_key=issue.project_key,
                        assignee_account_id=(
                            issue.assignee.account_id if issue.assignee else None
                        ),
                        embedding=embedding,
                        context=issue.context or "",
                    )
                    self.db.add(db_vector)

                stored_count += 1

            except Exception as e:
                logger.error(f"Error storing embedding for {issue.issue_key}: {str(e)}")

        return stored_count

    def calculate_developer_workload(self, jira_account_id: str) -> DeveloperWorkload:
        """
        Calculate workload for a developer based on their open/in-progress issues.
        Satisfies FR8: Workload calculation.
        """
        # Query issues assigned to this developer
        issues = (
            self.db.query(JiraIssue)
            .filter(cast(Any, JiraIssue.assignee_account_id == jira_account_id))
            .all()
        )

        # Get developer info
        first_issue = issues[0] if issues else None
        display_name = first_issue.assignee_display_name if first_issue else None
        email = first_issue.assignee_email if first_issue else None

        # Count by status
        open_issues = 0
        in_progress_issues = 0
        in_review_issues = 0

        # Count by priority
        high_priority = 0
        medium_priority = 0
        low_priority = 0

        # Count by type
        bugs = 0
        tasks = 0
        stories = 0
        other = 0

        active_statuses = ["Open", "To Do", "In Progress", "In Review", "Reopened"]

        for issue in issues:
            if issue.status not in active_statuses:
                continue

            # Status counts
            if issue.status in ["Open", "To Do", "Reopened"]:
                open_issues += 1
            elif issue.status == "In Progress":
                in_progress_issues += 1
            elif issue.status == "In Review":
                in_review_issues += 1

            # Priority counts
            priority = (issue.priority or "").lower()
            if priority in ["highest", "high", "critical", "blocker"]:
                high_priority += 1
            elif priority in ["medium", "normal"]:
                medium_priority += 1
            elif priority in ["low", "lowest", "trivial"]:
                low_priority += 1

            # Type counts
            issue_type = (issue.issue_type or "").lower()
            if "bug" in issue_type:
                bugs += 1
            elif "task" in issue_type or "sub-task" in issue_type:
                tasks += 1
            elif "story" in issue_type or "feature" in issue_type:
                stories += 1
            else:
                other += 1

        total_active = open_issues + in_progress_issues + in_review_issues

        # Calculate weighted workload score
        # High priority issues count more, bugs count more than tasks
        workload_score = (
            (high_priority * 3.0)
            + (medium_priority * 2.0)
            + (low_priority * 1.0)
            + (bugs * 1.5)  # Bugs add extra weight
            + (in_progress_issues * 0.5)  # In-progress adds slight weight
        )

        return DeveloperWorkload(
            jira_account_id=jira_account_id,
            display_name=display_name,
            email=email,
            open_issues=open_issues,
            in_progress_issues=in_progress_issues,
            in_review_issues=in_review_issues,
            total_active_issues=total_active,
            high_priority_count=high_priority,
            medium_priority_count=medium_priority,
            low_priority_count=low_priority,
            bugs_count=bugs,
            tasks_count=tasks,
            stories_count=stories,
            other_count=other,
            workload_score=round(workload_score, 2),
            last_updated=datetime.utcnow(),
        )

    def _update_all_developer_workloads(self) -> None:
        """Update workload for all developers with assigned issues."""
        # Get unique assignees
        assignees = (
            self.db.query(JiraIssue.assignee_account_id)
            .filter(cast(Any, JiraIssue.assignee_account_id.isnot(None)))
            .distinct()
            .all()
        )

        for (account_id,) in assignees:
            if not account_id:
                continue

            try:
                workload = self.calculate_developer_workload(account_id)

                # Update or create developer profile
                profile = (
                    self.db.query(DeveloperProfile)
                    .filter(cast(Any, DeveloperProfile.jira_account_id == account_id))
                    .first()
                )

                if profile:
                    profile.current_workload = workload.total_active_issues
                    profile.workload_updated_at = datetime.utcnow()
                    profile.jira_display_name = workload.display_name
                    profile.jira_email = workload.email
                else:
                    profile = DeveloperProfile(
                        jira_account_id=account_id,
                        jira_display_name=workload.display_name,
                        jira_email=workload.email,
                        current_workload=workload.total_active_issues,
                        workload_updated_at=datetime.utcnow(),
                    )
                    self.db.add(profile)

            except Exception as e:
                logger.warning(f"Error updating workload for {account_id}: {str(e)}")

    def get_all_developers(self) -> list[dict[str, Any]]:
        """Get all Jira users who have been assigned issues."""
        profiles = self.db.query(DeveloperProfile).all()
        return [
            {
                "jira_account_id": p.jira_account_id,
                "display_name": p.jira_display_name,
                "email": p.jira_email,
                "github_login": p.github_login,
                "internal_user_id": p.internal_user_id,
                "current_workload": p.current_workload,
                "skills": p.skills.split(",") if p.skills else [],
                "domains": p.domains.split(",") if p.domains else [],
            }
            for p in profiles
        ]

    def map_user(
        self,
        jira_account_id: str,
        internal_user_id: str | None = None,
        github_login: str | None = None,
    ) -> DeveloperProfile:
        """
        Map a Jira user to internal ResourceIQ profile and/or GitHub account.
        Satisfies UC-002: User Mapping.
        """
        profile = (
            self.db.query(DeveloperProfile)
            .filter(cast(Any, DeveloperProfile.jira_account_id == jira_account_id))
            .first()
        )

        if not profile:
            profile = DeveloperProfile(jira_account_id=jira_account_id)
            self.db.add(profile)

        if internal_user_id:
            profile.internal_user_id = internal_user_id
        if github_login:
            profile.github_login = github_login

        profile.updated_at = datetime.utcnow()
        self.db.commit()

        return profile

    def search_similar_issues(
        self,
        query: str,
        n_results: int = 5,
        project_key: str | None = None,
        assignee_account_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for similar Jira issues using vector similarity.
        Useful for finding related issues or recommending developers.
        """
        try:
            # Generate embedding for query
            query_embedding = self.vector_service.generate_embeddings([query])[0]
            query_embedding = self.vector_service._normalize_embedding_dimension(
                query_embedding
            )

            # Build query
            query_obj = self.db.query(JiraIssueVector)

            if project_key:
                query_obj = query_obj.filter(
                    cast(Any, JiraIssueVector.project_key == project_key)
                )

            if assignee_account_id:
                query_obj = query_obj.filter(
                    cast(Any, JiraIssueVector.assignee_account_id == assignee_account_id)
                )

            # Order by similarity
            results = (
                query_obj.order_by(
                    JiraIssueVector.embedding.l2_distance(query_embedding)
                )
                .limit(n_results)
                .all()
            )

            return [
                {
                    "issue_id": r.issue_id,
                    "issue_key": r.issue_key,
                    "project_key": r.project_key,
                    "assignee_account_id": r.assignee_account_id,
                    "context": r.context,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in results
            ]

        except Exception as e:
            logger.error(f"Error searching similar issues: {str(e)}")
            raise

    def process_webhook_event(self, event_type: str, payload: dict) -> dict[str, Any]:
        """
        Process a Jira webhook event for real-time updates.
        """
        result = {"event_type": event_type, "processed": False}

        try:
            if event_type in ["jira:issue_created", "jira:issue_updated"]:
                issue_data = payload.get("issue")
                if issue_data:
                    # Fetch full issue details and sync
                    client = self.get_jira_client()
                    issue = client.issue(issue_data["key"])
                    issue_content = self._parse_issue(issue)
                    created = self._store_issue(issue_content)

                    # Generate embedding
                    if issue_content.context:
                        self._store_issue_embeddings([issue_content])

                    # Update workload if assignee exists
                    if issue_content.assignee:
                        self._update_all_developer_workloads()

                    self.db.commit()

                    result["processed"] = True
                    result["issue_key"] = issue.key
                    result["action"] = "created" if created else "updated"

            elif event_type == "jira:issue_deleted":
                issue_data = payload.get("issue")
                if issue_data:
                    issue_id = issue_data.get("id")
                    # Delete from database
                    self.db.query(JiraIssue).filter(
                        cast(Any, JiraIssue.issue_id == issue_id)
                    ).delete()
                    self.db.query(JiraIssueVector).filter(
                        cast(Any, JiraIssueVector.issue_id == issue_id)
                    ).delete()
                    self.db.commit()

                    result["processed"] = True
                    result["action"] = "deleted"

        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            result["error"] = str(e)

        return result

