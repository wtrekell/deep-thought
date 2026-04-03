"""Multi-layer hallucination detection for Whisper transcriptions.

Whisper can produce hallucinated output — repeated phrases, fabricated text
during silence, or garbled segments. This module scores segments across
multiple detection layers. Segments exceeding a combined threshold are
actioned (removed, flagged, or logged).

Each detector is a pure function that returns a float score (0.0 or 1.0).
Scores are aggregated in ``score_segment`` and acted on by
``apply_hallucination_detection``.
"""

from __future__ import annotations

import logging
import string
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deep_thought.audio.models import TranscriptSegment

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blocklist of known Whisper hallucination phrases
# ---------------------------------------------------------------------------

# These phrases frequently appear in Whisper output as artifacts from its
# YouTube training data, even when the audio contains nothing of the sort.
_KNOWN_HALLUCINATION_PHRASES: frozenset[str] = frozenset(
    {
        "thank you for watching",
        "thanks for watching",
        "please subscribe",
        "subscribe to my channel",
        "like and subscribe",
        "don't forget to subscribe",
        "hit the bell",
        "subtitled by",
        "subtitles by",
        "transcribed by",
        "translated by",
        "captions by",
        "please like and subscribe",
        "thanks for listening",
        "thank you for listening",
        "see you in the next video",
        "see you next time",
        "bye bye",
        "music",
        "applause",
        "laughter",
    }
)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class HallucinationScore:
    """Score result for a single transcript segment."""

    segment_index: int
    """Zero-based index of the scored segment in the original list."""

    layer_scores: dict[str, float] = field(default_factory=dict)
    """Per-layer scores keyed by detector name, each 0.0 or 1.0."""

    total_score: float = 0.0
    """Sum of all layer scores."""

    action_taken: str = "none"
    """Outcome applied to the segment: "none", "removed", "flagged", or "logged"."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, and collapse extra whitespace.

    Args:
        text: Raw segment text.

    Returns:
        Cleaned, normalised string suitable for comparison.
    """
    lowered = text.lower().strip()
    without_punctuation = lowered.translate(str.maketrans("", "", string.punctuation))
    return " ".join(without_punctuation.split())


# ---------------------------------------------------------------------------
# Detection layers
# ---------------------------------------------------------------------------


def _check_ngram_repetition_in_word_list(words: list[str], threshold: int) -> bool:
    """Return True if any bigram or trigram appears >= threshold times in words.

    Used both for within-segment checks and cross-segment window checks.

    Args:
        words: Pre-normalised, whitespace-split word list to scan.
        threshold: Minimum occurrence count to consider repetitive.

    Returns:
        True if any bigram or trigram meets or exceeds the threshold, False otherwise.
    """
    if len(words) >= 2:
        bigrams = [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)]
        bigram_counts = Counter(bigrams)
        if any(count >= threshold for count in bigram_counts.values()):
            return True

    if len(words) >= 3:
        trigrams = [f"{words[i]} {words[i + 1]} {words[i + 2]}" for i in range(len(words) - 2)]
        trigram_counts = Counter(trigrams)
        if any(count >= threshold for count in trigram_counts.values()):
            return True

    return False


