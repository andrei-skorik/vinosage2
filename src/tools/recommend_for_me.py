"""Tool 7: recommend_for_me — profile-conditioned, catalog-grounded picks.

Unlike the other tools, this one is built per-request with the resolved
taste profile captured in a closure (SPEC §3.3) so the LLM never passes
identity as an argument. `build_recommend_for_me_tool(profile)` is called by
the graph's `agent` node (wired in Step 3) once per turn with the profile
`load_preferences` resolved for that user/session.

The profile only ever shapes the search filter and ranking — it is never a
source of catalog truth. Every returned wine still comes from the cached
active-wines DataFrame.
"""
from __future__ import annotations

from typing import Any, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.catalog import get_active_wines_df

_ERR = lambda code, msg: {"error": {"code": code, "message": msg}}   # noqa: E731

_PREFERRED_LIST_FIELDS = (
    ("preferred_types", "type"),
    ("preferred_grapes", "grape"),
    ("preferred_countries", "country"),
    ("preferred_styles", "style"),
    ("preferred_regions", "region"),
)
_DISLIKED_LIST_FIELDS = (
    ("disliked_types", "type"),
    ("disliked_grapes", "grape"),
    ("disliked_styles", "style"),
)


class RecommendForMeArgs(BaseModel):
    occasion:      Optional[str]   = Field(None, description="Optional context, e.g. 'dinner with friends'")
    max_price_eur: Optional[float] = Field(None, ge=0, description="Optional hard ceiling overriding profile")
    limit:         int             = Field(3, ge=1, le=5)


def _profile_is_empty(profile: dict[str, Any]) -> bool:
    for key, _ in _PREFERRED_LIST_FIELDS:
        if profile.get(key):
            return False
    if profile.get("preferred_characteristics"):
        return False
    if profile.get("min_price_eur_cents") is not None or profile.get("max_price_eur_cents") is not None:
        return False
    return True


def _unstocked_dimension(profile: dict[str, Any], df) -> str | None:
    """Best-effort: name the first preferred value that doesn't exist in the
    catalog at all, for an honest 'we don't stock that' message."""
    for key, col in _PREFERRED_LIST_FIELDS:
        values = profile.get(key) or []
        if not values:
            continue
        known = set(df[col].dropna().unique().tolist())
        for v in values:
            if v not in known:
                return v
    return None


def _overlap_score(row, profile: dict[str, Any]) -> int:
    score = 0
    for key, col in _PREFERRED_LIST_FIELDS:
        values = profile.get(key) or []
        if values and row.get(col) in values:
            score += 1
    chars = (row.get("characteristics") or "")
    if isinstance(chars, str):
        for c in profile.get("preferred_characteristics") or []:
            if c.lower() in chars.lower():
                score += 1
    return score


def _build(profile: dict[str, Any], occasion: str | None, max_price_eur: float | None, limit: int) -> dict[str, Any]:
    try:
        profile = profile or {}

        if _profile_is_empty(profile):
            return {
                "recommendations": [],
                "result": "empty_profile",
                "agent_instruction": (
                    "The user has no saved taste yet. Ask ONE short question "
                    "(e.g. red or white? sweet or dry?) instead of guessing. Name no wines."
                ),
            }

        df = get_active_wines_df()
        if df.empty:
            return _ERR("INTERNAL", "Catalog not available")

        mask = df["is_active"].notna()

        for key, col in _PREFERRED_LIST_FIELDS:
            values = profile.get(key) or []
            if values:
                mask = mask & df[col].isin(values)

        for key, col in _DISLIKED_LIST_FIELDS:
            values = profile.get(key) or []
            if values:
                mask = mask & ~df[col].isin(values)

        min_cents = profile.get("min_price_eur_cents")
        if min_cents is not None:
            mask = mask & (df["price_eur_cents"].notna() & (df["price_eur_cents"] >= min_cents))

        effective_max_cents = (
            int(max_price_eur * 100) if max_price_eur is not None else profile.get("max_price_eur_cents")
        )
        if effective_max_cents is not None:
            mask = mask & (df["price_eur_cents"].notna() & (df["price_eur_cents"] <= effective_max_cents))

        subset = df[mask]

        if subset.empty:
            unstocked = _unstocked_dimension(profile, df)
            if unstocked:
                instruction = (
                    f"The user's preferred '{unstocked}' is not stocked. Say so plainly "
                    "(no apology, no invention) and offer the closest in-stock style; "
                    "you MAY call filter_wines to find it."
                )
            else:
                instruction = (
                    "No in-stock wine matches this combination of taste preferences. "
                    "Say so plainly (no apology, no invention) and offer the closest "
                    "in-stock alternative; you MAY call filter_wines to find it."
                )
            return {"recommendations": [], "result": "no_catalog_match", "agent_instruction": instruction}

        rows = subset.to_dict("records")
        rows.sort(key=lambda r: (-_overlap_score(r, profile), r.get("price_eur_cents") or 0))
        rows = rows[:limit]

        recommendations = []
        for row in rows:
            cents = row.get("price_eur_cents")
            matched_dims = [
                col for key, col in _PREFERRED_LIST_FIELDS
                if (profile.get(key) or []) and row.get(col) in (profile.get(key) or [])
            ]
            reason_bits = " and ".join(f"{row.get(d)}" for d in matched_dims) if matched_dims else None
            rationale = (
                f"Matches your taste for {reason_bits}." if reason_bits
                else "Fits your saved price range."
            )
            recommendations.append({
                "wine_id":   row["wine_id"],
                "title":     row["title"],
                "price_eur": round(cents / 100, 2) if cents else None,
                "type":      row.get("type"),
                "grape":     row.get("grape"),
                "style":     row.get("style"),
                "rationale": rationale,
            })

        profile_used: dict[str, Any] = {}
        for key, _ in _PREFERRED_LIST_FIELDS:
            if profile.get(key):
                profile_used[key] = profile[key]
        for key, _ in _DISLIKED_LIST_FIELDS:
            if profile.get(key):
                profile_used[key] = profile[key]
        if effective_max_cents is not None:
            profile_used["max_price_eur"] = round(effective_max_cents / 100, 2)
        if occasion:
            profile_used["occasion"] = occasion

        return {
            "profile_used": profile_used,
            "recommendations": recommendations,
            "count": len(recommendations),
        }

    except Exception as exc:
        return _ERR("INTERNAL", str(exc))


def build_recommend_for_me_tool(profile: dict[str, Any]) -> StructuredTool:
    """Build a request-scoped recommend_for_me tool bound to `profile` via closure."""

    def _run(
        occasion: str | None = None,
        max_price_eur: float | None = None,
        limit: int = 3,
    ) -> dict[str, Any]:
        return _build(profile, occasion, max_price_eur, limit)

    return StructuredTool.from_function(
        func=_run,
        name="recommend_for_me",
        description=(
            "Recommend catalog wines personalised to the current user's saved taste "
            "profile. ALWAYS call this tool FIRST — before asking any clarifying "
            "questions — whenever the user asks what they should try, drink, or buy. "
            "If the profile is empty the tool will tell you exactly what to ask; "
            "if it has preferences it returns ready-to-present wine picks. "
            "Do NOT use for a specific dish (pair_with_food), named wines "
            "(compare_wines), or explicit filter constraints (filter_wines)."
        ),
        args_schema=RecommendForMeArgs,
    )
