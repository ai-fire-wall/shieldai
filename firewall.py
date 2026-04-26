"""
Firewall — the central controller (v0.2).

Changes from v0.1:
  - Accepts an optional AsyncSession to persist every transaction to PostgreSQL.
  - Passes ml_score from input scan through to the log record.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.filters.input_filter import scan_input, ThreatLevel
from app.filters.output_filter import scan_output
from app.llm import call_llm, LLMResponse
from app.models.schemas import (
    FirewallRequest, FirewallResponse, BlockedResponse,
    ThreatInfo, OutputThreatInfo,
)
from app.utils.config import get_settings
from app.utils.logger import generate_request_id, log_request_event, log_error

settings = get_settings()
_BLOCKING_LEVELS = {ThreatLevel.HIGH, ThreatLevel.CRITICAL}


async def process_request(
    request: FirewallRequest,
    db_session: Optional[AsyncSession] = None,
) -> FirewallResponse | BlockedResponse:
    request_id = generate_request_id()
    t0 = time.perf_counter()

    # ── Stage 1: input scan ───────────────────────────────────────────────────
    input_result = scan_input(request.prompt)

    should_block = (
        input_result.threat_level in _BLOCKING_LEVELS and settings.block_on_high_threat
    ) or input_result.threat_level == ThreatLevel.CRITICAL

    if should_block:
        latency_ms = (time.perf_counter() - t0) * 1000
        await _persist(
            db_session, request_id=request_id, prompt_preview=request.prompt,
            provider=str(request.provider), model=request.model or "default",
            allowed=False, input_threat_level=str(input_result.threat_level),
            input_threats=input_result.threats_found,
            input_ml_score=input_result.ml_score,
            latency_ms=latency_ms, metadata=request.metadata,
        )
        log_request_event(
            request_id=request_id, prompt_preview=request.prompt,
            provider=str(request.provider), model=request.model or "default",
            allowed=False, input_threat_level=str(input_result.threat_level),
            input_threats=input_result.threats_found, latency_ms=latency_ms,
            metadata=request.metadata,
        )
        return BlockedResponse(
            request_id=request_id, reason=input_result.reason,
            threat_level=str(input_result.threat_level),
            threats_found=input_result.threats_found,
        )

    effective_prompt = input_result.sanitized_prompt or request.prompt

    # ── Stage 2: call the LLM ─────────────────────────────────────────────────
    try:
        llm_response: LLMResponse = await call_llm(
            prompt=effective_prompt, provider=request.provider,
            model=request.model, system_prompt=request.system_prompt,
        )
    except Exception as exc:
        log_error(request_id, exc)
        raise

    # ── Stage 3: output scan ──────────────────────────────────────────────────
    output_result = scan_output(llm_response.text, redact_pii=request.redact_pii)
    latency_ms = (time.perf_counter() - t0) * 1000

    await _persist(
        db_session, request_id=request_id, prompt_preview=request.prompt,
        provider=llm_response.provider, model=llm_response.model, allowed=True,
        input_threat_level=str(input_result.threat_level),
        input_threats=input_result.threats_found,
        input_ml_score=input_result.ml_score,
        output_threat_level=str(output_result.threat_level),
        output_issues=output_result.issues_found,
        latency_ms=latency_ms, metadata=request.metadata,
    )
    log_request_event(
        request_id=request_id, prompt_preview=request.prompt,
        provider=llm_response.provider, model=llm_response.model, allowed=True,
        input_threat_level=str(input_result.threat_level),
        input_threats=input_result.threats_found,
        output_threat_level=str(output_result.threat_level),
        output_issues=output_result.issues_found,
        latency_ms=latency_ms, metadata=request.metadata,
    )

    return FirewallResponse(
        request_id=request_id, allowed=True,
        response=output_result.sanitized_response,
        input_analysis=ThreatInfo(
            threat_level=str(input_result.threat_level),
            threats_found=input_result.threats_found,
            reason=input_result.reason,
        ),
        output_analysis=OutputThreatInfo(
            threat_level=str(output_result.threat_level),
            issues_found=output_result.issues_found,
            clean=output_result.clean,
        ),
        latency_ms=round(latency_ms, 2),
        provider=llm_response.provider,
        model=llm_response.model,
    )


async def _persist(
    session: Optional[AsyncSession],
    **kwargs: Any,
) -> None:
    """Write to DB if a session is available. Never raises — logs are non-critical."""
    if session is None or not settings.log_to_db:
        return
    try:
        from app.db.repository import save_log
        await save_log(session, **kwargs)
    except Exception as exc:
        from app.utils.logger import get_logger
        get_logger("firewall").error(f"Log persist failed: {exc}")
