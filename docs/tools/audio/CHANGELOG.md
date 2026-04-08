# Changelog — Audio Tool

All notable changes to the audio tool will be documented in this file.

## [Unreleased]

### Changed

- HuggingFace token retrieval now checks macOS Keychain first, falling back to environment variables. Uses the shared `deep_thought.secrets` module.

### Added

- Cross-segment bigram/trigram hallucination check in `hallucination.py`: all segment texts in the detection window are now concatenated and scanned for n-gram repetition across segment boundaries, complementing the existing within-segment check. Threshold scales with window size (`max(1, len(segments) // 2)`) to reduce false positives; effective when `window_size >= 4` (default is 10).

### Changed

- Renamed `requirements.md` to `260322-requirements.md` to follow repository naming convention.
