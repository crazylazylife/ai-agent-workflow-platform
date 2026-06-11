"""/models endpoint — exposes the configured LLM provider + selectable models for the UI."""
from fastapi import APIRouter

from awp_shared.config import shared_settings

router = APIRouter(tags=["models"])


@router.get("/models")
def list_models():
    return {
        "provider": shared_settings.llm_provider,
        "default": shared_settings.llm_model,
        "models": shared_settings.llm_model_list,
    }
