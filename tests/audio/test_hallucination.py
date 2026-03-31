"""Tests for the hallucination detection module in deep_thought.audio.hallucination."""

from __future__ import annotations

from deep_thought.audio.hallucination import (
    HallucinationScore,
    _normalize_text,
    apply_hallucination_detection,
    check_blocklist,
    check_compression_ratio,
    detect_duration_anomaly,
    detect_repetition,
    detect_silence_gap,
    score_confidence,
    score_segment,
)
from deep_thought.audio.models import TranscriptSegment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_segment(
    start: float = 0.0,
    end: float = 2.0,
    text: str = "This is normal speech.",
    confidence: float | None = None,
    no_speech_prob: float | None = None,
    compression_ratio: float | None = None,
    speaker: str | None = None,
) -> TranscriptSegment:
    """Return a TranscriptSegment with sensible test defaults."""
    return TranscriptSegment(
        start=start,
        end=end,
        text=text,
        confidence=confidence,
        no_speech_prob=no_speech_prob,
        compression_ratio=compression_ratio,
        speaker=speaker,
    )


# ---------------------------------------------------------------------------
# TestNormalizeText (T-08)
# ---------------------------------------------------------------------------


class TestNormalizeText:
    def test_lowercases_input(self) -> None:
        """_normalize_text must convert all characters to lowercase."""
        result = _normalize_text("Hello World")
        assert result == "hello world"

    def test_strips_punctuation(self) -> None:
        """_normalize_text must remove all punctuation characters."""
        result = _normalize_text("Hello, world!")
        assert result == "hello world"

    def test_collapses_extra_whitespace(self) -> None:
        """_normalize_text must collapse multiple spaces into a single space."""
        result = _normalize_text("hello   world")
        assert result == "hello world"

    def test_strips_leading_and_trailing_whitespace(self) -> None:
        """_normalize_text must strip leading and trailing whitespace."""
        result = _normalize_text("  hello world  ")
        assert result == "hello world"

    def test_empty_string_returns_empty(self) -> None:
        """_normalize_text on an empty string must return an empty string."""
        result = _normalize_text("")
        assert result == ""

    def test_punctuation_only_returns_empty(self) -> None:
        """A string containing only punctuation must produce an empty string."""
        result = _normalize_text("!?.,;:")
        assert result == ""

    def test_preserves_alphanumeric_content(self) -> None:
        """Alphanumeric content must be preserved after normalization."""
        result = _normalize_text("Thank you for watching!")
        assert result == "thank you for watching"

    def test_combined_normalisation(self) -> None:
        """_normalize_text must apply all transformations together."""
        result = _normalize_text("  Thank You, FOR Watching!!  ")
        assert result == "thank you for watching"


# ---------------------------------------------------------------------------
# TestRepetitionDetection
# ---------------------------------------------------------------------------


class TestRepetitionDetection:
    def test_detects_repeated_phrases_in_window(self) -> None:
        """A segment that appears three or more times in the window must be flagged."""
        repeated_text = "Thank you very much."
        target_segment = _make_segment(text=repeated_text)
        window_segments = [
            _make_segment(text=repeated_text),
            _make_segment(text=repeated_text),
            _make_segment(text=repeated_text),
            _make_segment(text="Something completely different."),
        ]
        result = detect_repetition(target_segment, window_segments, threshold=3)
        assert result == 1.0

    def test_passes_when_no_repetition(self) -> None:
        """A unique segment with no repeated text must return 0.0."""
        target_segment = _make_segment(text="This is a unique utterance.")
        window_segments = [
            _make_segment(text="First different sentence."),
            _make_segment(text="Second different sentence."),
        ]
        result = detect_repetition(target_segment, window_segments, threshold=3)
        assert result == 0.0

    def test_respects_threshold_parameter(self) -> None:
        """With threshold=2, two window matches must trigger a flag."""
        repeated_text = "Repeated phrase here."
        target_segment = _make_segment(text=repeated_text)
        window_segments = [
            _make_segment(text=repeated_text),
            _make_segment(text=repeated_text),
        ]
        result = detect_repetition(target_segment, window_segments, threshold=2)
        assert result == 1.0

    def test_below_threshold_not_flagged(self) -> None:
        """One window match against a threshold of 3 must not flag the segment."""
        repeated_text = "Once repeated."
        target_segment = _make_segment(text=repeated_text)
        window_segments = [
            _make_segment(text=repeated_text),
            _make_segment(text="Something else entirely."),
        ]
        result = detect_repetition(target_segment, window_segments, threshold=3)
        assert result == 0.0

    def test_detects_internal_bigram_repetition(self) -> None:
        """A segment with an internal repeated bigram must be flagged."""
        # "hello world" repeated many times within one segment
        repeated_bigram_text = "hello world hello world hello world hello world"
        target_segment = _make_segment(text=repeated_bigram_text)
        result = detect_repetition(target_segment, [], threshold=3)
        assert result == 1.0

    def test_empty_window_no_flag(self) -> None:
        """An empty context window must not produce a false positive."""
        target_segment = _make_segment(text="Isolated segment.")
        result = detect_repetition(target_segment, [], threshold=3)
        assert result == 0.0


