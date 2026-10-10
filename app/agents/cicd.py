from langchain_core.tools import tool

from app.agents.base import build_worker

CICD_PROMPT = (
    "You are the CI/CD sub-agent in a multi-agent dev platform. "
    "Trigger pipelines and deploy release channels by calling your tools. "
    "Never deploy to 'prod' without explicit human approval, per the deploy tool."
)


@tool
def trigger_pipeline(branch: str) -> str:
    """Trigger a CI/CD pipeline for BRANCH and return its run id/status.
    STUB: wire to your CI system (GitHub Actions, Jenkins, Tekton, ...)."""
    return f"[cicd-stub] pipeline for {branch}: queued"


@tool
def deploy_to_k8s(channel: str) -> str:
    """Deploy a build to a Kubernetes channel: dev|staging|prod.
    STUB: wire to 'kubectl apply -f release.yaml'. PROD requires approval."""
    if channel.strip().lower() == "prod":
        return "[cicd-stub] PROD deploy BLOCKED: requires human approval"
    return f"[cicd-stub] deployed to channel '{channel}'"


def build_cicd_agent():
    """The CI/CD sub-agent: pipelines and safe-channel deploys."""
    return build_worker(prompt=CICD_PROMPT, tools=[trigger_pipeline, deploy_to_k8s])
