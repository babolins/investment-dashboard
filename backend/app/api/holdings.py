"""
/api/upload and /api/allocation: CSV upload and grouping a portfolio into categories.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.deps import ConfigDep
from app.models.schemas import AllocationBreakdown, PortfolioSnapshot, UploadResponse
from app.services.allocation import compute_allocation
from app.services.csv_parser import parse_fidelity_csv

router = APIRouter(tags=["holdings"])

_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB guard


@router.post("/upload", response_model=UploadResponse)
async def upload_portfolio(config: ConfigDep, file: UploadFile = File(...)) -> UploadResponse:
    """
    Upload a Fidelity positions CSV.

    Returns the parsed holdings table and current allocation breakdown
    in a single response so the frontend only needs one round-trip.
    """
    if file.content_type and "csv" not in file.content_type and "text" not in file.content_type:
        raise HTTPException(
            status_code=415,
            detail="Expected a CSV file. Received content-type: "
            + (file.content_type or "unknown"),
        )

    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {_MAX_UPLOAD_BYTES // 1024} KB.",
        )

    try:
        snapshot = parse_fidelity_csv(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    breakdown = compute_allocation(snapshot, config)
    return UploadResponse(portfolio=snapshot, allocation=breakdown)


@router.post("/allocation", response_model=AllocationBreakdown)
def allocation(portfolio: PortfolioSnapshot, config: ConfigDep) -> AllocationBreakdown:
    """
    Re-group an already parsed portfolio with the current config.

    Lets the UI refresh the breakdown after categories or assignments change
    without uploading the CSV again.
    """
    return compute_allocation(portfolio, config)