# ---------------------------------------------------------------------------
# TestSilenceGapDetection
# ---------------------------------------------------------------------------


class TestSilenceGapDetection:
    def test_flags_high_no_speech_prob(self) -> None:
        """A segment with no_speech_prob above 0.6 must return 1.0."""
        segment = _make_segment(no_speech_prob=0.85)
        result = detect_silence_gap(segment, no_speech_prob_threshold=0.6)
        assert result == 1.0

    def test_passes_low_no_speech_prob(self) -> None:
        """A segment with no_speech_prob below the threshold must return 0.0."""
        segment = _make_segment(no_speech_prob=0.2)
        result = detect_silence_gap(segment, no_speech_prob_threshold=0.6)
        assert result == 0.0

    def test_returns_zero_when_no_speech_prob_is_none(self) -> None:
        """When no_speech_prob is None, the layer must return 0.0 (no signal)."""
        segment = _make_segment(no_speech_prob=None)
        result = detect_silence_gap(segment)
        assert result == 0.0

    def test_exactly_at_threshold_not_flagged(self) -> None:
        """A segment exactly at the threshold must not be flagged (strictly above)."""
        segment = _make_segment(no_speech_prob=0.6)
        result = detect_silence_gap(segment, no_speech_prob_threshold=0.6)
        assert result == 0.0


# ---------------------------------------------------------------------------
# TestConfidenceScoring
# ---------------------------------------------------------------------------


class TestConfidenceScoring:
    def test_flags_low_confidence(self) -> None:
        """A confidence value below the floor must return 1.0."""
        segment = _make_segment(confidence=-2.5)
        result = score_confidence(segment, confidence_floor=-1.0)
        assert result == 1.0

    def test_passes_normal_confidence(self) -> None:
        """A confidence value at or above the floor must return 0.0."""
        segment = _make_segment(confidence=-0.5)
        result = score_confidence(segment, confidence_floor=-1.0)
        assert result == 0.0

    def test_returns_zero_when_confidence_is_none(self) -> None:
        """When confidence is None, the layer must return 0.0 (no signal)."""
        segment = _make_segment(confidence=None)
        result = score_confidence(segment)
        assert result == 0.0

    def test_exactly_at_floor_not_flagged(self) -> None:
        """A confidence value exactly at the floor must not be flagged."""
        segment = _make_segment(confidence=-1.0)
        result = score_confidence(segment, confidence_floor=-1.0)
        assert result == 0.0


# ---------------------------------------------------------------------------
# TestDurationAnomaly
# ---------------------------------------------------------------------------


class TestDurationAnomaly:
    def test_flags_text_burst_above_max(self) -> None:
        """A segment with a character rate above chars_per_sec_max must be flagged."""
        # 1 second with 100 characters = 100 chars/sec, well above 25
        segment = _make_segment(start=0.0, end=1.0, text="A" * 100)
        result = detect_duration_anomaly(segment, chars_per_sec_max=25, chars_per_sec_min=2)
        assert result == 1.0

    def test_flags_sparse_text_below_min_for_long_segments(self) -> None:
        """A long segment with very few characters must be flagged."""
        # 5 seconds, 3 characters = 0.6 chars/sec, below minimum of 2
        segment = _make_segment(start=0.0, end=5.0, text="Hi.")
        result = detect_duration_anomaly(segment, chars_per_sec_max=25, chars_per_sec_min=2)
        assert result == 1.0

    def test_ignores_short_segments_under_half_second(self) -> None:
        """Segments under 0.5 seconds must not be flagged for sparse content."""
        # 0.3 second with 1 character is sparse but too short to measure
        segment = _make_segment(start=0.0, end=0.3, text="I")
        result = detect_duration_anomaly(segment, chars_per_sec_max=25, chars_per_sec_min=2)
        assert result == 0.0

    def test_passes_normal_speech_rate(self) -> None:
        """A segment with a typical character rate must return 0.0."""
        # 3 seconds, 45 characters = 15 chars/sec (normal)
        segment = _make_segment(start=0.0, end=3.0, text="A" * 45)
        result = detect_duration_anomaly(segment, chars_per_sec_max=25, chars_per_sec_min=2)
        assert result == 0.0

    def test_zero_duration_segment_returns_zero(self) -> None:
        """A segment with zero duration must return 0.0 (avoids division by zero)."""
        segment = _make_segment(start=1.0, end=1.0, text="Same start and end.")
        result = detect_duration_anomaly(segment)
        assert result == 0.0


