"""Unit tests for src/preferences.py — explicit-signal extraction (SPEC §5.3)
and the feedback fold rule (SPEC §5.4)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

_CATALOG_MODULE = "src.preferences.get_active_wines_df"


class TestDetectPreferenceSignals:
    def test_explicit_positive_grape_in_catalog(self, mock_df):
        from src.preferences import detect_preference_signals
        with patch(_CATALOG_MODULE, return_value=mock_df):
            signals = detect_preference_signals("I love Malbec", {})
        assert "Malbec" in signals["preferred_grapes"]

    def test_explicit_negative_style_signal(self, mock_df):
        """'Sweet & Rich' is the only catalog style containing 'sweet' —
        disliking sweet wines must fold into disliked_styles."""
        from src.preferences import detect_preference_signals
        with patch(_CATALOG_MODULE, return_value=mock_df):
            signals = detect_preference_signals("I can't stand sweet wines", {})
        assert "Sweet & Rich" in signals["disliked_styles"]

    def test_sentence_boundary_keeps_trailing_question_out_of_clause(self, mock_df):
        """A clause must stop at the first sentence terminator — a wine named
        in an unrelated trailing question must never be folded into the
        preceding dislike clause (regression: this used to wrongly tag
        Riesling as disliked)."""
        from src.preferences import detect_preference_signals
        with patch(_CATALOG_MODULE, return_value=mock_df):
            signals = detect_preference_signals("I hate Chardonnay. What about Riesling?", {})
        assert "Riesling" not in signals.get("disliked_grapes", [])
        assert "Riesling" not in signals.get("preferred_grapes", [])

    def test_non_catalog_term_lands_in_notes_not_dropped(self, mock_df):
        """A term with no catalog match must still be recorded somewhere
        (notes) — the cardinal rule forbids inventing a structured-array
        match, but it must not be silently lost either."""
        from src.preferences import detect_preference_signals
        with patch(_CATALOG_MODULE, return_value=mock_df):
            signals = detect_preference_signals("I love Glerb", {})
        assert all("Glerb" not in (signals.get(f) or []) for f in (
            "preferred_types", "preferred_grapes", "preferred_countries",
            "preferred_styles", "preferred_characteristics",
        ))
        assert signals.get("notes")
        assert "Glerb" in signals["notes"]

    def test_casual_mention_triggers_no_signal(self, mock_df):
        from src.preferences import detect_preference_signals
        with patch(_CATALOG_MODULE, return_value=mock_df):
            signals = detect_preference_signals("I had a Malbec last night, it was nice.", {})
        assert signals == {}

    def test_idempotent_repeat_statement_returns_empty_delta(self, mock_df):
        from src.preferences import detect_preference_signals
        with patch(_CATALOG_MODULE, return_value=mock_df):
            first = detect_preference_signals("I love Malbec", {})
            second = detect_preference_signals("I love Malbec", first)
        assert second == {}


class TestFoldFeedback:
    def test_down_vote_does_not_add_grape_already_preferred(self):
        """Explicit positive preference wins over a single thumbs-down
        (SPEC §5.4) — Malbec is already in preferred_grapes, so a 👎 on a
        Malbec wine must not add it to disliked_grapes."""
        existing_profile = {
            "expertise_level": "beginner",
            "preferred_types": [], "preferred_grapes": ["Malbec"], "preferred_countries": [],
            "preferred_regions": [], "preferred_styles": [], "preferred_characteristics": [],
            "disliked_types": [], "disliked_grapes": [], "disliked_styles": [],
            "min_price_eur_cents": None, "max_price_eur_cents": None, "notes": None,
        }
        mock_resp = MagicMock()
        mock_resp.data = [existing_profile]
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = mock_resp
        mock_db = MagicMock()
        mock_db.table.return_value = mock_table

        wine = {"type": "Red", "grape": "Malbec", "style": "Rich & Juicy"}

        with patch("src.preferences.get_service_db", return_value=mock_db), \
             patch("src.preferences.upsert_preferences") as mock_upsert:
            from src.preferences import fold_feedback
            fold_feedback("user-1", wine, "down")

        mock_upsert.assert_called_once()
        assert "Malbec" not in mock_upsert.call_args.kwargs["disliked_grapes"]
        assert "Rich & Juicy" in mock_upsert.call_args.kwargs["disliked_styles"]

    def test_up_vote_adds_type_grape_style_to_preferred(self):
        empty_profile = {
            "expertise_level": "beginner",
            "preferred_types": [], "preferred_grapes": [], "preferred_countries": [],
            "preferred_regions": [], "preferred_styles": [], "preferred_characteristics": [],
            "disliked_types": [], "disliked_grapes": [], "disliked_styles": [],
            "min_price_eur_cents": None, "max_price_eur_cents": None, "notes": None,
        }
        mock_resp = MagicMock()
        mock_resp.data = [empty_profile]
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = mock_resp
        mock_db = MagicMock()
        mock_db.table.return_value = mock_table

        wine = {"type": "Red", "grape": "Malbec", "style": "Rich & Juicy"}

        with patch("src.preferences.get_service_db", return_value=mock_db), \
             patch("src.preferences.upsert_preferences") as mock_upsert:
            from src.preferences import fold_feedback
            fold_feedback("user-1", wine, "up")

        kwargs = mock_upsert.call_args.kwargs
        assert "Red" in kwargs["preferred_types"]
        assert "Malbec" in kwargs["preferred_grapes"]
        assert "Rich & Juicy" in kwargs["preferred_styles"]
