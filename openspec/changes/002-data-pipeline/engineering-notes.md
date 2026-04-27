# Engineering Notes — 002-data-pipeline

## Verdict: READY

All dependencies verified, architecture sound, tasks properly scoped. Open questions resolved. Three should-fix items noted below (not blocking).

## Parallelism

- Total waves: 3
- Wave 1 (Foundation): sequential — 5 tasks, must complete before any coding starts
- Wave 2 (Data Access + Spectral): parallel — 3 tracks (catalog.py, io.py, spectral.py band ops)
- Wave 3 (Indices + Masks + Tests): partial parallel — Tracks D+E parallel, Track F sequential after D+E
- Max parallel tracks: 3 (in Wave 2)
- File-disjointness: VERIFIED — all parallel tracks create new files with no overlap

## Execution Plan

- Estimated coder spawns: 3 sequential (Wave 1 + Wave 3 Track F) + 3 parallel (Wave 2) + 2 parallel (Wave 3 D+E) = 8 total sessions
- Branch strategy: feature/002-data-pipeline (worktrees for parallel tracks)
- Resource estimate: moderate (3 waves, up to 3 parallel coders)

## Open Question Resolutions

1. **HyperCoast version pinning:** Pin `>=0.22.0,<1.0`. 0.22.0 is latest, research tested 0.20.2. The <1.0 cap protects against breaking changes.
2. **Data directory convention:** `data/raw/fire/` with `.gitkeep`. Existing `.gitignore` already covers `data/raw/`. Env override via `TANAGER_DATA_DIR`. Files use `.h5` extension.
3. **SPy vs mesma package:** Confirmed deferred to Phase 3. Phase 2 only needs SPy for band math and indices.

## Enrichment Changes (this pass)

1. **Added `tests/test_io.py` task** — spec has 4 scenarios for io.py (load scene, band subset, spatial info, invalid file) but Track F had no io test. Added mocked test covering all scenarios.
2. **Added network dependency annotations** — every section and verify task now has `<!-- network: -->` tags indicating whether internet access is required.
3. **Added scipy dependency note** — continuum removal uses `scipy.spatial.ConvexHull`; noted in task gotcha and engineering-memory.md dependencies.
4. **Added open questions RESOLVED section** — tasks.md header now explicitly records resolved answers.
5. **Updated parallel safety check for Wave 3** — Track F file list now includes `tests/test_io.py`.

## Gotchas

1. **Scene count ambiguity (11 vs 12):** Data access evaluation lists 11 named scene IDs, proposal says 12. The coder building config.py should query the live STAC catalog for the authoritative count and record it. Not blocking — the FIRE_SCENES list will be corrected at build time.

2. **HyperCoast wavelength_range loading:** HyperCoast's `read_tanager()` accepts `bands` (integer indices), not wavelength ranges. The io.py `load_scene(filepath, wavelength_range)` task must load all bands then slice, or resolve wavelengths to indices first. Documented in task gotcha.

3. **cloud_mask HDF5 access:** HyperCoast may not expose `beta_cirrus_mask` in the xarray output. The coder may need to open the raw HDF5 with h5py directly. h5py added to dependencies.

4. **Continuum removal floating-point:** Convex hull continuum removal can produce values slightly > 1.0 at hull vertices. Clip to [0, 1].

5. **Circular dependency risk:** masks.py will import ndwi from spectral.py. This is fine as long as spectral.py never imports from masks.py. This constraint is documented in engineering-memory.md.

6. **spyndex version drift:** Research noted spyndex 0.6.0 but current latest is 0.10.0. The spyndex package is used as a reference/validation tool, not a core dependency for index computation (we compute indices directly). No version conflict.

7. **scipy dependency:** continuum_removal needs `scipy.spatial.ConvexHull`. scipy must be added to pyproject.toml dependencies. Noted in the continuum_removal task.

## Dependency Addition

Added `h5py` to the dependency list. Required for masks.py cloud_mask function to read beta_cirrus_mask from raw HDF5 files when HyperCoast doesn't expose it.

Added `scipy` to the dependency list. Required for spectral.py continuum_removal function (ConvexHull).
