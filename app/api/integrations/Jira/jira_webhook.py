"""Jira webhook endpoint for real-time updates."""

import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.api.integrations.Jira.jira_service import JiraIntegrationService
from app.core.config import settings
from app.utils.deps import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jira", tags=["jira"])


def verify_jira_webhook(request_body: bytes, signature: str | None) -> bool:
    """
    Verify Jira webhook signature.
    Note: Jira Cloud webhooks don't have a built-in signature mechanism like GitHub.
    You can configure a secret in your webhook URL or use IP allowlisting.
    This implementation supports an optional secret-based verification.
    """
    if not settings.JIRA_WEBHOOK_SECRET:
        # If no secret configured, skip verification (not recommended for production)
        logger.warning(
            "JIRA_WEBHOOK_SECRET not configured - skipping signature verification"
        )
        return True

    if not signature:
        return False

    # Calculate expected signature
    mac = hmac.new(
        key=settings.JIRA_WEBHOOK_SECRET.encode(),
        msg=request_body,
        digestmod=hashlib.sha256,
    )
    expected_signature = mac.hexdigest()

    return hmac.compare_digest(signature, expected_signature)


@router.post("/webhook")
async def jira_webhook(request: Request, session: SessionDep) -> dict[str, Any]:
    """
    Webhook endpoint for receiving real-time updates from Jira.
    Satisfies the optional real-time sync requirement.

    Jira webhook events:
    - jira:issue_created
    - jira:issue_updated
    - jira:issue_deleted
    - comment_created
    - comment_updated
    - comment_deleted
    - sprint_created
    - sprint_updated
    - sprint_closed
    - sprint_deleted
    - sprint_started

    To configure this webhook in Jira:
    1. Go to Jira Settings > System > Webhooks
    2. Create a new webhook with URL: https://your-domain.com/api/v1/jira/webhook
    3. Select the events you want to receive
    4. Optionally add a secret to the URL for verification
    """
    # Get request body
    body = await request.body()

    # Verify signature if configured
    signature = request.headers.get("X-Jira-Signature")
    if not verify_jira_webhook(body, signature):
        logger.warning("Invalid Jira webhook signature")
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse Jira webhook payload: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Extract event type
    webhook_event = payload.get("webhookEvent", "unknown")
    logger.info(f"Received Jira webhook event: {webhook_event}")

    try:
        jira_service = JiraIntegrationService(session)

        # Process the event
        if webhook_event in ["jira:issue_created", "jira:issue_updated"]:
            result = jira_service.process_webhook_event(webhook_event, payload)
            return {
                "status": "processed",
                "event": webhook_event,
                **result,
            }

        elif webhook_event == "jira:issue_deleted":
            result = jira_service.process_webhook_event(webhook_event, payload)
            return {
                "status": "processed",
                "event": webhook_event,
                **result,
            }

        elif webhook_event in ["comment_created", "comment_updated"]:
            # Re-sync the issue to update comments
            issue_data = payload.get("issue")
            if issue_data:
                issue_key = issue_data.get("key")
                if issue_key:
                    client = jira_service.get_jira_client()
                    issue = client.issue(issue_key)
                    issue_content = jira_service._parse_issue(issue)
                    jira_service._store_issue(issue_content)
                    session.commit()
                    return {
                        "status": "processed",
                        "event": webhook_event,
                        "issue_key": issue_key,
                    }

            return {
                "status": "ignored",
                "event": webhook_event,
                "reason": "no issue data",
            }

        elif webhook_event.startswith("sprint_"):
            # Sprint events - could trigger a full sync or specific handling
            logger.info(f"Sprint event received: {webhook_event}")
            return {
                "status": "acknowledged",
                "event": webhook_event,
                "message": "Sprint events are logged but not processed individually",
            }

        elif webhook_event == "user_created" or webhook_event == "user_updated":
            # User events - could update developer profiles
            user_data = payload.get("user")
            if user_data:
                from datetime import datetime

                from app.api.integrations.Jira.jira_model import DeveloperProfile

                account_id = user_data.get("accountId")
                display_name = user_data.get("displayName")
                email = user_data.get("emailAddress")

                if account_id:
                    from typing import cast

                    profile = (
                        session.query(DeveloperProfile)
                        .filter(
                            cast(Any, DeveloperProfile.jira_account_id == account_id)
                        )
                        .first()
                    )

                    if profile:
                        profile.jira_display_name = display_name
                        profile.jira_email = email
                        profile.updated_at = datetime.utcnow()
                    else:
                        profile = DeveloperProfile(
                            jira_account_id=account_id,
                            jira_display_name=display_name,
                            jira_email=email,
                        )
                        session.add(profile)

                    session.commit()
                    return {
                        "status": "processed",
                        "event": webhook_event,
                        "account_id": account_id,
                    }

            return {
                "status": "ignored",
                "event": webhook_event,
                "reason": "no user data",
            }

        else:
            # Unknown or unhandled event
            logger.info(f"Unhandled Jira webhook event: {webhook_event}")
            return {
                "status": "ignored",
                "event": webhook_event,
                "reason": "event type not handled",
            }

    except Exception as e:
        logger.error(f"Error processing Jira webhook: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to process webhook: {str(e)}"
        )


@router.get("/webhook/test")
async def test_webhook_endpoint() -> dict[str, str]:
    """
    Test endpoint to verify webhook URL is accessible.
    Jira may call this with GET to verify the URL.
    """
    return {
        "status": "ok",
        "message": "Jira webhook endpoint is active",
    }
