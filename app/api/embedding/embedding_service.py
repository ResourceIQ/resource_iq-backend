import logging
import re
import unicodedata
from typing import Any, cast

import requests
from sqlalchemy.orm import Session

from app.api.embedding.embedding_model import GitHubPRVector
from app.api.integrations.GitHub.github_schema import GitHubUser, PullRequestContent
from app.core.config import settings

logger = logging.getLogger(__name__)


class VectorEmbeddingService:
    def __init__(self, db: Session, use_api: bool = True):
        """
        Args:
            db: Database session
            use_api: If True, use Jina API. If False, use local model.
        """
        self.db = db
        self.use_api = use_api

        if use_api:
            self.api_key = settings.JINA_API_KEY
            self.api_url = f"{settings.JINA_API_URL}/v1/embeddings"
            self.embedding_model = settings.JINA_EMBEDDING_MODEL1
            logger.debug(
                f"Using Jina API for embeddings with model: {self.embedding_model}"
            )
        else:
            # Local embedding model
            try:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer(settings.JINA_EMBEDDING_MODEL2)
                logger.debug(
                    f"Using local Jina model for embeddings: {settings.JINA_EMBEDDING_MODEL2}"
                )
            except ImportError:
                raise ImportError(
                    "Install sentence-transformers for local embeddings: pip install sentence-transformers"
                )

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using Jina (API or local)."""
        if self.use_api:
            raw_embeddings = self._generate_embeddings_api(texts)
        else:
            raw_embeddings = self._generate_embeddings_local(texts)

        # Normalize shape early so downstream callers can assume consistent dimensions
        return [self._normalize_embedding_dimension(emb) for emb in raw_embeddings]

    def _clean_text_for_embedding(self, text: str) -> str:
        """Clean text to remove problematic characters for Jina API."""
        if not text or not text.strip():
            return "Empty content"

        # Normalize Unicode characters
        text = unicodedata.normalize("NFKD", text)

        # Remove control characters except newline, tab, carriage return
        text = "".join(
            char
            for char in text
            if unicodedata.category(char)[0] != "C" or char in "\n\t\r"
        )

        # Remove zero-width characters
        text = re.sub(r"[\u200b-\u200f\u2028-\u202f\ufeff]", "", text)

        # Replace multiple whitespace with single space
        text = re.sub(r"\s+", " ", text)

        # Ensure it's valid UTF-8
        text = text.encode("utf-8", errors="ignore").decode("utf-8")

        # Truncate if too long (Jina limit is 8192)
        if len(text) > 8000:
            text = text[:8000] + "... [truncated]"

        return text.strip() or "Empty content after cleaning"

    def _generate_embeddings_api(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using Jina API."""
        try:
            # Clean all texts before sending to API
            cleaned_texts = [self._clean_text_for_embedding(text) for text in texts]

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            payload = {"model": self.embedding_model, "input": cleaned_texts}

            logger.info(
                f"Calling Jina API with model: {self.embedding_model}, URL: {self.api_url}"
            )

            response = requests.post(
                self.api_url, json=payload, headers=headers, timeout=60
            )

            if response.status_code != 200:
                logger.error(f"Jina API Error - Status: {response.status_code}")
                logger.error(f"Response body: {response.text}")

            response.raise_for_status()

            response_data = cast(dict[str, Any], response.json())
            data_items = cast(list[dict[str, Any]], response_data.get("data", []))
            embeddings: list[list[float]] = []
            for item in data_items:
                embedding = item.get("embedding") if isinstance(item, dict) else None
                if isinstance(embedding, list):
                    embeddings.append(cast(list[float], embedding))
            logger.info(f"Generated {len(embeddings)} embeddings via Jina API")
            return embeddings

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error from Jina API: {str(e)}")
            if e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error generating embeddings via API: {str(e)}")
            raise

    def _generate_embeddings_local(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using local Jina model."""
        try:
            embeddings = self.model.encode(texts, show_progress_bar=True)
            logger.info(f"Generated {len(embeddings)} embeddings locally")
            return cast(list[list[float]], embeddings.tolist())
        except Exception as e:
            logger.error(f"Error generating local embeddings: {str(e)}")
            raise

    def store_pr_contexts(
        self, author: GitHubUser, pr_contents: list[PullRequestContent]
    ) -> None:
        """Store PR contexts with embeddings in pgvector."""
        if not pr_contents:
            logger.info(f"No PR contexts to store for author {author.login}")
            return

        # Prepare pr_context for embedding
        pr_contexts = [pr.context or "" for pr in pr_contents]

        # Generate embeddings with fallback to local model if API fails
        try:
            embeddings = self.generate_embeddings(pr_contexts)
        except Exception as e:
            logger.warning(
                f"Batch embedding failed for {author.login}, processing individually: {str(e)}"
            )
            embeddings_fallback: list[list[float]] = []
            for i, doc in enumerate(pr_contexts):
                try:
                    single_embedding = self.generate_embeddings([doc])[0]
                    embeddings_fallback.append(single_embedding)
                except Exception as doc_error:
                    logger.error(
                        f"Failed to embed PR {pr_contents[i].number} for {author.login}: {str(doc_error)}"
                    )
                    logger.error(f"Problematic text preview: {doc[:200]}...")
                    # Skip this PR
                    continue
            embeddings = embeddings_fallback

        # Store in database
        for pr, embedding in zip(pr_contents, embeddings, strict=False):
            try:
                # Check if already exists
                pr_filter = cast(Any, GitHubPRVector.pr_id == str(pr.id))
                existing = self.db.query(GitHubPRVector).filter(pr_filter).first()

                if existing:
                    # Update existing
                    existing.embedding = embedding
                    existing.context = pr.context or ""
                    existing.pr_url = str(pr.html_url)
                    existing.pr_title = pr.title
                    existing.pr_description = pr.body or ""
                    logger.debug(f"Updated PR {pr.number}")
                else:
                    # Create new
                    db_pr_vector = GitHubPRVector(
                        pr_id=str(pr.id),
                        pr_number=pr.number,
                        author_login=pr.author.login,
                        author_id=pr.author.id,
                        repo_id=pr.repo_id,
                        repo_name=pr.repo_name or "",
                        pr_title=pr.title,
                        pr_url=str(pr.html_url),
                        pr_description=pr.body or "",
                        embedding=embedding,
                        context=pr.context or "",
                        metadata_json={
                            "changed_files": pr.changed_files or [],
                            "labels": pr.labels or [],
                        },
                    )
                    self.db.add(db_pr_vector)
                    logger.debug(f"Created PR {pr.number}")

            except Exception as e:
                logger.error(f"Error storing PR {pr.number}: {str(e)}")
                self.db.rollback()
                continue

        self.db.commit()
        logger.info(f"Stored {len(embeddings)} PR vectors for {author.login}")

    def _normalize_embedding_dimension(self, embedding: list[float]) -> list[float]:
        """Normalize embedding to configured dimensions (default 1536)."""
        target_dim = settings.EMBEDDING_DIMENSION

        if len(embedding) == target_dim:
            return embedding
        elif len(embedding) < target_dim:
            # Pad with zeros to reach target dimension
            padding_size = target_dim - len(embedding)
            return embedding + [0.0] * padding_size
        else:
            # Truncate if larger than target dimension
            logger.warning(
                f"Embedding size {len(embedding)} exceeds {target_dim}, truncating"
            )
            return embedding[:target_dim]

    def store_all_authors_pr_contexts(
        self, authors_prs: dict[str, list[PullRequestContent]]
    ) -> None:
        """Store PR contexts for all authors."""
        total_stored = 0
        for _author_login, pr_contents in authors_prs.items():
            if pr_contents:
                author = pr_contents[0].author
                self.store_pr_contexts(author, pr_contents)
                total_stored += len(pr_contents)

        logger.info(f"Total PRs stored: {total_stored}")
