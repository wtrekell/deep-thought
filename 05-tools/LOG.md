# Log

## 260402 (session 1)

- Created `05-tools/` as the rebuild workspace for the deep-thought tool suite
- Created `spec/multi-repo-tooling.md` — full system design covering machine specs, repo relationships, AI tool roles, Python environment, non-Python tooling (Prettier, Vale, lint config), pre-commit safety hook, Brewfile, SSH keys, secrets strategy (macOS Keychain via iCloud), and setup order
- Decided to rebuild in `05-tools/` instead of `src/` to align directory structure with consuming repos
- Removed hub, git-extras, python@3.14 from Homebrew
- Secrets stored in macOS Keychain, paths set via `.zshrc` — no `.env` files
- Established worktree-based workflow: tools built one at a time, validated, merged to main
- Cycled SSH key (`id_ed25519_personal`), added new public key to GitHub, verified connection

## 260402 (session 2)

- Decided to build in place (`src/deep_thought/`) on same laptop; current tools stay working until replaced
- Confirmed tool sharing model: `magrathea/src/deep_thought/` is a symlink to `deep-thought/src/deep_thought/` — single source, no duplication; quiet-evolution uses same pattern
- Updated `spec/multi-repo-tooling.md`: corrected repo relationships, symlink architecture, removed Mac mini/Tailscale content, restored all reference sections
- Installed missing Homebrew packages: `nvm`, `tmux`, `yq`, `ripgrep`, `jq`
- Created `~/.nvm` directory and added nvm shell config to `~/.zshrc`
- quiet-evolution working tree not checked out on disk; symlink path needs verification before setup
- Brewfile not yet created — still only documented in `multi-repo-tooling.md`