# ---------------------------------------------------------------------------
# TestCompressionRatio
# ---------------------------------------------------------------------------


class TestCompressionRatio:
    def test_flags_high_compression_ratio(self) -> None:
        """A compression ratio above the threshold must return 1.0."""
        segment = _make_segment(compression_ratio=3.0)
        result = check_compression_ratio(segment, threshold=2.4)
        assert result == 1.0

    def test_passes_normal_compression_ratio(self) -> None:
        """A compression ratio at or below the threshold must return 0.0."""
        segment = _make_segment(compression_ratio=1.8)
        result = check_compression_ratio(segment, threshold=2.4)
        assert result == 0.0

    def test_returns_zero_when_compression_ratio_is_none(self) -> None:
        """When compression_ratio is None, the layer must return 0.0 (no signal)."""
        segment = _make_segment(compression_ratio=None)
        result = check_compression_ratio(segment)
        assert result == 0.0

    def test_exactly_at_threshold_not_flagged(self) -> None:
        """A compression ratio exactly at the threshold must not be flagged."""
        segment = _make_segment(compression_ratio=2.4)
        result = check_compression_ratio(segment, threshold=2.4)
        assert result == 0.0


# ---------------------------------------------------------------------------
# TestBlocklist
# ---------------------------------------------------------------------------


class TestBlocklist:
    def test_matches_exact_known_phrase(self) -> None:
        """A segment containing an exact known phrase must return 1.0."""
        segment = _make_segment(text="Thank you for watching.")
        result = check_blocklist(segment)
        assert result == 1.0

    def test_matches_known_phrase_as_substring(self) -> None:
        """A phrase that contains a known hallucination as a substring must be flagged."""
        segment = _make_segment(text="Thank you for watching this video today!")
        result = check_blocklist(segment)
        assert result == 1.0

    def test_passes_clean_text(self) -> None:
        """Normal transcript text must not match any blocklist entry."""
        segment = _make_segment(text="The conference will start at nine in the morning.")
        result = check_blocklist(segment)
        assert result == 0.0

    def test_case_insensitive_matching(self) -> None:
        """Blocklist matching must be case-insensitive."""
        segment = _make_segment(text="THANK YOU FOR WATCHING")
        result = check_blocklist(segment)
        assert result == 1.0

    def test_matches_applause_marker(self) -> None:
        """The 'applause' phrase must be flagged as a known hallucination."""
        segment = _make_segment(text="[applause]")
        result = check_blocklist(segment)
        assert result == 1.0

    def test_matches_music_marker(self) -> None:
        """The 'music' phrase must be flagged as a known hallucination."""
        segment = _make_segment(text="music")
        result = check_blocklist(segment)
        assert result == 1.0


# ---------------------------------------------------------------------------
# TestScoreAggregation
# ---------------------------------------------------------------------------


class TestScoreAggregation:
    def test_score_segment_accumulates_layer_scores(self) -> None:
        """score_segment must return a HallucinationScore with all expected keys."""
        segment = _make_segment(
            text="Normal speech segment.",
            no_speech_prob=0.1,
            confidence=-0.3,
            compression_ratio=1.5,
        )
        result = score_segment(segment, [])
        assert "repetition" in result.layer_scores
        assert "silence_gap" in result.layer_scores
        assert "confidence" in result.layer_scores
        assert "duration_anomaly" in result.layer_scores
        assert "compression_ratio" in result.layer_scores
        assert "blocklist" in result.layer_scores

    def test_total_score_is_sum_of_layer_scores(self) -> None:
        """total_score must equal the arithmetic sum of all individual layer scores."""
        segment = _make_segment(
            text="Normal segment.",
            no_speech_prob=0.1,
            confidence=-0.3,
            compression_ratio=1.2,
        )
        result = score_segment(segment, [])
        expected_total = sum(result.layer_scores.values())
        assert result.total_score == expected_total

    def test_all_clean_segment_scores_zero(self) -> None:
        """A clearly clean segment must have a total score of 0.0."""
        segment = _make_segment(
            start=0.0,
            end=3.0,
            text="This is a perfectly normal sentence.",
            no_speech_prob=0.05,
            confidence=-0.2,
            compression_ratio=1.1,
        )
        result = score_segment(segment, [])
        assert result.total_score == 0.0

    def test_blocklist_disabled_excludes_layer(self) -> None:
        """When blocklist_enabled is False, the blocklist key must not appear."""
        segment = _make_segment(text="Thank you for watching.")
        result = score_segment(segment, [], blocklist_enabled=False)
        assert "blocklist" not in result.layer_scores

    def test_segment_index_default_is_zero(self) -> None:
        """The segment_index field defaults to 0 before apply_hallucination_detection sets it."""
        segment = _make_segment(text="Some text.")
        result = score_segment(segment, [])
        assert isinstance(result, HallucinationScore)
        assert result.segment_index == 0


