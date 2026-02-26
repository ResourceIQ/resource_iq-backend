
import logging

from sqlmodel import Session, select

from app.api.embedding.embedding_model import GitHubPRVector
from app.api.integrations.GitHub.github_schema import GitHubUser, PullRequestContent
from app.api.knowledge_graph.kg_service import KnowledgeGraphService
from app.api.profiles.profile_model import ResourceProfile

logger = logging.getLogger(__name__)

class KGBuildService:
    def __init__(self, session: Session, kg_service: KnowledgeGraphService):
        self.session = session
        self.kg_service = kg_service

    def build_from_stored_vectors(
        self,
        author_login: str | None = None,   # None = all authors
        batch_size: int = 50,
    ) -> dict:
        results = {
            "prs_processed": 0,
            "profiles_updated": 0,
            "errors": [],
        }

        statement = select(ResourceProfile)
        resources = self.session.exec(statement).all()

        for resource in resources:
            try:
                if resource.github_id is None:
                    continue

                statement = select(GitHubPRVector).where(
                    GitHubPRVector.author_id == resource.github_id
                )
                prs = self.session.exec(statement).all()
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
                            html_url=pr.pr_url,
                            repo_id=pr.repo_id,
                            repo_name=pr.repo_name,
                            changed_files=(pr.metadata_json or {}).get("changed_files", []),
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
            except Exception as e:
                error_msg = f"Error processing PR {pr.pr_number} ({pr.pr_id}): {str(e)}"
                logger.error(error_msg)
                results["errors"].append(error_msg)

        return results
