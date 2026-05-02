"""
/api/holdings — CSV upload and portfolio table endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.config import load_config
from app.models.schemas import AllocationBreakdown, PortfolioSnapshot
from app.services.allocation import compute_allocation
from app.services.csv_parser import parse_fidelity_csv

router = APIRouter(tags=["holdings"])

_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB guard


@router.post("/upload", response_model=dict)
async def upload_portfolio(file: UploadFile = File(...)) -> dict:
    """
    Upload a Fidelity positions CSV.

    Returns the parsed holdings table and current allocation breakdown
    in a single response so the frontend only needs one round-trip.
    """
    if file.content_type and "csv" not in file.content_type and "text" not in file.content_type:
        raise HTTPException(
            status_code=415,
            detail="Expected a CSV file. Received content-type: " + (file.content_type or "unknown"),
        )

    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {_MAX_UPLOAD_BYTES // 1024} KB.",
        )

    try:
        snapshot: PortfolioSnapshot = parse_fidelity_csv(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        config = load_config()
        breakdown: AllocationBreakdown = compute_allocation(snapshot, config)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Config error: {exc}") from exc

    return {
        "portfolio": snapshot.model_dump(),
        "allocation": breakdown.model_dump(),
    }
