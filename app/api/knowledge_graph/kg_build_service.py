import logging
from typing import cast

from pydantic import HttpUrl
from sqlmodel import Session, select

from app.api.embedding.embedding_model import GitHubPRVector
from app.api.integrations.GitHub.github_schema import GitHubUser, PullRequestContent
from app.api.knowledge_graph.kg_extractor import LLMEntityExtractor
from app.api.knowledge_graph.kg_schema import (
    KGBuildResult,
    KGPRSnapshot,
    KGResourceSnapshot,
)
from app.api.knowledge_graph.kg_service import KnowledgeGraphService
from app.api.profiles.profile_model import ResourceProfile

logger = logging.getLogger(__name__)


class KGBuildService:
    def __init__(self, session: Session, kg_service: KnowledgeGraphService):
        self.session = session
        self.kg_service = kg_service
        self.extractor = LLMEntityExtractor()

    def _load_resource_snapshots(self) -> list[KGResourceSnapshot]:
        statement = select(ResourceProfile)
        resources = self.session.exec(statement).all()
        snapshots = [
            KGResourceSnapshot(
                id=resource.id,
                github_id=resource.github_id,
                github_login=resource.github_login,
            )
            for resource in resources
        ]
        self.session.rollback()
        return snapshots

    def _load_pr_snapshots(
        self,
        github_id: int,
        author_login: str | None,
        batch_size: int,
    ) -> list[KGPRSnapshot]:
        statement = select(GitHubPRVector).where(GitHubPRVector.author_id == github_id)
        if author_login is not None:
            statement = statement.where(GitHubPRVector.author_login == author_login)

        prs = self.session.exec(statement).all()[:batch_size]
        snapshots = [
            KGPRSnapshot(
                pr_id=pr.pr_id,
                id=pr.id,
                pr_number=pr.pr_number,
                pr_title=pr.pr_title,
                pr_description=pr.pr_description,
                pr_url=pr.pr_url,
                repo_id=pr.repo_id,
                repo_name=pr.repo_name,
                metadata_json=pr.metadata_json,
                author_login=pr.author_login,
                author_id=pr.author_id,
                context=pr.context,
            )
            for pr in prs
        ]
        self.session.rollback()
        return snapshots

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
        skipped_prs = 0
        resource_snapshots = self._load_resource_snapshots()
        logger.info(
            "KG build started: resources=%d author_filter=%s batch_size=%d",
            len(resource_snapshots),
            author_login,
            batch_size,
        )

        for resource_idx, resource in enumerate(resource_snapshots, start=1):
            try:
                if resource.github_id is None:
                    logger.debug(
                        "KG build skipping resource #%d (profile_id=%s) without github_id",
                        resource_idx,
                        resource.id,
                    )
                    continue

                pr_snapshots = self._load_pr_snapshots(
                    github_id=resource.github_id,
                    author_login=author_login,
                    batch_size=batch_size,
                )
                logger.info(
                    "KG build processing resource #%d login=%s github_id=%s prs=%d",
                    resource_idx,
                    resource.github_login,
                    resource.github_id,
                    len(pr_snapshots),
                )

                for pr_idx, pr in enumerate(pr_snapshots, start=1):
                    if pr.pr_id is not None:
                        try:
                            pr_identifier = int(pr.pr_id)
                        except (TypeError, ValueError):
                            pr_identifier = pr.id or pr.pr_number
                    else:
                        pr_identifier = pr.id or pr.pr_number

                    logger.debug(
                        "KG build processing PR %d/%d for resource=%s pr_id=%s pr_number=%s repo=%s",
                        pr_idx,
                        len(pr_snapshots),
                        resource.github_login,
                        pr_identifier,
                        pr.pr_number,
                        pr.repo_name,
                    )

                    meta = pr.metadata_json or {}
                    changed_files = cast(list[str], meta.get("changed_files", []))
                    labels = cast(list[str], meta.get("labels", []))
                    commit_messages = cast(list[str], meta.get("commit_messages", []))

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
                            changed_files=changed_files,
                            labels=labels,
                            author=GitHubUser(
                                login=pr.author_login,
                                id=pr.author_id,
                            ),
                            context=pr.context,
                        ),
                        repo_name=pr.repo_name,
                    )

                    if (
                        self.kg_service.pr_exists(pr_identifier)
                        and self.kg_service.pr_has_entity_links(pr_identifier)
                        and self.kg_service.pr_has_context(pr_identifier)
                    ):
                        skipped_prs += 1
                        logger.debug(
                            "KG build skipping already-ingested PR %d/%d for resource=%s pr_id=%s",
                            pr_idx,
                            len(pr_snapshots),
                            resource.github_login,
                            pr_identifier,
                        )
                        continue

                    # ── Extract entities ─────────────────────────────────
                    entities = self.extractor.extract(
                        files=changed_files,
                        commit_messages=commit_messages,
                        title=pr.pr_title,
                        body=pr.pr_description or "",
                        labels=labels,
                    )

                    # ── Pass entities to graph service ───────────────────
                    self.kg_service.upsert_pr_entities(
                        pr_id=pr_identifier,
                        author_id=resource.github_id,
                        entities=entities,
                    )

                    logger.debug(
                        "KG build upserted entities for pr_id=%s languages=%d frameworks=%d domains=%d skills=%d tools=%d",
                        pr_identifier,
                        len(entities.languages),
                        len(entities.frameworks),
                        len(entities.domains),
                        len(entities.skills),
                        len(entities.tools),
                    )

                    results["prs_processed"] += 1

                results["profiles_updated"] += 1
                logger.info(
                    "KG build completed resource login=%s processed_prs=%d cumulative_prs=%d",
                    resource.github_login,
                    len(pr_snapshots),
                    results["prs_processed"],
                )
            except Exception as exc:
                self.session.rollback()
                resource_identifier = resource.github_login or str(resource.github_id)
                error_msg = f"Error processing resource {resource_identifier}: {exc}"
                logger.error(error_msg)
                results["errors"].append(error_msg)

        logger.info(
            "KG build finished: prs_processed=%d prs_skipped=%d profiles_updated=%d errors=%d",
            results["prs_processed"],
            skipped_prs,
            results["profiles_updated"],
            len(results["errors"]),
        )
        return results
