# Multi-Repo Tooling Strategy

## Machine

**MacBook Pro, M4 Pro** — primary and only development machine. All three repos live and run here.

| Spec | Detail |
|---|---|
| Chip | Apple M4 Pro |
| Memory | 48GB unified |

---

## Repositories and Their Relationships

Three repositories make up the full system. Deep-thought is the canonical source for all tool code. They must be set up in this order.

```
deep-thought  ──symlink──▶  magrathea
                   └────────▶  quiet-evolution
```

### 1. deep-thought

The Python development repo. All tool source code lives here. Builds, tests, and quality checks happen here.

- **Location:** `/Users/williamtrekell/Documents/dont-panic/deep-thought/`
- **Tool source:** `src/deep_thought/`

### 2. magrathea

Private content and article production repo. Accesses deep-thought tool code via a symlink — no code duplication.

- **Location:** `/Users/williamtrekell/Documents/dont-panic/magrathea/`
- **Symlinks (must be created manually after clone):**

| Symlink | Target |
|---------|--------|
| `src/deep_thought/` | `../../deep-thought/src/deep_thought/` |
| `00-reference/10-dt-docs/` | `../../deep-thought/docs/` |
| `00-reference/10-dt-files/` | `../../deep-thought/files/` |

- **Config:** `src/config/` — magrathea-specific tool configurations
- **CLI entry points:** defined in `pyproject.toml`, pointing into the symlinked source

Because `src/deep_thought/` is a symlink to deep-thought, any changes to tool code are immediately reflected in magrathea with no additional steps.

### 3. quiet-evolution

Public content repo. Will use a subset of tools. Same symlink pattern as magrathea.

- **Location:** `/Users/williamtrekell/Documents/quiet-evolution/`
- **Working tree:** not checked out on disk — setup needed
- **Symlink in git:** `src/deep_thought → ../../deep-thought/src/deep_thought/` — relative path may need adjustment given quiet-evolution sits one directory level shallower than magrathea

---

## AI Tool Roles

| Tool | Role |
|---|---|
| **Claude Code** | Development environment — where the system is built and reasoned about. Billed against Anthropic subscription. |
| **Gemini CLI** | Interactive AI for tasks that don't need to be automated — research, drafting, summarizing. Offloads work that would otherwise cost Claude API usage. 1,000 requests/day free via Google account. |
| **Gemini API** | Lightweight in-tool AI — summarizing, extracting, classifying within built tools. 250 requests/day free on Flash. |
| **Claude API / other paid** | Reserved for in-tool AI that needs more capability than Gemini Flash can deliver. |

The goal is to keep Claude Code focused on building, and route everything else to the cheapest tier that can handle it.

---

## Python Environment

**Python 3.12** is the minimum required version.

**uv** is the package manager. It handles creating virtual environments, resolving and installing dependencies, and exposing CLIs system-wide. It replaces pip, pip-tools, and virtualenv.

```bash
# Install uv (once, system-wide)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create the virtual environment and install all dependencies
uv sync
```

The virtual environment lives at `.venv/` in the project root and is never committed to git.

---

## Core Development Libraries

| Library | Role |
|---|---|
| `ruff` | Linter and formatter — replaces flake8, isort, and black in one tool |
| `mypy` | Static type checker — strict mode enforced |
| `pytest` | Test runner |
| `pytest-cov` | Coverage reporting, wired into pytest automatically |

These are dev-only dependencies — they are not included when the package is installed in consuming repos.

---

## How They Connect

```
Source code (src/)
      │
      ├── ruff check .                              → catches lint errors and style issues
      ├── ruff format .                             → enforces consistent formatting
      ├── mypy --python-executable .venv/bin/python src/   → verifies all type annotations are correct
      └── pytest                                    → runs tests, reports coverage
```

Each tool operates independently on the source code. The intended order is lint → format → type check → test. Running them out of order is fine, but a failure at any step is worth fixing before moving on.

---

## Configuration

All tool configuration lives in `pyproject.toml` — no separate config files needed.

- `ruff` is configured under `[tool.ruff]` — line length, target Python version, which rule sets to enforce
- `mypy` is configured under `[tool.mypy]` — strict mode, type annotation requirements
- `pytest` is configured under `[tool.pytest.ini_options]` — test discovery paths, coverage settings, custom markers

---

## Non-Python Tooling

### Prettier

Formats markdown, YAML, JSON, and other non-Python files. Requires Node.js.

```bash
npm install --save-dev prettier
```

Run via npm scripts defined in `package.json`:

```bash
npm run format        # format in place
npm run format:check  # check without writing (useful in CI)
```

Configuration lives in `.prettierrc` or `package.json` under `"prettier"`.

### Vale

Lints prose — checks writing style, grammar, and consistency in markdown files. Distributed as a standalone Go binary with no runtime dependencies.

```bash
brew install vale
```

Vale uses style rules defined in YAML files pulled from the Vale package registry. Configuration lives in `.vale.ini` at the repo root. All three repos use the same three styles:

| Style | Purpose |
|---|---|
| `write-good` | Catches weak and passive writing |
| `alex` | Flags insensitive or inconsiderate language |
| `proselint` | Catches redundancies, jargon, and common writing mistakes |

### Lint Config

Vale and Prettier are run together via a single `npm run lint` command. A `lint.config.yaml` at the repo root controls which directories they check:

```yaml
# Directories to check with Vale and Prettier
# Override at runtime: npm run lint -- path/to/check
paths:
  - docs/
  - content/
```

```bash
npm run lint           # uses paths from lint.config.yaml
npm run lint -- path/  # overrides with a specific path
```

---

## Pre-Commit Safety Hook

A git pre-commit hook blocks commits if tests fail.

Create `.git/hooks/pre-commit`:

```bash
#!/bin/sh
echo "Running tests before commit..."
.venv/bin/python -m pytest --no-cov -q

if [ $? -ne 0 ]; then
    echo ""
    echo "Tests failed. Commit blocked."
    echo "Fix the failures above, then try committing again."
    exit 1
fi
```

Make it executable:

```bash
chmod +x .git/hooks/pre-commit
```

The `--no-cov` flag skips coverage reporting to keep the hook fast. This file lives in `.git/hooks/` which git does not track — must be run as part of setup on any machine.

---

## Sharing Tools Across Repos

Tool source code is shared via symlinks, not installation or duplication. The single copy lives in `deep-thought/src/deep_thought/`. Consuming repos point into it.

```bash
# magrathea (run from magrathea root)
ln -s ../../deep-thought/src/deep_thought src/deep_thought
ln -s ../../deep-thought/docs 00-reference/10-dt-docs
ln -s ../../deep-thought/files 00-reference/10-dt-files

# quiet-evolution (run from quiet-evolution root — verify relative path)
ln -s ../dont-panic/deep-thought/src/deep_thought src/deep_thought
```

Symlinks must be created manually after cloning. They are not tracked by git.

---

## SSH Keys

Required before cloning any private repo from GitHub. Generate and add the public key to GitHub.

```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
# Add ~/.ssh/id_ed25519.pub to GitHub → Settings → SSH Keys
```

Test the connection before attempting any clones:

```bash
ssh -T git@github.com
```

---

## Brewfile

Instead of installing Homebrew packages one by one, a `Brewfile` at the repo root lists everything. One command installs it all:

```bash
brew bundle
```

| Package | Purpose |
|---|---|
| `git` | Version control |
| `gh` | GitHub CLI — PR and issue management |
| `nvm` | Node.js version manager |
| `vale` | Prose linter |
| `tmux` | Terminal session persistence |
| `yq` | YAML parser — required by the lint shell script |
| `ripgrep` | Fast search — used by Claude Code |
| `jq` | JSON parser — used in shell scripts |
| `gitleaks` | Scans repos for accidentally committed secrets |
| `git-lfs` | Large file storage for git |

uv is installed separately via its own curl script since it's not distributed through Homebrew. Node.js itself is installed via nvm after Homebrew runs.

---

## Node.js Version

Node.js version is pinned in `.nvmrc` at the repo root. Install nvm first, then:

```bash
nvm install   # reads .nvmrc and installs the correct version
nvm use       # activates it
```

nvm requires shell config in `~/.zshrc`:

```bash
export NVM_DIR="$HOME/.nvm"
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"
[ -s "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm" ] && \. "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm"
```

---

## .gitignore Baseline

All three repos share the same baseline of what never gets committed:

```
.venv/
node_modules/
data/
__pycache__/
*.pyc
.coverage
htmlcov/
00-*
```

---

## Setup Order

### Requires your presence

These steps cannot be scripted. Do them first, in order, before handing anything off.

1. Sign into iCloud — secrets stored in macOS Keychain sync automatically via iCloud
2. Generate SSH keys and add the public key to GitHub — nothing can be cloned without this
3. Install Homebrew — run the curl installer from brew.sh

---

### What the repo provides

These files are committed to deep-thought.

| File | Purpose |
|---|---|
| `05-tools/spec/multi-repo-tooling.md` | This document — the full setup guide |
| `Brewfile` | System-level tools to install via `brew bundle` |
| `.nvmrc` | Pinned Node.js version |
| `.gitignore` | Baseline of what never gets committed |
| `pyproject.toml` | Package definition, dependencies, and tooling config |
| `CLAUDE.md` | Instructions for Claude Code instances working in this repo |

---

### deep-thought (scripted)

1. `brew bundle` — installs all Brewfile entries
2. `nvm install` and `nvm use` — activates the pinned Node.js version
3. `npm install -g @anthropic-ai/claude-code` — Claude Code CLI
4. `npm install -g @google/gemini-cli` — Gemini CLI
5. Install uv via its own curl script
6. `uv sync` — installs Python 3.12 and all dependencies into `.venv/`
7. Install the pre-commit hook
8. Create symlinks (see **Sharing Tools Across Repos**)

---

### magrathea and quiet-evolution (scripted)

Each repo has its own setup. Clone the repo, then:

1. `nvm install` and `nvm use`
2. `npm install` — installs Prettier
3. Create `lint.config.yaml`
4. Create `.vale.ini` — write-good, alex, proselint
5. Create symlinks to deep-thought (see **Sharing Tools Across Repos**)

---

### Requires your presence (final)

Verify all tools can authenticate correctly — secrets come from Keychain via iCloud.

---

## TODO

- **quiet-evolution setup** — check out working tree, verify symlink path, determine which tools it needs, create tool configs
- **Brewfile** — create at repo root (currently only documented here)
- **Claude Code config** — `~/.claude/` contents (MCP servers, settings, hooks) need a home in the repo
- **Git config** — name, email, and default branch should be called out in setup order