def detect_repetition(
    segment: TranscriptSegment,
    window_segments: list[TranscriptSegment],
    threshold: int = 3,
) -> float:
    """Detect repeated phrases using bigram and trigram matching.

    Three checks are performed:

    1. **Window repetition** — counts how many times the normalised text of
       ``segment`` appears verbatim among ``window_segments``. If the count
       meets or exceeds ``threshold``, the segment is flagged.

    2. **Internal repetition** — splits the segment into bigrams and trigrams
       and checks whether any single n-gram appears more than ``threshold``
       times within the segment itself.

    3. **Cross-segment n-gram repetition** — concatenates all window segment
       texts (including the target segment) into a single word list and checks
       whether any bigram or trigram appears at an elevated rate across the
       entire window. The cross-segment threshold is scaled by window size so
       that a phrase appearing once per segment in a large window does not
       produce false positives: a n-gram must appear more than
       ``threshold * max(1, len(window_segments) // 2)`` times to be flagged.
       This catches hallucinations that span segment boundaries, such as
       "thank you for watching" split across the end of one segment and the
       start of the next.

    Args:
        segment: The segment being evaluated.
        window_segments: Surrounding segments used as the repetition window.
        threshold: Minimum occurrence count to flag as a hallucination.
            Used directly for checks 1 and 2. For check 3 (cross-segment),
            the threshold is scaled by half the window size to avoid false
            positives on naturally varied speech.

    Returns:
        1.0 if repetition exceeds the threshold, 0.0 otherwise.
    """
    normalised_target = _normalize_text(segment.text)

    # Check 1: How many window segments share the same normalised text
    window_match_count = sum(
        1 for window_segment in window_segments if _normalize_text(window_segment.text) == normalised_target
    )
    if window_match_count >= threshold:
        return 1.0

    # Check 2: Internal bigram and trigram repetition within this segment alone
    target_words = normalised_target.split()
    if _check_ngram_repetition_in_word_list(target_words, threshold):
        return 1.0

    # Check 3: Cross-segment n-gram repetition across the full window.
    # Concatenate all segment texts (window + target) into one word list and
    # look for any bigram or trigram that appears at a rate suggesting a
    # hallucination phrase has been repeated across segment boundaries.
    if window_segments:
        all_window_texts = [_normalize_text(ws.text) for ws in window_segments] + [normalised_target]
        combined_words = [word for text in all_window_texts for word in text.split()]
        # Scale threshold by half the window size so a phrase must recur more
        # densely than "once per two segments" before being flagged.
        cross_segment_threshold = threshold * max(1, len(window_segments) // 2)
        if _check_ngram_repetition_in_word_list(combined_words, cross_segment_threshold):
            return 1.0

    return 0.0


def detect_silence_gap(segment: TranscriptSegment, no_speech_prob_threshold: float = 0.6) -> float:
    """Detect segments likely overlapping silence using Whisper's no_speech_prob.

    Whisper provides a probability estimate that a segment contains no speech.
    High values suggest the transcribed text was fabricated over silence.

    Args:
        segment: The segment being evaluated.
        no_speech_prob_threshold: Probability above which the segment is flagged.

    Returns:
        1.0 if no_speech_prob exceeds the threshold, 0.0 otherwise.
        Returns 0.0 if no_speech_prob is None (no signal available).
    """
    if segment.no_speech_prob is None:
        return 0.0
    return 1.0 if segment.no_speech_prob > no_speech_prob_threshold else 0.0


def score_confidence(segment: TranscriptSegment, confidence_floor: float = -1.0) -> float:
    """Score segment confidence as a hallucination signal.

    Low confidence is a weak signal — some hallucinations are produced with
    high confidence. This layer is used as a contributing factor in the
    aggregate score rather than a standalone hard filter.

    Args:
        segment: The segment being evaluated.
        confidence_floor: Log-probability below which the segment is flagged.

    Returns:
        1.0 if confidence is below the floor, 0.0 otherwise.
        Returns 0.0 if confidence is None (no signal available).
    """
    if segment.confidence is None:
        return 0.0
    return 1.0 if segment.confidence < confidence_floor else 0.0


def detect_duration_anomaly(
    segment: TranscriptSegment,
    chars_per_sec_max: int = 25,
    chars_per_sec_min: int = 2,
) -> float:
    """Detect text length disproportionate to the segment's time span.

    Normal conversational speech produces roughly 12–18 characters per second.
    Segments that are either far too dense (text burst) or far too sparse for
    their length are flagged.

    Short segments under 0.5 seconds are ignored because their character rate
    is unreliable at that granularity.

    Args:
        segment: The segment being evaluated.
        chars_per_sec_max: Upper bound; above this rate the segment is flagged.
        chars_per_sec_min: Lower bound; below this rate the segment is flagged
                           for segments longer than 0.5 seconds.

    Returns:
        1.0 if the character rate is anomalous, 0.0 otherwise.
    """
    segment_duration = segment.end - segment.start
    if segment_duration <= 0:
        return 0.0

    character_count = len(segment.text.strip())
    chars_per_second = character_count / segment_duration

    if chars_per_second > chars_per_sec_max:
        return 1.0

    # Only flag sparse segments that are long enough to measure reliably
    if segment_duration > 0.5 and chars_per_second < chars_per_sec_min:
        return 1.0

    return 0.0


def check_compression_ratio(
    segment: TranscriptSegment,
    threshold: float = 2.4,
) -> float:
    """Check Whisper's compression_ratio metric for hallucination signal.

    Whisper computes a compression ratio for each segment. Highly repetitive
    or formulaic text — a hallmark of hallucinations — compresses more
    aggressively and produces a higher ratio.

    Args:
        segment: The segment being evaluated.
        threshold: Compression ratio above which the segment is flagged.

    Returns:
        1.0 if compression_ratio exceeds the threshold, 0.0 otherwise.
        Returns 0.0 if compression_ratio is None (metric not available).
    """
    if segment.compression_ratio is None:
        return 0.0
    return 1.0 if segment.compression_ratio > threshold else 0.0


def check_blocklist(segment: TranscriptSegment) -> float:
    """Check whether the segment text matches a known hallucination phrase.

    Normalises the segment text and checks against ``_KNOWN_HALLUCINATION_PHRASES``.
    The matching strategy depends on phrase length:

    - **Short phrases (3 words or fewer):** require an approximate exact match —
      the normalised segment text must equal the phrase, or the phrase must equal
      the entire normalised segment text. This avoids false positives where common
      short words like "music" or "bye bye" appear inside legitimate speech.
    - **Longer phrases (4+ words):** use substring matching, since multi-word
      phrases like "thank you for watching" are specific enough to flag reliably
      even when embedded in a longer sentence.

    Args:
        segment: The segment being evaluated.

    Returns:
        1.0 if a known hallucination phrase is found, 0.0 otherwise.
    """
    normalised_segment_text = _normalize_text(segment.text)
    for known_phrase in _KNOWN_HALLUCINATION_PHRASES:
        phrase_word_count = len(known_phrase.split())
        if phrase_word_count <= 3:
            # Require approximate exact match for short phrases to avoid false positives
            if normalised_segment_text == known_phrase:
                return 1.0
        else:
            # Substring match is safe for longer, more specific phrases
            if known_phrase in normalised_segment_text:
                return 1.0
    return 0.0


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def score_segment(
    segment: TranscriptSegment,
    window_segments: list[TranscriptSegment],
    *,
    segment_index: int = 0,
    repetition_threshold: int = 3,
    compression_ratio_threshold: float = 2.4,
    confidence_floor: float = -1.0,
    no_speech_prob_threshold: float = 0.6,
    chars_per_sec_max: int = 25,
    chars_per_sec_min: int = 2,
    blocklist_enabled: bool = True,
) -> HallucinationScore:
    """Score a single segment across all detection layers.

    Each layer contributes 0.0 or 1.0 to the total. A segment that triggers
    more layers is more likely to be a hallucination.

    Args:
        segment: The segment to score.
        window_segments: Surrounding segments passed to the repetition detector.
        segment_index: Zero-based position of the segment in the original list.
        repetition_threshold: Minimum repetition count to flag.
        compression_ratio_threshold: Compression ratio above which to flag.
        confidence_floor: Log-probability below which to flag.
        no_speech_prob_threshold: No-speech probability above which to flag.
        chars_per_sec_max: Maximum plausible character rate.
        chars_per_sec_min: Minimum plausible character rate for long segments.
        blocklist_enabled: Whether to run the blocklist check.

    Returns:
        A HallucinationScore with per-layer scores and a total.
    """
    layer_scores: dict[str, float] = {
        "repetition": detect_repetition(segment, window_segments, threshold=repetition_threshold),
        "silence_gap": detect_silence_gap(segment, no_speech_prob_threshold=no_speech_prob_threshold),
        "confidence": score_confidence(segment, confidence_floor=confidence_floor),
        "duration_anomaly": detect_duration_anomaly(
            segment,
            chars_per_sec_max=chars_per_sec_max,
            chars_per_sec_min=chars_per_sec_min,
        ),
        "compression_ratio": check_compression_ratio(segment, threshold=compression_ratio_threshold),
    }

    if blocklist_enabled:
        layer_scores["blocklist"] = check_blocklist(segment)

    total_score = sum(layer_scores.values())

    return HallucinationScore(
        segment_index=segment_index,
        layer_scores=layer_scores,
        total_score=total_score,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_hallucination_detection(
    segments: list[TranscriptSegment],
    *,
    repetition_threshold: int = 3,
    compression_ratio_threshold: float = 2.4,
    confidence_floor: float = -1.0,
    no_speech_prob_threshold: float = 0.6,
    duration_chars_per_sec_max: int = 25,
    duration_chars_per_sec_min: int = 2,
    blocklist_enabled: bool = True,
    score_threshold: int = 2,
    action: str = "remove",
    window_size: int = 10,
) -> tuple[list[TranscriptSegment], list[HallucinationScore]]:
    """Apply hallucination detection to all segments in a transcript.

    Iterates over every segment, scoring it against a sliding context window
    of up to ``window_size`` surrounding segments. Segments whose total score
    meets or exceeds ``score_threshold`` are actioned according to ``action``.

    Args:
        segments: All transcript segments to analyse.
        repetition_threshold: Minimum window repetition count to flag.
        compression_ratio_threshold: Compression ratio threshold.
        confidence_floor: Confidence log-probability threshold.
        no_speech_prob_threshold: No-speech probability threshold.
        duration_chars_per_sec_max: Maximum plausible character rate.
        duration_chars_per_sec_min: Minimum plausible character rate.
        blocklist_enabled: Whether to run the blocklist layer.
        score_threshold: Number of layers that must flag before action is taken.
        action: What to do with flagged segments — "remove" filters them out,
                "flag" keeps them but records the score, "log" records only.
        window_size: Number of surrounding segments used for repetition context.

    Returns:
        A tuple of (output_segments, all_scores).

        - output_segments: The filtered (or unfiltered) segment list. When
          action is "remove", hallucinated segments are excluded. For "flag"
          and "log" all segments are returned.
        - all_scores: One HallucinationScore per input segment, always
          returned regardless of action.
    """
    all_scores: list[HallucinationScore] = []
    kept_segments: list[TranscriptSegment] = []

    half_window = window_size // 2

    for segment_index, current_segment in enumerate(segments):
        # Build a context window centred on the current segment, excluding it
        window_start = max(0, segment_index - half_window)
        window_end = min(len(segments), segment_index + half_window + 1)
        window_segments = [
            segments[position] for position in range(window_start, window_end) if position != segment_index
        ]

        hallucination_score = score_segment(
            current_segment,
            window_segments,
            segment_index=segment_index,
            repetition_threshold=repetition_threshold,
            compression_ratio_threshold=compression_ratio_threshold,
            confidence_floor=confidence_floor,
            no_speech_prob_threshold=no_speech_prob_threshold,
            chars_per_sec_max=duration_chars_per_sec_max,
            chars_per_sec_min=duration_chars_per_sec_min,
            blocklist_enabled=blocklist_enabled,
        )

        segment_is_flagged = hallucination_score.total_score >= score_threshold

        if segment_is_flagged:
            if action == "remove":
                hallucination_score.action_taken = "removed"
                logger.debug(
                    "Segment %d removed as likely hallucination (score=%.1f): %r",
                    segment_index,
                    hallucination_score.total_score,
                    current_segment.text[:60],
                )
            elif action == "flag":
                hallucination_score.action_taken = "flagged"
                kept_segments.append(current_segment)
                logger.debug(
                    "Segment %d flagged as likely hallucination (score=%.1f): %r",
                    segment_index,
                    hallucination_score.total_score,
                    current_segment.text[:60],
                )
            else:  # action == "log"
                hallucination_score.action_taken = "logged"
                kept_segments.append(current_segment)
                logger.info(
                    "Segment %d scored %.1f (hallucination candidate): %r",
                    segment_index,
                    hallucination_score.total_score,
                    current_segment.text[:60],
                )
        else:
            kept_segments.append(current_segment)

        all_scores.append(hallucination_score)

    return kept_segments, all_scores
