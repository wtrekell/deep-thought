"""Gemini AI extraction for the Gmail Tool.

Sends email text and extraction instructions to the Gemini API and returns
the extracted content. Rate limiting is handled internally. Error handling
logs warnings and returns empty strings on failure.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class GeminiExtractor:
    """Thin wrapper around the Google Generative AI (Gemini) API.

    Handles rate limiting between calls. The caller is responsible for
    decision caching — this class is stateless beyond rate limit tracking.
    """

    def __init__(self, api_key: str, model: str, rate_limit_rpm: int = 15) -> None:
        """Initialise the extractor with API credentials and rate limit settings.

        Args:
            api_key: The Gemini API key.
            model: The model name to use (e.g., 'gemini-2.5-flash').
            rate_limit_rpm: Maximum requests per minute.
        """
        import google.generativeai as genai

        genai.configure(api_key=api_key)  # type: ignore[attr-defined]
        self._model = genai.GenerativeModel(model)  # type: ignore[attr-defined]
        self._rate_limit_rpm = rate_limit_rpm
        self._last_request_time: float = 0.0

    def _rate_limit(self) -> None:
        """Enforce rate limiting between API calls.

        Sleeps if the minimum interval since the last request has not elapsed.
        """
        if self._rate_limit_rpm <= 0:
            return
        minimum_interval = 60.0 / self._rate_limit_rpm
        elapsed = time.time() - self._last_request_time
        if elapsed < minimum_interval:
            time.sleep(minimum_interval - elapsed)
        self._last_request_time = time.time()

    def _build_prompt(self, email_text: str, instructions: str) -> str:
        """Build the prompt to send to Gemini.

        Args:
            email_text: The cleaned email body text.
            instructions: The extraction instructions from the rule config.

        Returns:
            A formatted prompt string.
        """
        return (
            f"You are an email content extractor. Follow these instructions precisely:\n\n"
            f"{instructions}\n\n"
            f"---\n\n"
            f"Email content:\n\n{email_text}"
        )

    def extract(self, email_text: str, instructions: str) -> str:
        """Extract content from email text using Gemini AI.

        Args:
            email_text: The cleaned email body text.
            instructions: The extraction instructions from the rule config.

        Returns:
            The extracted content as a string. Returns an empty string if
            the API call fails.
        """
        self._rate_limit()

        prompt = self._build_prompt(email_text, instructions)

        try:
            response: Any = self._model.generate_content(prompt)
            extracted_text: str = response.text
            return extracted_text
        except (ValueError, AttributeError, RuntimeError, OSError) as expected_error:
            # Expected generation errors: invalid input, empty response, API errors,
            # rate limit exceeded, network failure.
            logger.warning("Gemini extraction failed: %s", expected_error)
            return ""
        except Exception:
            # Unexpected exceptions (e.g., auth failure, internal SDK bug) should
            # surface to the caller rather than being silently swallowed.
            logger.exception("Unexpected error during Gemini extraction — re-raising.")
            raise
