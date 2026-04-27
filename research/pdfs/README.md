# research/pdfs/

Human-staged PDFs for papers that research agents cannot fetch directly (paywalled, Cloudflare-blocked, or behind login walls).

## Purpose

Some publishers consistently block server-side fetchers (Elsevier/ScienceDirect, MDPI, Nature landing pages, etc.). When an agent reports a paper as `paywalled — manual download needed`, a human downloads the PDF from a credentialed browser session and drops it in this directory. Agents then read from disk instead of WebFetching.

See `/AGENTS.md` ("Research Sourcing Strategy") for the full sourcing priority order.

## Staging Conventions

- **Filename:** `<first-author-last>_<year>_<short-title-slug>.pdf`
  - Example: `roberts_1998_mesma-spectral-mixture-analysis.pdf`
  - Example: `key_2006_landscape-burn-severity-cbi.pdf`
- **One paper per file.** No combined PDFs.
- **Original publisher PDF** preferred. Preprint versions (arXiv etc.) only if no publisher PDF is available — note the version in the filename when ambiguous (e.g., `_preprint`).
- **Do not commit** these PDFs to git unless licensing permits. This directory is gitignored by default; add a `.gitkeep` here so the directory itself stays tracked.

## How Agents Use This Directory

When an agent needs a paper:

1. Check `research/pdfs/` first (priority 4 in the sourcing strategy).
2. If a matching PDF exists, read it via the `Read` tool — do not fetch it.
3. If no PDF exists and other open-access paths fail, skip the paper and report it as `paywalled — manual download needed: <citation>` in the agent's output so a human can stage it on the next pass.

## Currently Staged

_(none yet — populate as papers are downloaded)_
