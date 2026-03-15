import logging
import math
import re
import time
import unicodedata
from typing import Any, cast

import requests
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.api.embedding.embedding_model import GitHubPRVector
from app.api.integrations.GitHub.github_schema import GitHubUser, PullRequestContent
from app.core.config import settings

logger = logging.getLogger(__name__)


def is_retryable_error(exception: BaseException) -> bool:
    """Check if the exception corresponds to a retryable error (Connection, 429, 5xx)."""
    if isinstance(exception, requests.exceptions.HTTPError):
        status_code = exception.response.status_code if exception.response else 0
        return status_code == 429 or status_code >= 500
    return isinstance(exception, requests.exceptions.RequestException)


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
            if not settings.JINA_API_KEY:
                raise ValueError(
                    "JINA_API_KEY is required when embeddings are configured to use the Jina API"
                )
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

    def generate_embeddings(
        self, texts: list[str], prompt_name: str | None = None
    ) -> list[list[float]]:
        """Generate embeddings using Jina (API or local)."""
        if self.use_api:
            raw_embeddings = self._generate_embeddings_api(texts, prompt_name)
        else:
            raw_embeddings = self._generate_embeddings_local(texts, prompt_name)

        # Normalize shape early so downstream callers can assume consistent dimensions
        return [self._normalize_embedding_dimension(emb) for emb in raw_embeddings]

    @staticmethod
    def _prompt_name_to_task(prompt_name: str | None) -> str | None:
        """Map local prompt_name style (e.g. nl2code_query) to API task (e.g. nl2code.query)."""
        if not prompt_name:
            return None
        if prompt_name.endswith("_query"):
            return f"{prompt_name[:-6]}.query"
        if prompt_name.endswith("_document"):
            return f"{prompt_name[:-9]}.passage"
        if "." in prompt_name:
            return prompt_name
        return None

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

    def _generate_embeddings_api(
        self, texts: list[str], prompt_name: str | None = None
    ) -> list[list[float]]:
        """Generate embeddings using Jina API with batching and rate limiting."""
        # Constants for rate limiting
        batch_size = 30  # Conservative batch size
        rpm_limit = 100
        tpm_limit = 100000
        safety_margin = 0.8  # Use 80% to be very safe

        # 60s / (100 * 0.8) = 0.75s per request minimum
        min_request_interval = 60.0 / (rpm_limit * safety_margin)
        # (100000 * 0.8) / 60 = 1333 tokens/s
        tokens_per_second = (tpm_limit * safety_margin) / 60.0

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]

            # Clean texts first
            cleaned_batch = [self._clean_text_for_embedding(t) for t in batch_texts]

            # Estimate tokens (approx 4 chars per token)
            total_chars = sum(len(t) for t in cleaned_batch)
            estimated_tokens = math.ceil(total_chars / 4)

            start_time = time.time()

            try:
                batch_embeddings = self._call_jina_api_with_retry(
                    cleaned_batch, prompt_name
                )
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                logger.error(
                    f"Failed to process batch {i // batch_size} (indices {i}-{i + batch_size}): {str(e)}"
                )
                raise

            # Calculate rate limit delay
            # specific delay for tokens
            token_delay = estimated_tokens / tokens_per_second
            # max of rpm delay and tpm delay
            required_delay = max(min_request_interval, token_delay)

            elapsed = time.time() - start_time
            sleep_time = required_delay - elapsed

            if sleep_time > 0:
                logger.debug(
                    f"Rate limiting: sleeping {sleep_time:.2f}s (tokens: {estimated_tokens})"
                )
                time.sleep(sleep_time)

        return all_embeddings

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception(is_retryable_error),
    )
    def _call_jina_api_with_retry(
        self, texts: list[str], prompt_name: str | None = None
    ) -> list[list[float]]:
        """Helper to call Jina API with retry logic."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload: dict[str, Any] = {"model": self.embedding_model, "input": texts}
        task = self._prompt_name_to_task(prompt_name)
        if task:
            payload["task"] = task

        logger.info(
            f"Calling Jina API with model: {self.embedding_model}, Batch size: {len(texts)}"
        )

        response = requests.post(
            self.api_url, json=payload, headers=headers, timeout=60
        )

        # Some API/model combinations may not support task routing; retry once without task.
        if (
            task
            and response.status_code == 400
            and (
                "task" in response.text.lower()
                or "invalid task" in response.text.lower()
            )
        ):
            logger.warning(f"Jina API rejected task='{task}', retrying without task")
            payload.pop("task", None)
            response = requests.post(
                self.api_url, json=payload, headers=headers, timeout=60
            )

        if not response.ok:
            logger.error(f"Jina API Error: {response.status_code} - {response.text}")

        response.raise_for_status()

        response_data = cast(dict[str, Any], response.json())
        data_items = cast(list[dict[str, Any]], response_data.get("data", []))

        embeddings: list[list[float]] = []
        for item in data_items:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            # Simple list check
            if isinstance(embedding, list):
                embeddings.append(cast(list[float], embedding))

        return embeddings

    def _generate_embeddings_local(
        self, texts: list[str], prompt_name: str | None = None
    ) -> list[list[float]]:
        """Generate embeddings using local Jina model."""
        try:
            if prompt_name:
                try:
                    embeddings = self.model.encode(
                        texts,
                        show_progress_bar=True,
                        prompt_name=prompt_name,
                    )
                except TypeError:
                    logger.warning(
                        f"Local model encode does not support prompt_name='{prompt_name}', falling back to default encode"
                    )
                    embeddings = self.model.encode(texts, show_progress_bar=True)
            else:
                embeddings = self.model.encode(texts, show_progress_bar=True)
            logger.info(f"Generated {len(embeddings)} embeddings locally")
            return cast(list[list[float]], embeddings.tolist())
        except Exception as e:
            logger.error(f"Error generating local embeddings: {str(e)}")
            raise

    def store_pr_contexts(
        self, author: GitHubUser, pr_contents: list[PullRequestContent]
    ) -> int:
        """Store PR contexts with embeddings in pgvector. Returns count of successfully stored PRs."""
        if not pr_contents:
            logger.info(f"No PR contexts to store for author {author.login}")
            return 0

        # Filter out PRs that are already embedded to save API calls
        pr_ids = [str(pr.id) for pr in pr_contents]
        existing_pr_ids: set[str] = set()

        try:
            # Query existing PR IDs efficiently
            pr_id_column = cast(Any, GitHubPRVector.pr_id)
            existing_records = (
                self.db.query(pr_id_column).filter(pr_id_column.in_(pr_ids)).all()
            )
            existing_pr_ids = {r[0] for r in existing_records}
        except Exception as e:
            logger.warning(
                f"Failed to check existing PRs, proceeding with full list: {e}"
            )

        # Keep only new PRs
        new_pr_contents = [
            pr for pr in pr_contents if str(pr.id) not in existing_pr_ids
        ]
        skipped_count = len(pr_contents) - len(new_pr_contents)

        if skipped_count > 0:
            logger.info(
                f"Skipped {skipped_count} existing PR embeddings for {author.login}. Processing {len(new_pr_contents)} new PRs."
            )

        if not new_pr_contents:
            return skipped_count

        # Prepare pr_context for embedding (using only new PRs)
        pr_contexts = [pr.context or "" for pr in new_pr_contents]
        embeddings: list[list[float] | None] = []

        # Generate embeddings with fallback to local model if API fails
        try:
            valid_embeddings = self.generate_embeddings(
                pr_contexts,
                prompt_name=settings.GITHUB_DOCUMENT_PROMPT_NAME,
            )
            embeddings = cast(list[list[float] | None], valid_embeddings)
        except Exception as e:
            logger.warning(
                f"Batch embedding failed for {author.login}, processing individually: {str(e)}"
            )
            embeddings = []
            for i, doc in enumerate(pr_contexts):
                try:
                    single_embedding = self.generate_embeddings(
                        [doc],
                        prompt_name=settings.GITHUB_DOCUMENT_PROMPT_NAME,
                    )[0]
                    embeddings.append(single_embedding)
                except Exception:
                    logger.warning(
                        f"Initial embedding failed for PR {new_pr_contents[i].number}. Retrying with shorter text..."
                    )
                    try:
                        # Try very aggressive truncation as last resort (1000 chars)
                        short_doc = doc[:1000] + "... [truncated]"
                        single_embedding = self.generate_embeddings(
                            [short_doc],
                            prompt_name=settings.GITHUB_DOCUMENT_PROMPT_NAME,
                        )[0]
                        embeddings.append(single_embedding)
                        logger.info(
                            f"Successfully embedded truncated version of PR {new_pr_contents[i].number}"
                        )
                    except Exception:
                        # Emergency fallback - use minimal text (title) to ensure we get a vector
                        try:
                            logger.info(
                                f"Attempting emergency fallback for PR {new_pr_contents[i].number} using title only"
                            )
                            minimal_doc = f"PR: {new_pr_contents[i].title}"
                            minimal_doc = self._clean_text_for_embedding(minimal_doc)
                            single_embedding = self.generate_embeddings(
                                [minimal_doc],
                                prompt_name=settings.GITHUB_DOCUMENT_PROMPT_NAME,
                            )[0]
                            embeddings.append(single_embedding)
                            logger.info(
                                f"Successfully used minimal fallback for PR {new_pr_contents[i].number}"
                            )
                        except Exception as final_error:
                            logger.error(
                                f"Final failure to embed PR {new_pr_contents[i].number} for {author.login}: {str(final_error)}"
                            )
                            embeddings.append(None)

        success_count = 0
        # Store in database
        for pr, embedding in zip(new_pr_contents, embeddings, strict=False):
            if embedding is None:
                continue

            try:
                # We already know these are new, so just create
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

                success_count += 1

            except Exception as e:
                logger.error(f"Error storing PR {pr.number}: {str(e)}")
                self.db.rollback()
                continue

        self.db.commit()
        logger.info(f"Stored {success_count} new PR vectors for {author.login}")
        # Return total processed (skipped + newly stored) so the caller gets accurate "synced" count
        return success_count + skipped_count

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
                stored_count = self.store_pr_contexts(author, pr_contents)
                total_stored += stored_count

        logger.info(f"Total PRs stored: {total_stored}")
