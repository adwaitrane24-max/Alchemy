"""Rule-based security scanner.

Detects prompt injection, jailbreak attempts, and prompt/secret leakage using
regular expressions and keyword matching only. No model is ever invoked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger

from backend.app.constants.enums import SecurityStatus, ThreatType
from backend.app.models.analysis import SecurityResult
from backend.app.models.request import PromptRequest


@dataclass(frozen=True)
class _Rule:
    """A single compiled detection rule."""

    rule_id: str
    threat: ThreatType
    pattern: re.Pattern[str]
    description: str


def _rule(rule_id: str, threat: ThreatType, regex: str, description: str) -> _Rule:
    """Compile a case-insensitive detection rule."""
    return _Rule(rule_id, threat, re.compile(regex, re.IGNORECASE), description)


# Detection rules grouped by threat category. Patterns intentionally favor
# recall for known attack phrasings while staying cheap to evaluate.
_RULES: tuple[_Rule, ...] = (
    # ── Prompt injection / instruction override ──
    _rule(
        "INJ-001",
        ThreatType.INJECTION,
        r"\bignore\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above)\s+instructions?\b",
        "Ignore previous instructions",
    ),
    _rule(
        "INJ-002",
        ThreatType.INJECTION,
        r"\bdisregard\s+(?:all\s+)?(?:previous|prior|the\s+above)\b",
        "Disregard previous instructions",
    ),
    _rule(
        "INJ-003",
        ThreatType.INJECTION,
        r"\bforget\s+(?:everything|all\s+(?:previous|prior))\b",
        "Forget previous context",
    ),
    _rule(
        "INJ-004",
        ThreatType.ROLE_OVERRIDE,
        r"\byou\s+are\s+now\s+(?:a|an|in)\b",
        "Role reassignment",
    ),
    _rule(
        "INJ-005",
        ThreatType.ROLE_OVERRIDE,
        r"\bnew\s+(?:instructions?|rules?|system\s+prompt)\b",
        "New instruction injection",
    ),
    # ── Jailbreak ──
    _rule(
        "JB-001",
        ThreatType.JAILBREAK,
        r"\b(?:dan\s+mode|do\s+anything\s+now)\b",
        "DAN-style jailbreak",
    ),
    _rule("JB-002", ThreatType.JAILBREAK, r"\bdeveloper\s+mode\b", "Developer-mode jailbreak"),
    _rule(
        "JB-003",
        ThreatType.JAILBREAK,
        r"\bpretend\s+(?:you\s+(?:are|have\s+no)|to\s+have\s+no)\b",
        "Pretend-no-restrictions jailbreak",
    ),
    _rule(
        "JB-004",
        ThreatType.JAILBREAK,
        r"\b(?:no|without)\s+(?:restrictions?|filters?|rules?|guidelines?|limitations?)\b",
        "Restriction-removal jailbreak",
    ),
    _rule("JB-005", ThreatType.JAILBREAK, r"\bjailbreak\b", "Explicit jailbreak keyword"),
    # ── Prompt / secret leakage ──
    _rule(
        "LEAK-001",
        ThreatType.LEAKAGE,
        r"\b(?:reveal|show|print|repeat|tell\s+me)\s+(?:your|the)\s+system\s+prompt\b",
        "System prompt extraction",
    ),
    _rule(
        "LEAK-002",
        ThreatType.LEAKAGE,
        r"\bwhat\s+(?:are|were)\s+your\s+(?:original\s+)?instructions?\b",
        "Instruction extraction",
    ),
    _rule(
        "LEAK-003",
        ThreatType.EXFILTRATION,
        r"\b(?:api[_\s-]?key|secret\s+key|password|access\s+token|credentials?)\b",
        "Secret/credential exfiltration",
    ),
    _rule(
        "LEAK-004",
        ThreatType.LEAKAGE,
        r"\brepeat\s+(?:everything\s+)?(?:above|the\s+text\s+above)\b",
        "Context dump request",
    ),
    # ── Harmful content: weapons & explosives ──
    _rule(
        "HARM-001",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:(?:how\s+to|ways?\s+to|steps?\s+to|guide\s+(?:to|for|on)|explain(?:\s+(?:how|in\s+detail))?|teach\s+(?:me|us)?|tell\s+(?:me|us)?\s+how|instructions?\s+(?:to|for|on))\s+)?(?:make|build|create|construct|assemble|manufacture|craft|produce|synthesize)\s+(?:a\s+)?(?:deadly\s+|lethal\s+|powerful\s+|homemade\s+|improvised\s+)?(?:bomb|explosive|grenade|landmine|ied|detonator|dynamite|c4|molotov|pipe\s*bomb|nail\s*bomb|car\s*bomb|suicide\s*vest|weapon\s*of\s*mass\s*destruction)\b",
        "Weapon/explosive creation instructions",
    ),
    _rule(
        "HARM-001b",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:bomb|explosive|grenade|landmine|ied|detonator|dynamite|c4|molotov|pipe\s*bomb|nail\s*bomb|car\s*bomb|suicide\s*vest)\s+(?:making|building|creation|construction|recipe|tutorial|instructions?|guide|blueprint|schematic)\b",
        "Weapon/explosive creation (reversed phrasing)",
    ),
    _rule(
        "HARM-002",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:(?:how|ways?|steps?|guide|explain|teach|instructions?)\s+(?:to\s+|for\s+|on\s+)?)?(?:make|build|create|buy|obtain|get|acquire|purchase|synthesize|cook|produce|3d\s*print)\s+(?:a\s+)?(?:illegal\s+|homemade\s+|improvised\s+|untraceable\s+)?(?:gun|firearm|pistol|rifle|assault\s*weapon|machine\s*gun|shotgun|silencer|suppressor|3d\s*printed\s*gun|ghost\s*gun|zip\s*gun)\b",
        "Firearm creation/acquisition instructions",
    ),
    _rule(
        "HARM-003",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:(?:how|ways?|steps?|guide|explain|teach|instructions?)\s+(?:to\s+|for\s+|on\s+)?)?(?:make|create|synthesize|cook|produce|brew|manufacture)\s+(?:a\s+)?(?:deadly\s+|lethal\s+|homemade\s+)?(?:poison|toxic\s*(?:gas|substance|chemical)|nerve\s*(?:agent|gas)|ricin|cyanide|sarin|anthrax|mustard\s*gas|chlorine\s*gas|vx\s*gas)\b",
        "Poison/chemical weapon synthesis",
    ),
    # ── Harmful content: drugs ──
    _rule(
        "HARM-004",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:(?:how|ways?|steps?|guide|explain|teach|instructions?)\s+(?:to\s+|for\s+|on\s+)?)?(?:make|cook|synthesize|produce|manufacture|brew|create)\s+(?:a\s+)?(?:meth|methamphetamine|crystal\s*meth|cocaine|crack|heroin|fentanyl|lsd|mdma|ecstasy|dmt|ghb|ketamine|pcp)\b",
        "Illegal drug manufacturing",
    ),
    # ── Harmful content: violence & harm ──
    _rule(
        "HARM-005",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:(?:how|ways?|steps?|best\s+way|methods?)\s+(?:to\s+)?)?(?:kill|murder|assassinate|eliminate|execute|strangle|suffocate|poison)\s+(?:a\s+)?(?:person|someone|people|human|man|woman|child|kid|infant|baby|neighbor|neighbour|colleague|boss|teacher|classmate|spouse|partner|friend|family)\b",
        "Violence against persons",
    ),
    _rule(
        "HARM-006",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:(?:how|ways?|steps?)\s+(?:to\s+)?)?(?:kidnap|abduct|traffic|torture|dismember|mutilate)\s+(?:a\s+)?(?:person|someone|people|child|kid|woman|man|victim)\b",
        "Kidnapping/torture instructions",
    ),
    _rule(
        "HARM-006b",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:(?:how|ways?|steps?)\s+(?:to\s+)?)?(?:kidnap|abduct|torture|dismember|mutilate)\b.*\b(?:without\s+(?:getting\s+caught|being\s+(?:caught|detected|found|noticed|traced)))\b",
        "Evasion of law enforcement",
    ),
    _rule(
        "HARM-007",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:(?:how|ways?|steps?|plan|guide)\s+(?:to\s+|for\s+)?)?(?:commit|plan|carry\s*out|execute|organize|stage)\s+(?:a\s+)?(?:mass\s*shooting|school\s*shooting|terrorist?\s*attack|bombing|genocide|massacre|arson|hate\s*crime)\b",
        "Terrorism/mass violence planning",
    ),
    # ── Harmful content: hacking & cybercrime ──
    _rule(
        "HARM-008",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:how\s+to\s+)?(?:hack\s+into|break\s+into|crack|exploit|breach)\s+(?:a\s+)?(?:bank|government|military|hospital|school|company|someone'?s?\s+(?:account|email|phone|computer|social\s*media))\b",
        "Unauthorized system access",
    ),
    _rule(
        "HARM-009",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:how\s+to\s+)?(?:create|write|build|deploy|spread)\s+(?:a\s+)?(?:ransomware|malware|virus|trojan|worm|keylogger|spyware|rootkit|botnet|rat\s+(?:tool|software))\b",
        "Malware creation",
    ),
    # ── Harmful content: self-harm ──
    _rule(
        "HARM-010",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:how\s+to\s+)?(?:commit\s+suicide|kill\s+(?:myself|yourself)|end\s+(?:my|your)\s+life|painless\s+(?:way|method)\s+to\s+die|best\s+way\s+to\s+die)\b",
        "Self-harm/suicide instructions",
    ),
    # ── Harmful content: CSAM & exploitation ──
    _rule(
        "HARM-011",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:child\s+(?:porn|pornography|exploitation|abuse\s+(?:material|image|video))|csam|underage\s+(?:sex|porn|nude)|minor\s+(?:sex|porn|nude))\b",
        "Child exploitation material",
    ),
    # ── Harmful content: fraud & identity theft ──
    _rule(
        "HARM-012",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:how\s+to\s+)?(?:forge|fake|counterfeit|falsify)\s+(?:a\s+)?(?:passport|id|identity|license|document|money|currency|diploma|certificate|prescription)\b",
        "Document forgery/counterfeiting",
    ),
    _rule(
        "HARM-013",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:how\s+to\s+)?(?:steal|clone|skim)\s+(?:a\s+)?(?:credit\s*card|debit\s*card|identity|someone'?s?\s+identity)\b",
        "Identity theft/card fraud",
    ),
    # ── Harmful content: human trafficking ──
    _rule(
        "HARM-014",
        ThreatType.HARMFUL_CONTENT,
        r"\b(?:how\s+to\s+)?(?:traffic|smuggle|sell)\s+(?:a\s+)?(?:person|people|human|organ|slave|child|children|women|girls|boys)\b",
        "Human trafficking",
    ),
)


class SecurityScanner:
    """Scans prompts for injection, jailbreak, and leakage attempts."""

    def __init__(self, log_blocked: bool = True) -> None:
        """Create a scanner.

        Args:
            log_blocked: When True, blocked prompts are logged at WARNING level.
        """
        self._log_blocked = log_blocked

    def scan(self, request: PromptRequest) -> SecurityResult:
        """Evaluate a request against all detection rules.

        Args:
            request: The inbound prompt request.

        Returns:
            A :class:`SecurityResult` with status CLEAR or BLOCK and the list of
            matched threats/rules.
        """
        text = request.prompt
        threats: list[ThreatType] = []
        matched: list[str] = []
        descriptions: list[str] = []

        for rule in _RULES:
            if rule.pattern.search(text):
                matched.append(rule.rule_id)
                descriptions.append(rule.description)
                if rule.threat not in threats:
                    threats.append(rule.threat)

        if matched:
            reason = "; ".join(descriptions)
            if self._log_blocked:
                logger.warning(
                    "Security BLOCK request_id={} rules={} threats={}",
                    request.request_id,
                    matched,
                    [t.value for t in threats],
                )
            return SecurityResult(
                status=SecurityStatus.BLOCK,
                threats=tuple(threats),
                matched_rules=tuple(matched),
                reason=reason,
            )

        return SecurityResult(
            status=SecurityStatus.CLEAR,
            reason="No threats detected",
        )
