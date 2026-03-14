# Cross-Repo Symlinks for Shared Resources

## Goal

Enable multiple local repositories to access shared tools and sensitive configuration from a single source of truth, without duplicating files or committing secrets to any public repo.

## Proposed Architecture

A private repository (not yet built) would serve as the central store for:

- **Shared tools** — scripts, utilities, or modules used across repos
- **Sensitive configuration** — API tokens, credentials, environment files
- **Shared templates** — common config patterns, shared CLAUDE.md fragments

Local symlinks from each consuming repo would point into the private repo, keeping all operations local with no network dependency.

### Example Layout

```
~/Documents/
  private-repo/          # Private, never pushed to public remote
    secrets/
      .env.deep-thought
      .env.rlyeh
    tools/
      shared_utility.py
  deep-thought/          # Public repo
    .env -> ../private-repo/secrets/.env.deep-thought
    shared/ -> ../private-repo/tools/
  r'lyeh/                # Public repo
    .env -> ../private-repo/secrets/.env.rlyeh
```

## Benefits

- Single source of truth for secrets and shared tools
- No duplication, no drift between repos
- Secrets never exist inside a git-tracked directory
- Fully local — no cloud secrets manager required
- Symlinks are lightweight and easy to set up

## Considerations

- **Gitignore the symlinks** — add symlink targets to `.gitignore` so git never tracks or follows them
- **Document the setup** — new machine setup requires creating the private repo and symlinks manually; a bootstrap script would help
- **Relative vs absolute paths** — relative symlinks (e.g., `../private-repo/`) are portable across users if directory structure is consistent; absolute paths break on other machines
- **Broken symlinks fail loudly** — if the private repo is missing, tools error immediately rather than silently using stale data, which is the right behavior

## Recommendations

- **Keep the private repo git-initialized** even if it never has a remote — this gives you version history on secrets rotation and tool changes
- **Use a setup script** — a single shell script in each consuming repo that creates the expected symlinks and validates they resolve; run it once per machine
- **Pair with keychain storage** — symlinked `.env` files are still plaintext on disk; combining this pattern with the keychain enhancement (see `keychain-secret-storage.md`) would eliminate plaintext secrets entirely while keeping shared tools accessible via symlinks
- **Avoid symlinking into `src/`** — shared Python modules pulled in via symlink can confuse type checkers and build tools; prefer adding the private repo to `PYTHONPATH` or using editable installs instead

## Scope

Affects repository setup and onboarding documentation. No changes to application code unless shared Python modules need import path adjustments.
