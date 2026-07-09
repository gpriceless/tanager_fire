# Engineering Notes — 005-submission-packaging

## Verdict: READY

All file references verified against codebase. One API mismatch corrected (classify_severity → predict_severity). 5 open questions resolved. Visualization dependency (004) fully satisfied — 13 public functions, 99 tests, all wired into __init__.py.

## Parallelism

- Total sections: 8
- Sequential sections: 8
- Parallel sections: 0
- Max parallel tracks: 1
- File-disjointness: N/A — no parallel tracks

All waves are sequential with QA gates between them. Within each wave, sections are sequential because notebooks build on each other's outputs (NB02 severity → NB04 temporal trajectories, NB02 fractions → NB05 sensor comparison).

## Execution Plan

- Estimated coder spawns: 8 (one per section, sequential within waves)
- Branch strategy: feature/005-submission-packaging (single branch)
- Resource estimate: moderate (4 waves, 15 tasks, each section is one coder session)
- Wave gates: 4 mandatory QA gates between waves

## API Corrections Applied

| tasks.md Reference | Actual API | Status |
|---|---|---|
| `classify_severity()` | `predict_severity()` | FIXED in tasks.md |
| `compute_index()` (proposal only) | `nbr()`, `ndvi()`, `ndwi()` (individual functions) | Proposal-only, not in tasks.md |

## Dependency Verification: 004-visualization-overhaul

Phase 3.5 (004) is COMPLETE. All visualization functions that notebooks depend on are available:

| Function | Module | Verified |
|---|---|---|
| `plot_map()` | visualization.py:182 | ✓ |
| `plot_before_after()` | visualization.py:353 | ✓ |
| `plot_temporal_trajectory()` | visualization.py:523 | ✓ |
| `plot_severity_summary()` | visualization.py:708 | ✓ |
| `plot_difference_map()` | visualization.py:867 | ✓ |
| `interactive_map()` | visualization.py:975 | ✓ |
| `show_product()` | visualization.py:1232 | ✓ |
| `save_figure()` | visualization.py:1288 | ✓ (300 DPI default) |
| `add_basemap()` | visualization.py:1330 | ✓ |
| `load_fire_perimeters()` | visualization.py:1396 | ✓ |
| `overlay_perimeters()` | visualization.py:1433 | ✓ |
| `add_scalebar()` | visualization.py:1516 | ✓ |
| `PRODUCT_STYLES` | visualization.py:85 | ✓ |

## Existing File State

| File | Task Action | Current State |
|---|---|---|
| `pyproject.toml` | modify | dev deps ALREADY EXIST (pytest, ruff, mypy). Only add notebook group. |
| `.gitignore` | modify | .ipynb_checkpoints/, *.tif, data/raw/ ALREADY PRESENT. Only add reference DB rule. |
| `README.md` | replace | EXISTS (basic project README, needs full rewrite for competition) |
| `LICENSE` | create | DOES NOT EXIST |
| `CITATION.cff` | create | DOES NOT EXIST |
| `.github/workflows/ci.yml` | create | DOES NOT EXIST |
| `docs/api-reference.md` | create | DOES NOT EXIST |
| `notebooks/` | create dir | DOES NOT EXIST |
| `figures/` | create dir | DOES NOT EXIST |
| `Makefile` | create | DOES NOT EXIST |

## Tech Debt Affecting Notebooks

| TD | Severity | Affects | Notebook Impact |
|---|---|---|---|
| TD-7 | HIGH | NB02, NB04 | Pre-fire scene ~60km offset from post-fire. Temporal trajectory and dNBR must use overlap area. |
| TD-8 | HIGH | NB02 | MESMA fractions violate non-negativity (5-9% negative). Notebook should disclose. |
| TD-9 | MEDIUM | NB03 | SAI1660 all zeros on real data. Exclude from feature set. |
| TD-11 | HIGH | NB03 | Continuum removal too slow for full scenes. Use 256×256 crop. |
| TD-12 | MEDIUM | NB03 | SAI produces 0 instead of NaN for masked pixels. |

None of these are blockers for 005 — notebooks can work around them with crops, disclosures, and feature exclusions. All are documented as gotchas in enriched tasks.md.

## Gotchas

- `data/reference/` directory may not exist — NB01/NB03 data steps should create it
- conftest.py handles missing optional deps — CI will pass without real data
- save_figure() auto-creates parent dirs — figures/ directory created on first export
- plot_before_after() handles different spatial extents per panel — useful for TD-7 workaround
- Visualization module sits at TOP of dependency tree (alongside validation.py) — notebooks can import all tanager functions via the lazy __init__.py
