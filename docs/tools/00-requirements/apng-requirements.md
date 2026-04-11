# Product Brief — APNG Tool

## Name and Purpose

**APNG Tool** — assembles sequences of image frames into animated PNGs (APNG). Supports per-frame timing, loop control, frame size mismatch handling, and batch operation across multiple frame directories.

**Tool type:** Generative (creates animated images from frames; no state database, no embeddings).

## Operations

1. **CLI Command** — `apng` (entry point)
2. **Single Assembly** — One directory of frames → one APNG
3. **Batch Assembly** — Multiple frame directories listed in a text file → one APNG per directory

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **Pillow** (`Pillow`) for image loading, resizing, and APNG writing.
3. No API keys required — fully local processing.
4. A changelog is maintained in `files/tools/apng/CHANGELOG.md`.

## Design Notes

- **Frame discovery:** Frames are discovered by file extension within the input directory in alphabetical order. Alphabetical ordering determines the animation sequence.
- **Frame timing:** `--duration-ms` and `--fps` are mutually exclusive. Per-frame overrides can extend specific frames.
- **Size mismatch handling:** When frames differ in dimensions, the tool applies the configured strategy relative to the first frame's dimensions.

## Command List

| Subcommand | Description |
| --- | --- |
| `apng config` | Validate and display current YAML configuration |
| `apng init` | Create config file and directory structure |

| Flag | Description |
| --- | --- |
| `--input PATH` | Directory of frame images (default: `input/`) |
| `--output PATH` | Output file path or directory (default: `data/apng/export/`) |
| `--config PATH` | YAML configuration file |
| `--batch-file PATH` | Text file listing frame directories, one per line |
| `--duration-ms INT` | Frame duration in milliseconds (mutually exclusive with `--fps`) |
| `--fps FLOAT` | Frames per second (mutually exclusive with `--duration-ms`) |
| `--loop INT` | Loop count: 0 = infinite, N = repeat N times (default: 0) |
| `--fit [fit\|crop\|stretch]` | How to handle frames that differ in size (default: `fit`) |
| `--extensions TEXT` | Comma-separated frame extensions to include (default: `png,jpg,jpeg,webp,bmp,gif`) |
| `--dry-run` | Preview frame list and settings without writing |
| `--verbose`, `-v` | Detailed logging |
| `--save-config PATH` | Generate example config and exit |
| `--version` | Show version and exit |

### Size Mismatch Modes

| Mode | Behavior |
| --- | --- |
| `fit` | Letterbox/pillarbox frame into first-frame dimensions (preserves aspect ratio) |
| `crop` | Center-crop frame to first-frame dimensions |
| `stretch` | Stretch frame to first-frame dimensions (may distort) |

## File & Output Map

```
files/tools/apng/
├── requirements.md              # This document
└── CHANGELOG.md                 # Release history

src/deep_thought/apng/
├── __init__.py
├── cli.py                       # CLI entry point
├── config.py                    # YAML config loader
└── assembler.py                 # Frame discovery, resizing, APNG assembly

src/config/
└── apng-configuration.yaml      # Tool configuration
```

## Configuration

Configuration is stored in `src/config/apng-configuration.yaml`. All values below are required unless marked optional.

```yaml
# Timing (choose one)
duration_ms: 100                 # Milliseconds per frame
# fps: 12                        # Frames per second (uncomment to use instead)

# Per-frame overrides (by frame filename or index)
frame_overrides:
  - frame: 'frame_001.png'
    duration_ms: 500             # Hold this frame for 500ms
  - frame: 'frame_010.png'
    duration_ms: 1000

# Loop
loop: 0                          # 0 = infinite; N = repeat N times

# Size mismatch
fit_mode: 'fit'                  # 'fit', 'crop', or 'stretch'

# Frame discovery
extensions:
  - png
  - jpg
  - jpeg
  - webp

# Output
output_dir: 'data/apng/export/'
```

## Data Format

### Output Structure

```
data/apng/export/
└── {animation_name}.apng        # Assembled animated PNG
```

When processing a batch file, each input directory produces one `.apng` in the output directory, named after the source directory.

### Batch File Format

```text
/path/to/frames/animation_01
/path/to/frames/animation_02
/path/to/frames/animation_03
```

One frame directory per line. Lines starting with `#` are treated as comments and skipped.

### Frame Discovery Order

Given a directory containing:
```
frame_001.png
frame_002.png
frame_003.png
```

Frames are sorted alphabetically and assembled in that order. Zero-padded numbering (e.g., `001`, `002`) ensures correct sort order for sequences larger than 9 frames.

## Error Handling

- `Pillow image loading errors` (corrupt frames, unsupported format) — caught per-animation; remaining animations in a batch continue processing.
- `Frame size mismatch errors` — caught per-animation when the configured fit mode cannot be applied; logs the offending frame and skips the animation.
- `Empty directory errors` — caught per-animation; logged and skipped when the input directory contains no matching frames.
- Top-level `try/except` in CLI entry point catches all above and prints descriptive messages.
- Exit codes: `0` all items succeeded, `1` fatal error, `2` partial failure (some items errored)

## Testing

- Mock target: **Pillow** (`PIL.Image`) — mock image loading and save operations to avoid filesystem I/O in unit tests.
- Test fixtures: sample frame image files (small PNGs of varying sizes) for integration tests.
- Test classes organized by feature area: frame discovery, size mismatch handling, batch processing, config validation.
- Mark slow or filesystem-heavy tests with `@pytest.mark.slow`.
- Mark error path tests with `@pytest.mark.error_handling`.
- Test directory: `tests/apng/` with `conftest.py` for shared fixtures
- Fixture data files stored in `tests/apng/fixtures/`