# ---------------------------------------------------------------------------
# TestApplyHallucinationDetection
# ---------------------------------------------------------------------------


class TestApplyHallucinationDetection:
    def _make_clean_segment(self, text: str = "Normal speech.") -> TranscriptSegment:
        """Return a segment that will not trigger any hallucination layer."""
        return _make_segment(
            start=0.0,
            end=3.0,
            text=text,
            no_speech_prob=0.05,
            confidence=-0.2,
            compression_ratio=1.1,
        )

    def _make_hallucinated_segment(self) -> TranscriptSegment:
        """Return a segment designed to trigger multiple hallucination layers."""
        return _make_segment(
            start=0.0,
            end=10.0,
            text="Thank you for watching",  # blocklist hit
            no_speech_prob=0.9,  # silence gap hit
            compression_ratio=3.5,  # compression ratio hit
        )

    def test_remove_action_filters_out_flagged_segments(self) -> None:
        """With action='remove', segments above the threshold must be excluded."""
        clean_segment = self._make_clean_segment("Clean speech here.")
        hallucinated_segment = self._make_hallucinated_segment()

        kept_segments, all_scores = apply_hallucination_detection(
            [clean_segment, hallucinated_segment],
            score_threshold=2,
            action="remove",
        )

        assert len(kept_segments) == 1
        assert kept_segments[0].text == "Clean speech here."

    def test_flag_action_keeps_all_segments(self) -> None:
        """With action='flag', all segments must be returned regardless of score."""
        hallucinated_segment = self._make_hallucinated_segment()

        kept_segments, all_scores = apply_hallucination_detection(
            [hallucinated_segment],
            score_threshold=2,
            action="flag",
        )

        assert len(kept_segments) == 1

    def test_log_action_keeps_all_segments(self) -> None:
        """With action='log', all segments must be returned unchanged."""
        hallucinated_segment = self._make_hallucinated_segment()

        kept_segments, all_scores = apply_hallucination_detection(
            [hallucinated_segment],
            score_threshold=2,
            action="log",
        )

        assert len(kept_segments) == 1

    def test_segments_below_threshold_are_always_kept(self) -> None:
        """Clean segments that score below the threshold must never be removed."""
        clean_segments = [self._make_clean_segment(f"Sentence {idx}.") for idx in range(5)]

        kept_segments, all_scores = apply_hallucination_detection(
            clean_segments,
            score_threshold=2,
            action="remove",
        )

        assert len(kept_segments) == 5

    def test_scores_always_returned_regardless_of_action(self) -> None:
        """all_scores must contain one entry per input segment for every action mode."""
        segments = [
            self._make_clean_segment("First sentence."),
            self._make_hallucinated_segment(),
            self._make_clean_segment("Third sentence."),
        ]

        for action_mode in ("remove", "flag", "log"):
            _kept, all_scores = apply_hallucination_detection(
                segments,
                score_threshold=2,
                action=action_mode,
            )
            assert len(all_scores) == 3, f"Expected 3 scores for action={action_mode!r}"

    def test_score_indices_match_original_positions(self) -> None:
        """Each HallucinationScore must have a segment_index matching its position."""
        segments = [self._make_clean_segment(f"Segment {idx}.") for idx in range(4)]

        _kept, all_scores = apply_hallucination_detection(segments)

        for expected_index, hallucination_score in enumerate(all_scores):
            assert hallucination_score.segment_index == expected_index

    def test_removed_segment_has_action_taken_removed(self) -> None:
        """Scores for removed segments must record action_taken='removed'."""
        hallucinated_segment = self._make_hallucinated_segment()

        _kept, all_scores = apply_hallucination_detection(
            [hallucinated_segment],
            score_threshold=2,
            action="remove",
        )

        assert all_scores[0].action_taken == "removed"

    def test_flagged_segment_has_action_taken_flagged(self) -> None:
        """Scores for flagged segments must record action_taken='flagged'."""
        hallucinated_segment = self._make_hallucinated_segment()

        _kept, all_scores = apply_hallucination_detection(
            [hallucinated_segment],
            score_threshold=2,
            action="flag",
        )

        assert all_scores[0].action_taken == "flagged"

    def test_empty_segment_list_returns_empty_results(self) -> None:
        """An empty input list must produce empty output with no errors."""
        kept_segments, all_scores = apply_hallucination_detection([])
        assert kept_segments == []
        assert all_scores == []
