"""
Pydantic schemas for request/response validation.
"""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MOCK = "mock"          # for testing without a live API key


# ── Inbound ───────────────────────────────────────────────────────────────────

class FirewallRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=32_000, description="User prompt to be checked and forwarded.")
    provider: LLMProvider = Field(LLMProvider.OPENAI, description="Target LLM provider.")
    model: Optional[str] = Field(None, description="Specific model name (e.g. gpt-4o). Provider default used if omitted.")
    system_prompt: Optional[str] = Field(None, description="Optional system prompt to prepend.")
    redact_pii: bool = Field(True, description="Whether to redact PII from the LLM response.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary caller metadata stored in logs.")


# ── Threat information ────────────────────────────────────────────────────────

class ThreatInfo(BaseModel):
    threat_level: str
    threats_found: list[str]
    reason: str


class OutputThreatInfo(BaseModel):
    threat_level: str
    issues_found: list[str]
    clean: bool


# ── Outbound ──────────────────────────────────────────────────────────────────

class FirewallResponse(BaseModel):
    request_id: str
    allowed: bool
    response: Optional[str] = None          # None when blocked at input stage
    input_analysis: ThreatInfo
    output_analysis: Optional[OutputThreatInfo] = None
    latency_ms: float
    provider: str
    model: str


class BlockedResponse(BaseModel):
    request_id: str
    allowed: bool = False
    reason: str
    threat_level: str
    threats_found: list[str]


# ── Health check ──────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    filters: list[str]
