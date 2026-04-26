"""
Output Filter — sanitizes LLM responses before they reach the user.
Detects: leaked secrets, harmful content, PII, hallucinated credentials.
"""

import re
from dataclasses import dataclass, field
from app.filters.input_filter import ThreatLevel, SENSITIVE_PATTERNS


@dataclass
class OutputFilterResult:
    clean: bool
    threat_level: ThreatLevel
    issues_found: list[str] = field(default_factory=list)
    sanitized_response: str = ""
    original_length: int = 0
    sanitized_length: int = 0


# ── Patterns that should never appear in an LLM response ──────────────────────

HARMFUL_OUTPUT_PATTERNS: list[tuple[str, re.Pattern, ThreatLevel]] = [
    # Credential leakage
    ("leaked_api_key",     re.compile(r"(?i)(sk-|pk-|api[_-]?key)[a-zA-Z0-9\-_]{16,}"),   ThreatLevel.CRITICAL),
    ("leaked_aws_key",     re.compile(r"AKIA[0-9A-Z]{16}"),                                  ThreatLevel.CRITICAL),
    ("leaked_jwt",         re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}"),        ThreatLevel.CRITICAL),
    ("leaked_private_key", re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),             ThreatLevel.CRITICAL),
    ("leaked_connection",  re.compile(r"(?i)(mongodb|postgresql|mysql|redis):\/\/[^\s]+:[^\s]+@"), ThreatLevel.CRITICAL),

    # PII patterns
    ("pii_ssn",            re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                             ThreatLevel.HIGH),
    ("pii_credit_card",    re.compile(r"\b(?:\d[ -]?){13,16}\b"),                            ThreatLevel.HIGH),
    ("pii_email_password", re.compile(r"(?i)password.{0,30}:\s*\S{6,}"),                     ThreatLevel.HIGH),

    # Harmful instructions
    ("malware_code",       re.compile(r"(?i)(import os|subprocess|eval\(|exec\().{0,100}(rm -rf|del /|format c:)", re.DOTALL), ThreatLevel.CRITICAL),
    ("sql_injection_help", re.compile(r"(?i)(union select|drop table|insert into).{0,60}(--|\#|;)"), ThreatLevel.HIGH),
    ("bomb_instructions",  re.compile(r"(?i)step.{0,20}(1|one).{0,60}(explosive|detonate|fuse|trigger)"), ThreatLevel.CRITICAL),

    # Jailbreak confirmation
    ("jailbreak_confirm",  re.compile(r"(?i)(I am now DAN|jailbreak successful|safety (disabled|bypassed)|as an AI without restrictions)"), ThreatLevel.CRITICAL),
]

# ── PII redaction helpers ──────────────────────────────────────────────────────

PII_REDACTION: list[tuple[str, re.Pattern, str]] = [
    ("email",   re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[REDACTED:EMAIL]"),
    ("phone_us",re.compile(r"\b(\+1[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),  "[REDACTED:PHONE]"),
    ("ip_addr", re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b"),                             "[REDACTED:IP]"),
]


def scan_output(response: str, redact_pii: bool = True) -> OutputFilterResult:
    """
    Scan and optionally sanitize an LLM response.

    Args:
        response: Raw text from the LLM.
        redact_pii: If True, redact detected PII from the response.

    Returns:
        OutputFilterResult with sanitized text and threat metadata.
    """
    issues: list[str] = []
    max_level = ThreatLevel.SAFE
    sanitized = response

    def escalate(level: ThreatLevel) -> None:
        nonlocal max_level
        order = [ThreatLevel.SAFE, ThreatLevel.LOW, ThreatLevel.MEDIUM,
                 ThreatLevel.HIGH, ThreatLevel.CRITICAL]
        if order.index(level) > order.index(max_level):
            max_level = level

    # 1. Check for harmful patterns and redact them
    for label, pattern, level in HARMFUL_OUTPUT_PATTERNS:
        if pattern.search(sanitized):
            issues.append(f"output:{label}")
            escalate(level)
            sanitized = pattern.sub(f"[BLOCKED:{label.upper()}]", sanitized)

    # 2. Check for sensitive data using shared patterns from input_filter
    for label, pattern in SENSITIVE_PATTERNS.items():
        if pattern.search(sanitized):
            issues.append(f"leaked_secret:{label}")
            escalate(ThreatLevel.CRITICAL)
            sanitized = pattern.sub(f"[REDACTED:{label.upper()}]", sanitized)

    # 3. Optional PII redaction
    if redact_pii:
        for label, pattern, placeholder in PII_REDACTION:
            if pattern.search(sanitized):
                issues.append(f"pii:{label}")
                escalate(ThreatLevel.MEDIUM)
                sanitized = pattern.sub(placeholder, sanitized)

    clean = max_level in (ThreatLevel.SAFE, ThreatLevel.LOW)

    return OutputFilterResult(
        clean=clean,
        threat_level=max_level,
        issues_found=issues,
        sanitized_response=sanitized,
        original_length=len(response),
        sanitized_length=len(sanitized),
    )
