from fastapi import APIRouter, Request, HTTPException
from app.api.integrations.GitHub.github_model import GithubOrgIntBaseModel
from app.core.config import settings
import hmac
import hashlib
from app.utils.deps import SessionDep

router = APIRouter(prefix="/github", tags=["github"])

@router.post("/webhook")
async def github_webhook(request: Request, session: SessionDep):
    # 1. Verify Signature (Security)
    signature = request.headers.get("X-Hub-Signature-256")
    body = await request.body()
    
    mac = hmac.new(
        key=settings.GITHUB_WEBHOOK_SECRET.encode(), 
        msg=body, 
        digestmod=hashlib.sha256
    )
    expected_signature = "sha256=" + mac.hexdigest()
    
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # 2. Process Data
    payload = await request.json()
    action = payload.get("action")
    
    if action == "created" and "installation" in payload:
        install_id = payload["installation"]["id"]
        org_name = payload["installation"]["account"]["login"]
        print(f"SUCCESS: Linked Organization '{org_name}' with ID {install_id}")
        
        integration = session.query(GithubOrgIntBaseModel).first()
        if not integration:
            integration = GithubOrgIntBaseModel(org_name=org_name)
            session.add(integration)

        integration.github_install_id = str(install_id)
        session.commit()
        return {"status": "ok"}
    return {"status": "ignored"}