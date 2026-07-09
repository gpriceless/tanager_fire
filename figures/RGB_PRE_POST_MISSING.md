# rgb_pre_post.png — not yet generated

`tasks.md` (Section 8, Phase 4) lists `rgb_pre_post.png` as one of the minimum
required figures for `figures/`, but no such file exists in `outputs/` or
anywhere else in the repo to copy into place.

## Why it's missing

Notebook `notebooks/01-data-discovery.ipynb` renders true-color pre-fire and
post-fire RGB quicklooks inline (see cells around the "Quicklooks" section,
using red=660nm/green=560nm/blue=470nm with a per-channel percentile stretch),
but it never calls `tanager.save_figure()` (or `plt.savefig()`) to persist
that composite to `outputs/`. Every other figure in `figures/` was produced by
copying an already-saved `outputs/notebookNN_*.png` file (see `Makefile`
`figures` target); this one has no equivalent source file because the
notebook was never updated to export it.

## What's needed to close this gap

1. Add a `save_figure(fig, "../outputs/notebook01_rgb_pre_post", ["png"])`
   call (or equivalent) to the quicklook cell in
   `notebooks/01-data-discovery.ipynb`.
2. Re-run the notebook (`make notebooks` or
   `jupyter nbconvert --execute --to notebook --inplace notebooks/01-data-discovery.ipynb`)
   so it writes `outputs/notebook01_rgb_pre_post.png`.
3. Copy that output into `figures/rgb_pre_post.png` (and add the
   corresponding line to the `figures` target in `Makefile` so future runs
   produce it automatically).
4. Delete this note once `figures/rgb_pre_post.png` exists.

Tracked as a follow-up gap from the Phase 4 Closer rejection
(openspec/changes/005-submission-packaging).
