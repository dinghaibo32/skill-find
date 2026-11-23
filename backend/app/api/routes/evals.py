"""Routing eval endpoints: run on demand, read cached results."""

from fastapi import APIRouter, Depends, HTTPException

from app.services.llm.base import LLMError, LLMNotConfiguredError
from app.services.skills.evals import EvalReport, EvalService, EvalSummary, get_eval_service

router = APIRouter(tags=["evals"])


@router.post("/evals/run", response_model=EvalReport)
async def run_evals(service: EvalService = Depends(get_eval_service)) -> EvalReport:
    """Run the eval suite and return the fresh report."""
    # LLM errors are folded into per-row errors by the service; this guard only
    # protects future calls outside the row loop.
    try:
        return await service.run()
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/evals/results", response_model=EvalReport)
async def get_eval_results(service: EvalService = Depends(get_eval_service)) -> EvalReport:
    """Return the last cached eval report, or an empty one if none exists."""
    if service.last_report is None:
        return EvalReport(
            results=[], summary=EvalSummary(total=0, passed=0, accuracy=0.0, by_category={})
        )
    return service.last_report
