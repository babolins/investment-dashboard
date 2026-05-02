"""
/api/rebalance — buy-guidance endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.config import load_config
from app.models.schemas import RebalanceAPIRequest, RebalanceResult
from app.services.rebalance import compute_rebalance

router = APIRouter(tags=["rebalance"])


@router.post("/rebalance", response_model=RebalanceResult)
def rebalance(body: RebalanceAPIRequest) -> RebalanceResult:
    """
    Compute buy guidance for VTI / VXUS / BND.

    The client must supply the AllocationBreakdown from the /api/upload
    response (it is stateless — no server-side session).
    """
    try:
        config = load_config()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Config error: {exc}") from exc

    return compute_rebalance(breakdown=body.to_breakdown(), request=body.to_request(), config=config)
