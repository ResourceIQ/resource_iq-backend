import logging
from typing import cast

from pydantic import HttpUrl
from sqlmodel import Session, select

from app.api.embedding.embedding_model import GitHubPRVector
from app.api.integrations.GitHub.github_schema import GitHubUser, PullRequestContent
from app.api.knowledge_graph.kg_schema import KGBuildResult
from app.api.knowledge_graph.kg_service import KnowledgeGraphService
from app.api.profiles.profile_model import ResourceProfile

logger = logging.getLogger(__name__)


class KGBuildService:
    def __init__(self, session: Session, kg_service: KnowledgeGraphService):
        self.session = session
        self.kg_service = kg_service

    def build_from_stored_vectors(
        self,
        author_login: str | None = None,  # None = all authors
        batch_size: int = 50,
    ) -> KGBuildResult:
        results: KGBuildResult = {
            "prs_processed": 0,
            "profiles_updated": 0,
            "errors": [],
        }

        resource_statement = select(ResourceProfile)
        resources = self.session.exec(resource_statement).all()

        for resource in resources:
            try:
                if resource.github_id is None:
                    continue

                pr_statement = select(GitHubPRVector).where(
                    GitHubPRVector.author_id == resource.github_id
                )
                if author_login is not None:
                    pr_statement = pr_statement.where(
                        GitHubPRVector.author_login == author_login
                    )

                prs = self.session.exec(pr_statement).all()[:batch_size]
                for pr in prs:
                    try:
                        pr_identifier = int(pr.pr_id)
                    except (TypeError, ValueError):
                        pr_identifier = pr.id or pr.pr_number

                    # Upsert PR and related nodes/relationships in the KG
                    self.kg_service.upsert_pr(
                        PullRequestContent(
                            id=pr_identifier,
                            number=pr.pr_number,
                            title=pr.pr_title,
                            body=pr.pr_description,
                            html_url=cast(HttpUrl, pr.pr_url),
                            repo_id=pr.repo_id,
                            repo_name=pr.repo_name,
                            changed_files=(pr.metadata_json or {}).get(
                                "changed_files", []
                            ),
                            labels=(pr.metadata_json or {}).get("labels", []),
                            author=GitHubUser(
                                login=pr.author_login,
                                id=pr.author_id,
                            ),
                            context="",
                        ),
                        repo_name=pr.repo_name,
                    )
                    results["prs_processed"] += 1

                results["profiles_updated"] += 1
            except Exception as exc:
                resource_identifier = resource.github_login or str(resource.github_id)
                error_msg = f"Error processing resource {resource_identifier}: {exc}"
                logger.error(error_msg)
                results["errors"].append(error_msg)

        return results
