"""Endmember library construction for Tanager-1 hyperspectral unmixing.

This module assembles a fire-relevant endmember library from multiple spectral
sources (USGS v7 splib07, ECOSTRESS, FRAMES SoCal, image-derived) and produces
a single resampled, pruned library ready for MESMA spectral unmixing.

Public API (import lazily via ``tanager`` package):

* :func:`load_usgs_library` — USGS v7 spectra via splib07-loader
* :func:`load_ecostress_library` — ECOSTRESS spectra via SPy ``EcostressDatabase``
* :func:`load_frames_library` — FRAMES SoCal ASCII spectra (chaparral fire fuels)
* :func:`resample_library` — convolve to Tanager 426-band centres with Gaussian FWHM
* :func:`build_hybrid_library` — merge multiple sources with source tracking
* :func:`select_endmembers_incob` — count-based subset selection per class
* :func:`prune_endmembers_ear_masa` — EAR/MASA pruning via spectral-libraries
* :func:`extract_image_endmembers` — spatial ROI or PPI extraction from a scene
* :func:`build_fire_library` — convenience orchestrator producing the final library

All loaders return ``xarray.DataArray`` with dims ``(spectrum_id, wavelength)``,
the ``wavelength`` coordinate in nanometres, and per-spectrum metadata stored
in a parallel ``DataArray.coords["category"]``, ``coords["source"]``, and
``coords["name"]``. Reflectance values are in ``[0, 1]``.

This module imports from :mod:`tanager.config` and :mod:`tanager.spectral` only.
It must not import from :mod:`tanager.io` or :mod:`tanager.masks`.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import xarray as xr

if TYPE_CHECKING:  # avoid pulling rasterio/geopandas at module import time
    pass

logger = logging.getLogger(__name__)

# Reflectance is clipped to this range after every resample / merge step. Lab
# spectra (USGS, ECOSTRESS) are calibrated to [0, 1] but Gaussian convolution at
# absorption edges can produce small negative or > 1 values that propagate into
# MESMA as artefacts.
_REFLECTANCE_MIN = 0.0
_REFLECTANCE_MAX = 1.0

# Default per-band FWHM (nm) for the Tanager-1 sensor when a scene's per-band
# FWHM is not available. Tanager FWHM varies 5.20-6.81nm across the spectrum
# (Phase 2 finding); 5.5 is the nominal value documented in the sensor spec.
_DEFAULT_TARGET_FWHM_NM = 5.5

# Default source FWHM (nm) for ASD lab spectrometers used by USGS / ECOSTRESS /
# FRAMES (~1nm sampling, deconvolved).
_DEFAULT_SOURCE_FWHM_NM = 1.0

# Names of the categories the fire library is built around. The ordering is
# meaningful: it is used as the canonical class order in the merged library
# and downstream MESMA outputs.
FIRE_CATEGORIES: Tuple[str, ...] = ("char", "ash", "pv", "npv", "soil", "shade")

# Source identifiers attached to each spectrum so downstream code can audit
# provenance after libraries are merged. Match the spec scenarios.
SourceTag = str  # "usgs_v7" | "ecostress" | "frames" | "image" | "synthetic"


# ---------------------------------------------------------------------------
# Internal helpers shared across loaders
# ---------------------------------------------------------------------------


def _build_library_dataarray(
    reflectance: np.ndarray,
    wavelengths_nm: np.ndarray,
    spectrum_ids: Sequence[str],
    names: Sequence[str],
    categories: Sequence[str],
    source: SourceTag,
) -> xr.DataArray:
    """Assemble the canonical ``(spectrum_id, wavelength)`` DataArray.

    Args:
        reflectance: 2D array shape ``(n_spectra, n_wavelengths)``. Values
            outside ``[0, 1]`` are clipped.
        wavelengths_nm: 1D array of wavelength centres in nanometres.
        spectrum_ids: Unique spectrum identifiers, length ``n_spectra``.
        names: Human-readable names, length ``n_spectra``.
        categories: Per-spectrum category strings, length ``n_spectra``.
        source: Source tag applied to all spectra.

    Returns:
        An ``xarray.DataArray`` with dims ``(spectrum_id, wavelength)``,
        wavelength coordinate in nm, and parallel coordinate arrays for
        ``name``, ``category``, and ``source`` along the spectrum_id axis.
    """
    if reflectance.ndim != 2:
        raise ValueError(
            f"reflectance must be 2D (n_spectra, n_wavelengths), got shape {reflectance.shape}"
        )
    n_spectra, n_wavelengths = reflectance.shape
    if len(spectrum_ids) != n_spectra:
        raise ValueError("spectrum_ids length must match reflectance.shape[0]")
    if len(names) != n_spectra:
        raise ValueError("names length must match reflectance.shape[0]")
    if len(categories) != n_spectra:
        raise ValueError("categories length must match reflectance.shape[0]")
    if wavelengths_nm.shape != (n_wavelengths,):
        raise ValueError("wavelengths_nm must be 1D of length reflectance.shape[1]")

    reflectance = np.clip(np.asarray(reflectance, dtype=np.float32), _REFLECTANCE_MIN, _REFLECTANCE_MAX)

    return xr.DataArray(
        reflectance,
        dims=("spectrum_id", "wavelength"),
        coords={
            "spectrum_id": np.asarray(spectrum_ids, dtype=object),
            "wavelength": np.asarray(wavelengths_nm, dtype=np.float32),
            "name": ("spectrum_id", np.asarray(names, dtype=object)),
            "category": ("spectrum_id", np.asarray(categories, dtype=object)),
            "source": ("spectrum_id", np.asarray([source] * n_spectra, dtype=object)),
        },
        attrs={"reflectance_range": (_REFLECTANCE_MIN, _REFLECTANCE_MAX)},
    )


def _read_usgs_ascii_column(path: Path) -> np.ndarray:
    """Read a single-column USGS splib07 ASCII file into a 1D float array.

    USGS splib07 files store one floating-point value per line, with a one-line
    header containing the spectrum description. Missing values are encoded as
    ``-1.23e34`` (the USGS sentinel) and converted to ``np.nan`` here.

    Args:
        path: Filesystem path to the ASCII file.

    Returns:
        1D ``np.ndarray`` of floats with USGS sentinel values replaced by NaN.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the file contains no numeric data.
    """
    values: list[float] = []
    with open(path, "r", encoding="latin-1") as handle:
        first = True
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            # Skip the descriptive header on the first line if it is not numeric.
            if first:
                first = False
                try:
                    float(stripped.split()[0])
                except (ValueError, IndexError):
                    continue
            try:
                values.append(float(stripped.split()[0]))
            except (ValueError, IndexError):
                # Tolerate stray comment lines without aborting.
                continue
    if not values:
        raise ValueError(f"No numeric data found in USGS ASCII file: {path}")
    arr = np.asarray(values, dtype=np.float32)
    # USGS sentinel for missing values is -1.23e34 (Clark et al. 2007).
    arr[arr <= -1.0e30] = np.nan
    return arr


def _detect_usgs_wavelength_file(data_dir: Path, sensor_hint: str = "ASD") -> Path:
    """Find the splib07a wavelength index file for a given sensor convolution.

    Args:
        data_dir: Directory containing USGS splib07 ASCII files (recursive search).
        sensor_hint: Substring to disambiguate sensors (e.g. ``"ASD"`` for the
            full-resolution 2151-channel Field Spec spectra).

    Returns:
        Path to the matching ``splib07a_Wavelengths_*<sensor_hint>*.txt`` file.

    Raises:
        FileNotFoundError: If no wavelength file matches the hint.
    """
    candidates = sorted(data_dir.rglob("*Wavelengths*"))
    matches = [p for p in candidates if sensor_hint.upper() in p.name.upper() and p.is_file()]
    if not matches:
        raise FileNotFoundError(
            f"No splib07a wavelength file with sensor hint {sensor_hint!r} found under {data_dir}"
        )
    return matches[0]


def load_usgs_library(
    categories: Optional[Sequence[str]] = None,
    data_dir: Optional[Union[str, os.PathLike]] = None,
    *,
    sensor_hint: str = "ASD",
    category_map: Optional[Mapping[str, str]] = None,
) -> xr.DataArray:
    """Load USGS splib07a spectra from local ASCII files.

    splib07-loader is incompatible with numpy 2.x (it pins ``nptyping`` against
    ``numpy<2.0`` which forces a downgrade that breaks rasterio and rioxarray),
    so this function parses the raw ASCII archive directly. Download
    ``ASCIIdata_splib07a.zip`` from `USGS ScienceBase
    <https://doi.org/10.5066/F7RR1WDJ>`_ and extract to ``data_dir``.

    The function discovers files matching ``s07ASD_*.txt`` (or whatever
    ``sensor_hint`` selects) and a paired wavelength index file
    (``splib07a_Wavelengths_*ASD*.txt``). Each spectrum file is one column of
    reflectance values; the wavelength file is one column of micrometre values.

    Args:
        categories: Optional iterable of category strings to keep. If ``None``,
            all spectra are returned. Categories come from ``category_map`` or
            from filename heuristics (substring match against
            :data:`FIRE_CATEGORIES`).
        data_dir: Directory containing the extracted splib07a ASCII tree. May be
            a string or ``os.PathLike``.
        sensor_hint: Substring used to select both the wavelength file and the
            spectrum files. Defaults to ``"ASD"`` (Field Spec, 2151 channels).
        category_map: Optional mapping from filename (without directory or
            extension) to a category string. Overrides filename heuristics.

    Returns:
        ``xr.DataArray`` with dims ``(spectrum_id, wavelength)``, wavelength
        coordinate in nanometres, and per-spectrum coords ``name``, ``category``,
        ``source`` (set to ``"usgs_v7"``). Reflectance values are clipped to
        ``[0, 1]``. Spectra that are entirely NaN within the VSWIR window
        (380-2500nm) are dropped.

    Raises:
        FileNotFoundError: If ``data_dir`` does not exist or no spectrum files
            match ``sensor_hint``.
        ValueError: If the wavelength file length disagrees with spectrum
            files, or all spectra are filtered out.
    """
    if data_dir is None:
        raise FileNotFoundError(
            "data_dir is required. Download ASCIIdata_splib07a.zip from "
            "USGS ScienceBase (DOI:10.5066/F7RR1WDJ) and extract it locally."
        )
    root = Path(data_dir).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(f"USGS splib07 data_dir does not exist: {root}")

    wl_path = _detect_usgs_wavelength_file(root, sensor_hint=sensor_hint)
    wavelengths_um = _read_usgs_ascii_column(wl_path)
    wavelengths_nm = wavelengths_um * 1000.0  # USGS files store micrometres

    pattern = re.compile(rf"s07[a-z0-9]*{re.escape(sensor_hint)}", re.IGNORECASE)
    spectrum_paths = sorted(p for p in root.rglob("*.txt") if pattern.search(p.name) and p != wl_path)
    if not spectrum_paths:
        raise FileNotFoundError(
            f"No spectrum files matching sensor hint {sensor_hint!r} found under {root}"
        )

    keep_categories = set(c.lower() for c in categories) if categories is not None else None

    rows: list[np.ndarray] = []
    spectrum_ids: list[str] = []
    names: list[str] = []
    cats: list[str] = []

    vswir_mask = (wavelengths_nm >= 380.0) & (wavelengths_nm <= 2500.0)

    for path in spectrum_paths:
        try:
            refl = _read_usgs_ascii_column(path)
        except ValueError:
            logger.warning("USGS spectrum file %s contains no numeric data; skipping", path.name)
            continue
        if refl.shape != wavelengths_nm.shape:
            logger.warning(
                "USGS spectrum %s has %d points; wavelength file has %d. Skipping.",
                path.name, refl.shape[0], wavelengths_nm.shape[0],
            )
            continue
        if np.all(np.isnan(refl[vswir_mask])):
            logger.info("USGS spectrum %s is all-NaN in VSWIR; dropping.", path.name)
            continue

        stem = path.stem
        if category_map is not None and stem in category_map:
            cat = category_map[stem].lower()
        else:
            cat = _guess_category_from_filename(stem)

        if keep_categories is not None and cat not in keep_categories:
            continue

        rows.append(np.nan_to_num(refl, nan=0.0))
        spectrum_ids.append(f"usgs_{cat}_{len(rows):04d}")
        names.append(stem)
        cats.append(cat)

    if not rows:
        raise ValueError(
            f"No USGS spectra survived filtering (categories={categories}, sensor={sensor_hint})"
        )

    reflectance = np.vstack(rows).astype(np.float32)
    return _build_library_dataarray(
        reflectance=reflectance,
        wavelengths_nm=wavelengths_nm,
        spectrum_ids=spectrum_ids,
        names=names,
        categories=cats,
        source="usgs_v7",
    )


# ---------------------------------------------------------------------------
# Library merge with source tracking
# ---------------------------------------------------------------------------


def build_hybrid_library(
    usgs: Optional[xr.DataArray] = None,
    ecostress: Optional[xr.DataArray] = None,
    frames: Optional[xr.DataArray] = None,
    image_derived: Optional[xr.DataArray] = None,
) -> xr.DataArray:
    """Merge multiple endmember libraries into a single DataArray.

    All inputs must already share the same wavelength grid (i.e. be the output
    of :func:`resample_library` against the same target). The resulting
    DataArray concatenates spectra along the ``spectrum_id`` axis and carries
    a per-spectrum ``source`` coordinate so callers can audit provenance after
    merging.

    Args:
        usgs: USGS-derived library (output of ``load_usgs_library`` →
            ``resample_library``) or ``None`` if unavailable.
        ecostress: ECOSTRESS-derived library or ``None``.
        frames: FRAMES SoCal library or ``None``.
        image_derived: Image-derived endmembers (output of
            :func:`extract_image_endmembers` → :func:`resample_library`) or
            ``None``.

    Returns:
        Merged ``xr.DataArray`` with dims ``(spectrum_id, wavelength)``.
        Spectra retain their original ``name``, ``category``, and ``source``
        coordinate values.

    Raises:
        ValueError: If all inputs are ``None`` or if the wavelength grids of
            the supplied inputs disagree.
    """
    inputs = [arr for arr in (usgs, ecostress, frames, image_derived) if arr is not None]
    if not inputs:
        raise ValueError("build_hybrid_library: at least one input library must be non-None")

    reference_wavelengths = np.asarray(inputs[0].coords["wavelength"].values, dtype=np.float32)
    for arr in inputs[1:]:
        wls = np.asarray(arr.coords["wavelength"].values, dtype=np.float32)
        if wls.shape != reference_wavelengths.shape or not np.allclose(wls, reference_wavelengths, atol=1e-3):
            raise ValueError(
                "build_hybrid_library: all inputs must share the same wavelength grid; "
                "call resample_library() with the same target first"
            )

    merged = xr.concat(inputs, dim="spectrum_id")
    # Make spectrum_id values unique by suffixing duplicates.
    seen: dict[str, int] = {}
    new_ids: list[str] = []
    for sid in merged.coords["spectrum_id"].values.tolist():
        if sid in seen:
            seen[sid] += 1
            new_ids.append(f"{sid}_dup{seen[sid]}")
        else:
            seen[sid] = 0
            new_ids.append(sid)
    merged = merged.assign_coords(spectrum_id=("spectrum_id", np.asarray(new_ids, dtype=object)))

    # Re-clip in case any input slipped past the [0, 1] guard.
    merged.values[:] = np.clip(merged.values, _REFLECTANCE_MIN, _REFLECTANCE_MAX)
    return merged


# ---------------------------------------------------------------------------
# Resampling to Tanager bands
# ---------------------------------------------------------------------------


def resample_library(
    library: xr.DataArray,
    target_wavelengths: np.ndarray,
    *,
    fwhm: Union[float, np.ndarray] = _DEFAULT_TARGET_FWHM_NM,
    source_fwhm: Union[float, np.ndarray] = _DEFAULT_SOURCE_FWHM_NM,
) -> xr.DataArray:
    """Resample an endmember library to a target wavelength grid via SPy.

    Uses :class:`spectral.BandResampler` for Gaussian-convolution-based
    spectral resampling. Per the Phase 2 finding that Tanager's per-band FWHM
    varies 5.20-6.81 nm across the spectrum, this function accepts either a
    scalar or a per-band array for ``fwhm``. When a scene Dataset's
    ``coords["fwhm"]`` is available, prefer passing it as the per-band array.

    Args:
        library: Source endmember library (output of one of the loaders).
            Must have dims ``(spectrum_id, wavelength)`` with the wavelength
            coordinate in nanometres.
        target_wavelengths: 1D array of target band centres in nanometres.
            Tanager's standard 426 bands span 380-2500 nm at ~5 nm spacing.
        fwhm: Target sensor FWHM (nm). Scalar broadcast across all target
            bands, or a 1D array matching ``target_wavelengths``.
        source_fwhm: Source spectrometer FWHM (nm). Scalar or 1D array
            matching the input library's wavelength axis. Defaults to ASD
            field-spec resolution (1 nm).

    Returns:
        ``xr.DataArray`` with dims ``(spectrum_id, wavelength)``, the target
        wavelength grid, original metadata coords (``name``, ``category``,
        ``source``), and reflectance clipped to ``[0, 1]``.

    Raises:
        ValueError: If ``library`` does not have a ``wavelength`` coordinate
            or ``target_wavelengths`` is not 1D.
    """
    if "wavelength" not in library.coords:
        raise ValueError("library must have a 'wavelength' coordinate")
    target_wavelengths = np.asarray(target_wavelengths, dtype=np.float64).ravel()
    if target_wavelengths.ndim != 1 or target_wavelengths.size == 0:
        raise ValueError("target_wavelengths must be a non-empty 1D array")

    source_centers = np.asarray(library.coords["wavelength"].values, dtype=np.float64)

    fwhm_target = np.broadcast_to(np.asarray(fwhm, dtype=np.float64), target_wavelengths.shape).copy()
    fwhm_source = np.broadcast_to(np.asarray(source_fwhm, dtype=np.float64), source_centers.shape).copy()

    from spectral import BandResampler  # heavy dep — defer import

    resampler = BandResampler(
        centers1=source_centers,
        centers2=target_wavelengths,
        fwhm1=fwhm_source,
        fwhm2=fwhm_target,
    )

    n_spectra = library.sizes["spectrum_id"]
    out = np.empty((n_spectra, target_wavelengths.size), dtype=np.float32)
    for i in range(n_spectra):
        spectrum = np.asarray(library.isel(spectrum_id=i).values, dtype=np.float64)
        # Replace any lingering NaNs with 0 so the convolution is well-defined.
        spectrum = np.nan_to_num(spectrum, nan=0.0)
        resampled = resampler(spectrum)
        out[i] = np.clip(np.asarray(resampled, dtype=np.float32), _REFLECTANCE_MIN, _REFLECTANCE_MAX)

    metadata_coords: dict[str, Tuple[str, np.ndarray]] = {}
    for key in ("name", "category", "source"):
        if key in library.coords:
            metadata_coords[key] = ("spectrum_id", library.coords[key].values)

    resampled_da = xr.DataArray(
        out,
        dims=("spectrum_id", "wavelength"),
        coords={
            "spectrum_id": library.coords["spectrum_id"].values,
            "wavelength": target_wavelengths.astype(np.float32),
            **metadata_coords,
        },
        attrs={
            **library.attrs,
            "resampled_to": f"{target_wavelengths.size} bands",
            "target_fwhm_nm": (float(fwhm_target.min()), float(fwhm_target.max())),
        },
    )
    return resampled_da


# ---------------------------------------------------------------------------
# FRAMES SoCal loader
# ---------------------------------------------------------------------------


# FRAMES filename keyword → category. The SoCal chaparral library has 66
# spectra split as: 7 char/ash, 36 GV (=pv), 13 NPV, 10 soil. Filenames are
# not standardised across all FRAMES contributions, so we provide both an
# explicit ``category_map`` parameter and these heuristic fallbacks.
_FRAMES_CATEGORY_KEYWORDS: Tuple[Tuple[str, str], ...] = (
    ("char", "char"),
    ("ash", "ash"),
    ("burn", "char"),
    ("dryveg", "npv"),
    ("dry_veg", "npv"),
    ("dry-veg", "npv"),
    ("npv", "npv"),
    ("litter", "npv"),
    ("woody", "npv"),
    ("dead", "npv"),
    ("gv", "pv"),
    ("green", "pv"),
    ("photosynthetic", "pv"),
    ("vegetation", "pv"),
    ("chaparral", "pv"),
    ("soil", "soil"),
    ("rock", "soil"),
    ("mineral", "soil"),
)


def _classify_frames(stem: str) -> str:
    """Infer a fire-relevant category from a FRAMES filename stem.

    Args:
        stem: Filename without directory or extension.

    Returns:
        One of the fire categories or ``"other"`` when no keyword matches.
    """
    lower = stem.lower()
    for needle, category in _FRAMES_CATEGORY_KEYWORDS:
        if needle in lower:
            return category
    return "other"


def _read_two_column_ascii(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """Read a two-column whitespace-delimited ASCII file.

    Tolerates header comment lines (any line whose first token is not a finite
    float) and blank lines. Treats commas, tabs, and runs of whitespace as
    separators.

    Args:
        path: Filesystem path to the ASCII spectrum file.

    Returns:
        Two 1D ``np.ndarray`` (wavelengths, reflectance), both ``np.float64``.

    Raises:
        ValueError: If fewer than two numeric rows are found.
    """
    wls: list[float] = []
    refl: list[float] = []
    with open(path, "r", encoding="latin-1") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            tokens = re.split(r"[,\s]+", stripped)
            if len(tokens) < 2:
                continue
            try:
                w = float(tokens[0])
                r = float(tokens[1])
            except ValueError:
                continue
            wls.append(w)
            refl.append(r)
    if len(wls) < 2:
        raise ValueError(f"Fewer than 2 numeric rows in FRAMES ASCII file: {path}")
    return np.asarray(wls, dtype=np.float64), np.asarray(refl, dtype=np.float64)


def load_frames_library(
    data_dir: Union[str, os.PathLike],
    *,
    category_map: Optional[Mapping[str, str]] = None,
    file_pattern: str = "*.txt",
) -> xr.DataArray:
    """Load the FRAMES SoCal chaparral spectral library from local ASCII files.

    FRAMES (Forest and Rangeland Ecosystem Analysis and Modelling System) hosts
    spectra collected after the Old and Simi fires — the standard reference
    library for SoCal chaparral fuel mapping. Files are not on PyPI; download
    them manually from `frames.gov <https://www.frames.gov/>`_ into
    ``data_dir``.

    Each spectrum file is a two-column ASCII (wavelength + reflectance). The
    wavelength column may be in micrometres or nanometres — the function
    auto-detects based on magnitude (max < 50 → assume micrometres, otherwise
    nanometres). Reflectance values reported as percent (0-100) are auto-scaled
    to fractional reflectance. Different files may have different wavelength
    grids: the first file's grid is canonical and subsequent files are
    interpolated onto it.

    Args:
        data_dir: Directory containing FRAMES ASCII spectrum files.
        category_map: Optional mapping from filename stem to category string.
            When supplied, takes precedence over filename heuristics.
        file_pattern: Glob pattern for spectrum files. Default ``"*.txt"``.

    Returns:
        ``xr.DataArray`` with the same schema as :func:`load_usgs_library`,
        ``source="frames"``. Spectra that fail to parse or yield ``"other"``
        category are skipped with a warning.

    Raises:
        FileNotFoundError: If ``data_dir`` does not exist or no files match.
        ValueError: If no spectrum survives parsing/categorisation.
    """
    root = Path(data_dir).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(f"FRAMES data_dir does not exist: {root}")

    paths = sorted(root.glob(file_pattern))
    if not paths:
        raise FileNotFoundError(
            f"No FRAMES spectrum files matching {file_pattern!r} found in {root}"
        )

    rows: list[np.ndarray] = []
    spectrum_ids: list[str] = []
    names: list[str] = []
    cats: list[str] = []
    common_wavelengths: Optional[np.ndarray] = None

    for path in paths:
        try:
            wl_raw, refl = _read_two_column_ascii(path)
        except ValueError as exc:
            logger.warning("FRAMES file %s: %s", path.name, exc)
            continue

        # Auto-detect wavelength units. ASD field-spec is 350-2500 nm; a max
        # value < 50 strongly implies micrometres.
        wl_nm = wl_raw * 1000.0 if np.nanmax(wl_raw) < 50.0 else wl_raw
        if np.nanmax(refl) > 1.5:
            refl = refl / 100.0
        refl = np.clip(refl, _REFLECTANCE_MIN, _REFLECTANCE_MAX)

        stem = path.stem
        if category_map is not None and stem in category_map:
            category = category_map[stem].lower()
        else:
            category = _classify_frames(stem)
        if category == "other":
            logger.info("FRAMES spectrum %s: no category match — skipping", stem)
            continue

        if common_wavelengths is None:
            common_wavelengths = wl_nm.astype(np.float32)
            refl_v = refl.astype(np.float32)
        else:
            refl_v = np.interp(common_wavelengths, wl_nm, refl, left=np.nan, right=np.nan).astype(np.float32)

        rows.append(refl_v)
        spectrum_ids.append(f"frames_{category}_{len(rows):04d}")
        names.append(stem)
        cats.append(category)

    if not rows:
        raise ValueError(
            f"No FRAMES spectra survived categorisation in {root} (try category_map)"
        )

    reflectance = np.vstack(rows).astype(np.float32)
    return _build_library_dataarray(
        reflectance=reflectance,
        wavelengths_nm=common_wavelengths,
        spectrum_ids=spectrum_ids,
        names=names,
        categories=cats,
        source="frames",
    )


# ---------------------------------------------------------------------------
# ECOSTRESS loader
# ---------------------------------------------------------------------------


# Mapping from ECOSTRESS sample Type/Class strings (case-insensitive) to our
# fire-relevant categories. Keys are matched as case-insensitive substrings.
# Order matters: more specific keywords come first so they match before more
# general ones (e.g. "non-photosynthetic vegetation" must hit NPV before PV).
_ECOSTRESS_CATEGORY_KEYWORDS: Tuple[Tuple[str, str], ...] = (
    ("char", "char"),
    ("ash", "ash"),
    ("non-photosynthetic", "npv"),
    ("dry vegetation", "npv"),
    ("dryveg", "npv"),
    ("litter", "npv"),
    ("wood", "npv"),
    ("bark", "npv"),
    ("vegetation", "pv"),
    ("tree", "pv"),
    ("grass", "pv"),
    ("shrub", "pv"),
    ("soil", "soil"),
    ("rock", "soil"),
    ("mineral", "soil"),
)


def _classify_ecostress(sample_type: str, sample_class: str, sample_subclass: str) -> str:
    """Map ECOSTRESS sample metadata to a fire-relevant category.

    Args:
        sample_type: ECOSTRESS sample Type field (e.g. ``"vegetation"``).
        sample_class: ECOSTRESS sample Class field (e.g. ``"tree"``).
        sample_subclass: ECOSTRESS sample Subclass field.

    Returns:
        One of the fire categories or ``"other"`` when no keyword matches.
    """
    haystack = " ".join(s.lower() for s in (sample_type or "", sample_class or "", sample_subclass or ""))
    for needle, category in _ECOSTRESS_CATEGORY_KEYWORDS:
        if needle in haystack:
            return category
    return "other"


def load_ecostress_library(
    categories: Optional[Sequence[str]] = None,
    *,
    sqlite_path: Optional[Union[str, os.PathLike]] = None,
    db: Optional[object] = None,
) -> xr.DataArray:
    """Load ECOSTRESS spectra via SPy ``EcostressDatabase``, filtered to VSWIR.

    The SPy ECOSTRESS database is a SQLite file built from the ECOSTRESS
    Spectral Library distributable. It must be created once (per the SPy
    ``EcostressDatabase.create()`` documentation) and pointed at via
    ``sqlite_path``. For unit-testing, callers may inject a fully-formed
    duck-typed ``db`` instance exposing ``query`` and ``get_spectrum``.

    Args:
        categories: Optional iterable of category strings to keep. ``None``
            returns all spectra that map to a known fire category.
        sqlite_path: Path to the pre-built ECOSTRESS SQLite database. Required
            unless ``db`` is provided.
        db: Optional pre-instantiated ``EcostressDatabase``-like object. When
            provided, ``sqlite_path`` is ignored. Useful for unit tests with
            mocks.

    Returns:
        ``xr.DataArray`` with the same schema as :func:`load_usgs_library`.
        Wavelengths are converted from micrometres (ECOSTRESS native unit) to
        nanometres and clipped to VSWIR (350-2500 nm). Spectra without any
        VSWIR coverage are dropped.

    Raises:
        FileNotFoundError: If ``sqlite_path`` is given but does not exist.
        RuntimeError: If neither ``sqlite_path`` nor ``db`` is provided.
        ValueError: If no spectra survive filtering.
    """
    if db is None:
        if sqlite_path is None:
            raise RuntimeError(
                "Either sqlite_path or db must be provided. ECOSTRESS data is not "
                "auto-downloaded — see SPy EcostressDatabase.create() docs."
            )
        sqlite_path = Path(sqlite_path).expanduser()
        if not sqlite_path.is_file():
            raise FileNotFoundError(f"ECOSTRESS SQLite database not found: {sqlite_path}")
        from spectral.database.ecostress import EcostressDatabase

        db = EcostressDatabase(str(sqlite_path))

    keep_categories = set(c.lower() for c in categories) if categories is not None else None

    sample_rows = db.query(
        "SELECT SpectrumID, Type, Class, Subclass, Name "
        "FROM Spectra JOIN Samples ON Spectra.SampleID = Samples.SampleID "
        "WHERE Spectra.XUnit LIKE '%micrometer%' OR Spectra.XUnit LIKE '%um%'"
    )
    sample_rows = list(sample_rows)
    if not sample_rows:
        # Fallback for mocks or schemas that ignore the unit predicate.
        sample_rows = list(db.query(
            "SELECT SpectrumID, Type, Class, Subclass, Name FROM Samples"
        ))

    rows: list[np.ndarray] = []
    spectrum_ids: list[str] = []
    names: list[str] = []
    cats: list[str] = []
    common_wavelengths: Optional[np.ndarray] = None

    for row in sample_rows:
        spectrum_id, sample_type, sample_class, subclass, name = row
        category = _classify_ecostress(sample_type or "", sample_class or "", subclass or "")
        if category == "other":
            continue
        if keep_categories is not None and category not in keep_categories:
            continue

        wl_um, refl = db.get_spectrum(spectrum_id)
        wl_um = np.asarray(wl_um, dtype=np.float64)
        refl = np.asarray(refl, dtype=np.float64)
        wl_nm = wl_um * 1000.0  # micrometres → nanometres
        # Some ECOSTRESS spectra report reflectance as percent (0-100). Detect
        # and rescale to fractional reflectance.
        if np.nanmax(refl) > 1.5:
            refl = refl / 100.0

        vswir = (wl_nm >= 350.0) & (wl_nm <= 2500.0)
        if not np.any(vswir):
            continue
        wl_nm_v = wl_nm[vswir]
        refl_v = refl[vswir]

        if common_wavelengths is None:
            common_wavelengths = wl_nm_v.astype(np.float32)
        elif wl_nm_v.shape != common_wavelengths.shape or not np.allclose(wl_nm_v, common_wavelengths):
            # Different sampling grid — interpolate to the first spectrum's grid.
            refl_v = np.interp(common_wavelengths, wl_nm_v, refl_v, left=np.nan, right=np.nan)

        rows.append(refl_v.astype(np.float32))
        spectrum_ids.append(f"ecostress_{category}_{len(rows):04d}")
        names.append(str(name))
        cats.append(category)

    if not rows:
        raise ValueError(
            f"No ECOSTRESS spectra survived VSWIR/category filtering (categories={categories})"
        )

    reflectance = np.vstack(rows).astype(np.float32)
    return _build_library_dataarray(
        reflectance=reflectance,
        wavelengths_nm=common_wavelengths,
        spectrum_ids=spectrum_ids,
        names=names,
        categories=cats,
        source="ecostress",
    )


def _guess_category_from_filename(stem: str) -> str:
    """Heuristic mapping from a USGS spectrum filename to a fire-relevant category.

    The splib07 naming convention encodes material in the filename, e.g.
    ``s07ASD_Char_Pinus_W3R10`` or ``s07ASD_Soil_Mollisol_PNM81``. We look for
    well-known substrings in priority order.

    Args:
        stem: Filename without directory or extension.

    Returns:
        One of the strings in :data:`FIRE_CATEGORIES` plus ``"other"`` as the
        final catch-all when no fire category matches.
    """
    lower = stem.lower()
    keyword_map: Tuple[Tuple[str, str], ...] = (
        ("char", "char"),
        ("ash", "ash"),
        ("vegetation", "pv"),
        ("grass", "pv"),
        ("leaf", "pv"),
        ("conifer", "pv"),
        ("dry_grass", "npv"),
        ("dryveg", "npv"),
        ("npv", "npv"),
        ("litter", "npv"),
        ("wood", "npv"),
        ("bark", "npv"),
        ("soil", "soil"),
        ("mineral", "soil"),
        ("rock", "soil"),
    )
    for needle, category in keyword_map:
        if needle in lower:
            return category
    return "other"
