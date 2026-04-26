"""
Input Filter — scans user prompts before they reach the LLM.
Detects: sensitive data patterns, prompt injection attempts, banned topics.
"""

import re
from dataclasses import dataclass, field
from enum import Enum


class ThreatLevel(str, Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class FilterResult:
    allowed: bool
    threat_level: ThreatLevel
    threats_found: list[str] = field(default_factory=list)
    sanitized_prompt: str = ""
    reason: str = ""
    ml_score: float | None = None


# ── Sensitive data patterns ────────────────────────────────────────────────────

SENSITIVE_PATTERNS: dict[str, re.Pattern] = {
    "api_key":        re.compile(r"(?i)(sk-|pk-|api[_-]?key)[a-zA-Z0-9\-_]{16,}"),
    "aws_key":        re.compile(r"(?i)AKIA[0-9A-Z]{16}"),
    "password_field": re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"),
    "jwt_token":      re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}"),
    "credit_card":    re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "ssn":            re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "private_key":    re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
    "email_password": re.compile(r"(?i)my (email|gmail|yahoo).{0,30}(password|pass) (is|:)\s*\S+"),
    "connection_str": re.compile(r"(?i)(mongodb|postgresql|mysql|redis):\/\/[^\s]+:[^\s]+@"),
}

# ── Prompt injection signatures ────────────────────────────────────────────────

INJECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ignore_instructions",   re.compile(r"(?i)ignore (all )?(previous|prior|above) instructions?")),
    ("jailbreak_dan",         re.compile(r"(?i)\bDAN\b.{0,60}(mode|persona|now)")),
    ("jailbreak_pretend",     re.compile(r"(?i)pretend (you are|to be) (an? )?(unfiltered|unrestricted|evil|malicious)")),
    ("override_system",       re.compile(r"(?i)(override|bypass|disable).{0,40}(safety|filter|restriction|guideline|rule)")),
    ("reveal_system_prompt",  re.compile(r"(?i)(print|show|reveal|repeat|output).{0,30}(system prompt|instructions?|config)")),
    ("role_play_escape",      re.compile(r"(?i)you are now (an? )?(ai without|unrestricted|jailbroken)")),
    ("hidden_instruction",    re.compile(r"(?i)<\s*(system|hidden|secret|inject)\s*>.*?<\s*/\s*(system|hidden|secret|inject)\s*>", re.DOTALL)),
    ("exfil_attempt",         re.compile(r"(?i)(send|post|http|curl|fetch|exfiltrate).{0,60}(password|secret|key|token)")),
    ("token_manipulation",    re.compile(r"(?i)\[\s*(INST|SYS|SYSTEM|END)\s*\]")),
]

# ── Banned content categories ──────────────────────────────────────────────────

BANNED_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("weapons_synthesis",  re.compile(r"(?i)how (to|do I) (make|create|synthesize|build).{0,30}(bomb|explosive|weapon|malware|virus)")),
    ("credential_request", re.compile(r"(?i)(give|tell|show|provide).{0,20}(all )?(passwords?|credentials?|secrets?|keys?)")),
    ("data_dump",          re.compile(r"(?i)(dump|extract|export|list).{0,30}(all |every )?(user|customer|employee).{0,20}(data|record|info)")),
]


def scan_input(prompt: str, use_ml: bool = True) -> FilterResult:
    """
    Run all checks on a user prompt.
    Returns a FilterResult describing whether to allow the prompt.
    """
    threats: list[str] = []
    max_level = ThreatLevel.SAFE

    def escalate(level: ThreatLevel) -> None:
        nonlocal max_level
        order = [ThreatLevel.SAFE, ThreatLevel.LOW, ThreatLevel.MEDIUM,
                 ThreatLevel.HIGH, ThreatLevel.CRITICAL]
        if order.index(level) > order.index(max_level):
            max_level = level

    # 1. Sensitive data check
    for label, pattern in SENSITIVE_PATTERNS.items():
        if pattern.search(prompt):
            threats.append(f"sensitive_data:{label}")
            escalate(ThreatLevel.HIGH)

    # 2. Prompt injection check
    for label, pattern in INJECTION_PATTERNS:
        if pattern.search(prompt):
            threats.append(f"injection:{label}")
            escalate(ThreatLevel.CRITICAL)

    # 3. Banned content check
    for label, pattern in BANNED_PATTERNS:
        if pattern.search(prompt):
            threats.append(f"banned:{label}")
            escalate(ThreatLevel.CRITICAL)

    # 4. ML classifier — catches novel paraphrases regex misses
    ml_score: float | None = None
    if use_ml:
        try:
            from app.ml.classifier import get_classifier
            ml_result = get_classifier().predict(prompt)
            ml_score = ml_result.confidence
            if ml_result.is_injection and max_level not in (ThreatLevel.CRITICAL,):
                if ml_result.confidence >= 0.80:
                    threats.append(f"ml:injection_high({ml_result.confidence:.2f})")
                    escalate(ThreatLevel.CRITICAL)
                elif ml_result.confidence >= 0.55:
                    threats.append(f"ml:injection_medium({ml_result.confidence:.2f})")
                    escalate(ThreatLevel.HIGH)
        except Exception:
            pass  # ML unavailable — regex layer still protects

    allowed = max_level not in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)

    # Sanitize: mask secrets even in allowed prompts (MEDIUM/LOW)
    sanitized = _mask_sensitive(prompt) if threats else prompt

    reason = (
        f"Blocked due to: {', '.join(threats)}"
        if not allowed
        else ("Passed with warnings" if threats else "Clean")
    )

    return FilterResult(
        allowed=allowed,
        threat_level=max_level,
        threats_found=threats,
        sanitized_prompt=sanitized,
        reason=reason,
        ml_score=ml_score,
    )


def _mask_sensitive(text: str) -> str:
    """Replace recognized secrets with redaction placeholders."""
    for label, pattern in SENSITIVE_PATTERNS.items():
        text = pattern.sub(f"[REDACTED:{label.upper()}]", text)
    return text
