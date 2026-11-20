from fastapi import APIRouter

from app.providers.catalog import list_providers

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


@router.get("")
def providers() -> dict:
    """Verified provider catalog and setup metadata.

    No credentials or runtime state are included here; connections are
    returned by ``/api/v1/provider-connections``.
    """
    return {"items": list_providers()}
