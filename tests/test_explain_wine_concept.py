"""Unit tests for explain_wine_concept tool — Wikipedia HTTP call is mocked,
never live, per HANDOFF §6 testing philosophy applied to external APIs."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

_MODULE = "src.tools.explain_wine_concept.httpx.get"


class TestExplainWineConcept:
    def test_concept_found_returns_correct_shape(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "extract": "Nebbiolo is a red Italian wine grape most associated with Piedmont.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Nebbiolo"}},
        }
        with patch(_MODULE, return_value=mock_resp):
            from src.tools.explain_wine_concept import explain_wine_concept
            result = explain_wine_concept.invoke({"concept": "Nebbiolo", "locale": "en"})

        assert result["found"] is True
        assert result["concept"] == "Nebbiolo"
        assert result["summary"].startswith("Nebbiolo is a red Italian wine grape")
        assert result["source"] == "Wikipedia"
        assert result["source_url"] == "https://en.wikipedia.org/wiki/Nebbiolo"

    def test_concept_not_found_404_never_invents(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch(_MODULE, return_value=mock_resp):
            from src.tools.explain_wine_concept import explain_wine_concept
            result = explain_wine_concept.invoke({"concept": "Zzzqlerbnotaconcept", "locale": "en"})

        assert result["found"] is False
        assert result["summary"] is None
        assert "agent_instruction" in result
        assert result["agent_instruction"]

    def test_empty_extract_treated_as_not_found(self):
        """A 200 response with no usable extract must not be reported as found."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"extract": "", "content_urls": {}}
        with patch(_MODULE, return_value=mock_resp):
            from src.tools.explain_wine_concept import explain_wine_concept
            result = explain_wine_concept.invoke({"concept": "Glerb", "locale": "en"})

        assert result["found"] is False
        assert result["summary"] is None

    def test_timeout_degrades_gracefully_never_raises(self):
        """Both the initial attempt and the one retry (SPEC §3.5) time out —
        the tool must still return a result, never raise past its boundary."""
        with patch(_MODULE, side_effect=httpx.TimeoutException("timed out")):
            from src.tools.explain_wine_concept import explain_wine_concept
            result = explain_wine_concept.invoke({"concept": "Nebbiolo", "locale": "en"})

        assert result["found"] is False
        assert result["summary"] is None
        assert "agent_instruction" in result

    def test_non_200_non_404_status_degrades_gracefully(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch(_MODULE, return_value=mock_resp):
            from src.tools.explain_wine_concept import explain_wine_concept
            result = explain_wine_concept.invoke({"concept": "Nebbiolo", "locale": "en"})

        assert result["found"] is False
        assert "agent_instruction" in result

    def test_locale_maps_to_correct_wikipedia_language(self):
        captured_urls: list[str] = []

        def _fake_get(url, **kwargs):
            captured_urls.append(url)
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "extract": "Riesling ist eine Rebsorte.",
                "content_urls": {"desktop": {"page": "https://de.wikipedia.org/wiki/Riesling"}},
            }
            return resp

        with patch(_MODULE, side_effect=_fake_get):
            from src.tools.explain_wine_concept import explain_wine_concept
            result = explain_wine_concept.invoke({"concept": "Riesling", "locale": "de"})

        assert result["found"] is True
        assert captured_urls[0].startswith("https://de.wikipedia.org/")

    def test_unexpected_exception_returns_err_shape(self):
        """A genuine bug (e.g. malformed JSON) must surface as the project's
        standard _ERR shape, never an unhandled exception."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("malformed JSON")
        with patch(_MODULE, return_value=mock_resp):
            from src.tools.explain_wine_concept import explain_wine_concept
            result = explain_wine_concept.invoke({"concept": "Nebbiolo", "locale": "en"})

        assert "error" in result
        assert result["error"]["code"] == "EXTERNAL_API"
