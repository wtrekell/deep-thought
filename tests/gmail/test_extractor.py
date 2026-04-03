"""Tests for the Gmail Tool Gemini AI extractor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestGeminiExtractor:
    """Tests for the GeminiExtractor class."""

    @patch("deep_thought.gmail.extractor.time.sleep")
    def test_extract_returns_text(self, mock_sleep: MagicMock) -> None:
        """Should return the extracted text from Gemini."""
        mock_response = MagicMock()
        mock_response.text = "Extracted key takeaways: 1. Point A 2. Point B"

        mock_client_instance = MagicMock()
        mock_client_instance.models.generate_content.return_value = mock_response

        with patch("google.genai.Client", return_value=mock_client_instance):
            from deep_thought.gmail.extractor import GeminiExtractor

            extractor = GeminiExtractor(api_key="test_key", model="gemini-2.5-flash", rate_limit_rpm=0)
            result = extractor.extract("Email body text here", "Extract key takeaways.")

        assert "Point A" in result
        assert "Point B" in result

    @patch("deep_thought.gmail.extractor.time.sleep")
    def test_extract_builds_correct_prompt(self, mock_sleep: MagicMock) -> None:
        """Should include both instructions and email text in the prompt."""
        mock_response = MagicMock()
        mock_response.text = "result"

        mock_client_instance = MagicMock()
        mock_client_instance.models.generate_content.return_value = mock_response

        with patch("google.genai.Client", return_value=mock_client_instance):
            from deep_thought.gmail.extractor import GeminiExtractor

            extractor = GeminiExtractor(api_key="test_key", model="gemini-2.5-flash", rate_limit_rpm=0)
            extractor.extract("The email body", "Extract summary.")

            call_kwargs = mock_client_instance.models.generate_content.call_args[1]
            prompt_contents = call_kwargs["contents"]
            assert "Extract summary." in prompt_contents
            assert "The email body" in prompt_contents

    @pytest.mark.error_handling
    @patch("deep_thought.gmail.extractor.time.sleep")
    def test_extract_returns_empty_on_expected_errors(self, mock_sleep: MagicMock) -> None:
        """Should return empty string for expected error types (ValueError, RuntimeError, etc.)."""
        for expected_error_class in (ValueError, AttributeError, RuntimeError, OSError):
            mock_client_instance = MagicMock()
            mock_client_instance.models.generate_content.side_effect = expected_error_class("expected error")

            with patch("google.genai.Client", return_value=mock_client_instance):
                from deep_thought.gmail.extractor import GeminiExtractor

                extractor = GeminiExtractor(api_key="test_key", model="gemini-2.5-flash", rate_limit_rpm=0)
                result = extractor.extract("Email body", "Extract content.")

            assert result == "", f"Expected empty string for {expected_error_class.__name__}"

    @pytest.mark.error_handling
    @patch("deep_thought.gmail.extractor.time.sleep")
    def test_extract_reraises_unexpected_exceptions(self, mock_sleep: MagicMock) -> None:
        """Should re-raise exceptions that are not in the expected error set."""

        class UnexpectedInternalError(Exception):
            """Simulates an unexpected SDK-internal error."""

        mock_client_instance = MagicMock()
        mock_client_instance.models.generate_content.side_effect = UnexpectedInternalError("SDK bug")

        with patch("google.genai.Client", return_value=mock_client_instance):
            from deep_thought.gmail.extractor import GeminiExtractor

            extractor = GeminiExtractor(api_key="test_key", model="gemini-2.5-flash", rate_limit_rpm=0)

            with pytest.raises(UnexpectedInternalError, match="SDK bug"):
                extractor.extract("Email body", "Extract content.")
