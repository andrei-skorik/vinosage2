"""Heuristic prompt-injection / memory-injection detector (SPEC §5.7).

Conservative by design: prefer letting normal wine questions through. A
miss here is recoverable (the agent's own system-prompt rules are a second
line of defense); a false positive blocks a paying customer's question.
"""
from __future__ import annotations

import re
from typing import Any

# (pattern, event_type, severity, matched_rule) — first match wins.
# High severity → blocked (LLM bypassed); medium → flagged (allowed through,
# logged for tuning).
_PATTERNS: list[tuple[str, str, str, str]] = [
    (r"ignore\s+(all\s+)?previous", "prompt_injection", "high", "ignore_previous"),
    (r"disregard\s+(the\s+)?(instructions|prompt)", "prompt_injection", "high", "disregard_instructions"),
    (r"(reveal|show)\s+(your\s+|the\s+)?(system\s+)?prompt", "prompt_injection", "high", "reveal_prompt"),
    (r"\b(api[\s_-]?key|env(ironment)?\s+variable|secret\s+key)\b", "prompt_injection", "high", "extract_secrets"),
    (r"developer\s+mode", "prompt_injection", "medium", "developer_mode"),
    (r"you\s+are\s+now\b", "prompt_injection", "medium", "role_override"),
    (r"remember\s+(that\s+)?i\s*('?m|\s+am)\s+(an?\s+)?(admin|staff)", "memory_injection", "high", "fake_role_claim"),
    (r"set\s+my\s+(role|permissions)", "memory_injection", "high", "set_role"),
    (r"forget\s+(my|all|previous)\s+preferences", "memory_injection", "medium", "forget_preferences"),
    (r"(mark|treat|store|remember)\b.{0,40}\bas\s+available\b", "memory_injection", "medium", "fake_stock_claim"),
]


def check_guard(query: str) -> dict[str, Any]:
    """Classify a user query as clean, flagged, or blocked.

    Returns {"blocked": bool, "event_type": str | None, "severity": str | None,
    "matched_rule": str | None, "action_taken": str} — action_taken is
    'blocked' | 'flagged' | 'allowed'.
    """
    for pattern, event_type, severity, rule in _PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            action = "blocked" if severity == "high" else "flagged"
            return {
                "blocked": action == "blocked",
                "event_type": event_type,
                "severity": severity,
                "matched_rule": rule,
                "action_taken": action,
            }
    return {"blocked": False, "event_type": None, "severity": None, "matched_rule": None, "action_taken": "allowed"}
