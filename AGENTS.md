# AGENTS

- Stack: Hugo static site. Keep it static.
- Edit source, not generated output: `content/`, `layouts/`, `themes/dark-minimal/`, `hugo.toml`.
- Verify locally with: `hugo --cleanDestinationDir --panicOnWarning && python3 scripts/check_site.py public`
- Dev preview: `hugo server --bind 127.0.0.1 --port 1313 --disableFastRender --destination .local/preview`
- Public setup is documented in `SETUP.md`; private deployment notes belong in ignored `.local/DEPLOYMENT.md`.
- Do not scan old `/wiki` content trees or anything similar; searches should stay scoped to this repo unless deploy config is explicitly needed.
- The site had stale generated output before; if links look wrong, do a clean Hugo rebuild first.
