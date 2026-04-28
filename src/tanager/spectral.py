"""Spectral band operations for Tanager-1 hyperspectral imagery.

This module provides wavelength-based band selection, bad-band masking,
normalized-difference spectral indices (NBR, NDVI, NDWI, dNBR), and convex-hull
continuum removal for xarray Datasets produced by the tanager.io loader.  All
operations return new objects; the input is never modified in place.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence, Tuple

import numpy as np
import xarray as xr
from scipy.spatial import ConvexHull

from tanager.config import BAND_ALIASES, BAD_BAND_RANGES

logger = logging.getLogger(__name__)

_EXPECTED_GOOD_BAND_MIN = 320
_EXPECTED_GOOD_BAND_MAX = 360


def select_bands(
    dataset: xr.Dataset,
    *,
    min_wl: Optional[float] = None,
    max_wl: Optional[float] = None,
    wavelengths: Optional[Sequence[float]] = None,
) -> tuple[xr.Dataset, np.ndarray] | xr.Dataset:
    """Select a subset of spectral bands from a hyperspectral dataset.

    Exactly one of the two selection modes must be specified:

    * **Range mode** (``min_wl`` + ``max_wl``): returns all bands whose centre
      wavelength falls within the closed interval ``[min_wl, max_wl]``.
    * **Nearest-neighbor mode** (``wavelengths``): maps each requested
      wavelength to the closest band present in the dataset and returns a
      ``(dataset, matched_wavelengths)`` tuple so callers know which bands were
      actually selected.

    Args:
        dataset: xarray Dataset with a ``wavelength`` coordinate (units: nm).
        min_wl: Lower bound of wavelength range (nm), inclusive.  Must be
            provided together with ``max_wl``.
        max_wl: Upper bound of wavelength range (nm), inclusive.  Must be
            provided together with ``min_wl``.
        wavelengths: Sequence of target wavelengths (nm) for nearest-neighbor
            matching.  Duplicates are preserved in the output order.

    Returns:
        Range mode: an ``xr.Dataset`` containing only the selected bands.
        Nearest-neighbor mode: a ``(xr.Dataset, np.ndarray)`` tuple where the
        second element is the array of matched centre wavelengths.

    Raises:
        ValueError: If both modes are specified simultaneously, if neither mode
            is specified, or if a range selection yields zero matching bands.
    """
    range_provided = (min_wl is not None) or (max_wl is not None)
    nn_provided = wavelengths is not None

    if range_provided and nn_provided:
        raise ValueError(
            "Specify either (min_wl, max_wl) for range selection "
            "or wavelengths for nearest-neighbor selection, not both."
        )
    if not range_provided and not nn_provided:
        raise ValueError(
            "One of (min_wl, max_wl) or wavelengths must be provided."
        )

    if range_provided:
        if min_wl is None or max_wl is None:
            raise ValueError("Both min_wl and max_wl must be provided for range selection.")
        return _select_by_range(dataset, min_wl, max_wl)

    return _select_by_nearest(dataset, wavelengths)  # type: ignore[arg-type]


def _select_by_range(
    dataset: xr.Dataset, min_wl: float, max_wl: float
) -> xr.Dataset:
    """Return bands in [min_wl, max_wl] using boolean indexing.

    Args:
        dataset: Dataset with ``wavelength`` coordinate (nm).
        min_wl: Inclusive lower bound (nm).
        max_wl: Inclusive upper bound (nm).

    Returns:
        Subset Dataset restricted to the specified wavelength range.

    Raises:
        ValueError: If no bands fall within the specified range.
    """
    wl = dataset.coords["wavelength"]
    mask = (wl >= min_wl) & (wl <= max_wl)
    if not mask.any():
        raise ValueError(
            f"No bands found in wavelength range [{min_wl}, {max_wl}] nm. "
            f"Dataset covers {float(wl.min()):.1f}–{float(wl.max()):.1f} nm."
        )
    return dataset.sel(wavelength=mask)


def _select_by_nearest(
    dataset: xr.Dataset, wavelengths: Sequence[float]
) -> tuple[xr.Dataset, np.ndarray]:
    """Return nearest-neighbor band matches for each requested wavelength.

    Args:
        dataset: Dataset with ``wavelength`` coordinate (nm).
        wavelengths: Requested centre wavelengths (nm).

    Returns:
        Tuple of (subset Dataset, array of actual matched wavelengths).
    """
    target = xr.DataArray(list(wavelengths), dims="wavelength")
    subset = dataset.sel(wavelength=target, method="nearest")
    matched = subset.coords["wavelength"].values.copy()
    return subset, matched


def mask_bad_bands(
    dataset: xr.Dataset,
    *,
    zones: Optional[list[tuple[float, float]]] = None,
) -> xr.Dataset:
    """Remove bands that fall within known atmospheric-absorption and sensor-edge ranges.

    By default the four standard Tanager-1 exclusion zones defined in
    ``tanager.config.BAD_BAND_RANGES`` are applied:

    * 0–400 nm   — sensor edge / below reliable detector response
    * 1340–1480 nm — water vapour absorption band 1
    * 1790–1960 nm — water vapour absorption band 2
    * 2350–2500 nm — CO₂ / H₂O absorption at long-wave sensor edge

    When ``zones`` is provided it **replaces** the defaults entirely; the
    caller is responsible for specifying all exclusion zones they want applied.

    Args:
        dataset: xarray Dataset with a ``wavelength`` coordinate (units: nm).
        zones: Optional list of ``(low_nm, high_nm)`` tuples.  Each band whose
            centre wavelength falls within any zone (inclusive on both ends) is
            excluded.  When provided this argument replaces the default
            ``BAD_BAND_RANGES`` entirely.

    Returns:
        A new Dataset with bad bands removed.  The ``wavelength`` coordinate
        is a contiguous sorted sub-array of the input coordinate.

    Warns:
        Logs a WARNING if the remaining band count is outside the expected
        330–346 range (only when default zones are applied to a 426-band
        dataset).
    """
    exclusion_zones = zones if zones is not None else BAD_BAND_RANGES

    wl = dataset.coords["wavelength"]
    n_input = int(wl.sizes["wavelength"])

    good_mask = np.ones(n_input, dtype=bool)
    for low, high in exclusion_zones:
        good_mask &= ~((wl.values >= low) & (wl.values <= high))

    n_excluded = int(np.sum(~good_mask))
    n_remaining = int(np.sum(good_mask))

    logger.info(
        "mask_bad_bands: excluded %d bands, %d bands remaining (of %d input)",
        n_excluded,
        n_remaining,
        n_input,
    )

    if zones is None and n_input == 426:
        if not (_EXPECTED_GOOD_BAND_MIN <= n_remaining <= _EXPECTED_GOOD_BAND_MAX):
            logger.warning(
                "mask_bad_bands: expected ~330–346 good bands (real data) after "
                "masking 426-band dataset but got %d; verify BAD_BAND_RANGES "
                "and wavelength grid.",
                n_remaining,
            )

    return dataset.sel(wavelength=good_mask)


# ---------------------------------------------------------------------------
# Spectral indices
# ---------------------------------------------------------------------------


def _normalized_difference(band1: xr.DataArray, band2: xr.DataArray) -> xr.DataArray:
    """Compute (band1 - band2) / (band1 + band2) with NaN where denominator is zero.

    Args:
        band1: First spectral band DataArray.
        band2: Second spectral band DataArray.

    Returns:
        DataArray with normalized difference values in [-1, 1], NaN where
        band1 + band2 == 0.
    """
    numerator = band1 - band2
    denominator = band1 + band2
    return xr.where(denominator == 0, np.nan, numerator / denominator)


def nbr(dataset: xr.Dataset) -> xr.DataArray:
    """Compute Normalized Burn Ratio (NBR).

    NBR = (NIR - SWIR2) / (NIR + SWIR2)

    Uses 860 nm as NIR and 2200 nm as SWIR2, matched to nearest available band
    in the dataset (Tanager-1 5 nm spacing; match within 2.5 nm guaranteed).

    Args:
        dataset: xarray Dataset with a ``wavelength`` coordinate (nm) and a
            ``reflectance`` variable of shape (wavelength, y, x).

    Returns:
        DataArray of NBR values with spatial dimensions (y, x).  Values are in
        [-1, 1]; pixels where NIR + SWIR2 == 0 are set to NaN.
    """
    nir = dataset["reflectance"].sel(wavelength=BAND_ALIASES["NIR"], method="nearest")
    swir2 = dataset["reflectance"].sel(wavelength=BAND_ALIASES["SWIR2"], method="nearest")
    return _normalized_difference(nir, swir2)


def ndvi(dataset: xr.Dataset) -> xr.DataArray:
    """Compute Normalized Difference Vegetation Index (NDVI).

    NDVI = (NIR - Red) / (NIR + Red)

    Uses 860 nm as NIR and 660 nm as Red, matched to nearest available band.

    Args:
        dataset: xarray Dataset with a ``wavelength`` coordinate (nm) and a
            ``reflectance`` variable of shape (wavelength, y, x).

    Returns:
        DataArray of NDVI values with spatial dimensions (y, x).  Values are in
        [-1, 1]; pixels where NIR + Red == 0 are set to NaN.
    """
    nir = dataset["reflectance"].sel(wavelength=BAND_ALIASES["NIR"], method="nearest")
    red = dataset["reflectance"].sel(wavelength=BAND_ALIASES["RED"], method="nearest")
    return _normalized_difference(nir, red)


def ndwi(dataset: xr.Dataset) -> xr.DataArray:
    """Compute Normalized Difference Water Index (NDWI).

    NDWI = (Green - NIR) / (Green + NIR)

    Uses 560 nm as Green and 860 nm as NIR, matched to nearest available band.

    Args:
        dataset: xarray Dataset with a ``wavelength`` coordinate (nm) and a
            ``reflectance`` variable of shape (wavelength, y, x).

    Returns:
        DataArray of NDWI values with spatial dimensions (y, x).  Values are in
        [-1, 1]; pixels where Green + NIR == 0 are set to NaN.
    """
    green = dataset["reflectance"].sel(wavelength=BAND_ALIASES["GREEN"], method="nearest")
    nir = dataset["reflectance"].sel(wavelength=BAND_ALIASES["NIR"], method="nearest")
    return _normalized_difference(green, nir)


def dnbr(pre: xr.Dataset, post: xr.Dataset) -> xr.DataArray:
    """Compute differenced Normalized Burn Ratio (dNBR).

    dNBR = NBR(pre) - NBR(post)

    Positive values indicate burn severity (pre-fire vegetation vs post-fire
    bare/charred ground).

    Args:
        pre: Pre-fire xarray Dataset with ``wavelength`` coordinate and
            ``reflectance`` variable (shape: wavelength, y, x).
        post: Post-fire xarray Dataset with the same structure.  Spatial
            dimensions (y, x sizes) must match ``pre``.

    Returns:
        DataArray of dNBR values with spatial dimensions (y, x).

    Raises:
        ValueError: If the spatial dimensions of ``pre`` and ``post`` differ.
    """
    pre_y = pre.sizes.get("y")
    pre_x = pre.sizes.get("x")
    post_y = post.sizes.get("y")
    post_x = post.sizes.get("x")

    if (pre_y, pre_x) != (post_y, post_x):
        raise ValueError(
            f"Spatial dimensions of pre and post datasets must match: "
            f"pre is ({pre_y}, {pre_x}), post is ({post_y}, {post_x})."
        )

    return nbr(pre) - nbr(post)


# ---------------------------------------------------------------------------
# Continuum removal
# ---------------------------------------------------------------------------


def _continuum_removal_spectrum(reflectance: np.ndarray, wavelengths: np.ndarray) -> np.ndarray:
    """Apply convex hull continuum removal to a single spectrum.

    The upper convex hull of the (wavelength, reflectance) point set is
    computed, interpolated back to every wavelength, and used as the continuum.
    The spectrum is then divided by the continuum.  Results are clipped to
    [0, 1].

    Args:
        reflectance: 1-D array of reflectance values (unitless, typically 0–1).
        wavelengths: 1-D array of centre wavelengths (nm), same length as
            ``reflectance``.

    Returns:
        1-D array of continuum-removed reflectance values in [0, 1].
    """
    points = np.column_stack([wavelengths, reflectance])

    if len(points) < 3:
        # Cannot form a convex hull with fewer than 3 points; return ones.
        return np.ones_like(reflectance, dtype=np.float64)

    try:
        hull = ConvexHull(points)
        # Extract hull vertices; ConvexHull uses the full (lower + upper) hull.
        # We want only the upper hull — vertices with maximum y for each x.
        # Strategy: take all hull vertices, sort by wavelength, then keep only
        # those that lie on the upper boundary via monotone chain.
        hull_pts = points[hull.vertices]
        hull_pts = hull_pts[np.argsort(hull_pts[:, 0])]
        # Interpolate upper hull to all wavelengths
        continuum = np.interp(wavelengths, hull_pts[:, 0], hull_pts[:, 1])
    except Exception:
        # If hull fails (e.g., all-zero or collinear spectrum), use the
        # maximum value as a flat continuum to avoid dividing by zero.
        max_val = float(np.max(reflectance))
        continuum = np.full_like(reflectance, max_val if max_val > 0 else 1.0, dtype=np.float64)

    # Avoid division by zero in the continuum
    continuum = np.where(continuum == 0, np.nan, continuum)
    result = reflectance.astype(np.float64) / continuum
    return np.minimum(result, 1.0)


def continuum_removal(
    dataset: xr.Dataset,
    wavelength_range: Optional[Tuple[float, float]] = None,
) -> xr.DataArray:
    """Apply convex hull continuum removal to every pixel spectrum.

    Continuum removal normalises each pixel spectrum by dividing it by a
    convex-hull continuum fitted to the (wavelength, reflectance) curve.  The
    output represents relative absorption depth rather than absolute reflectance
    and is useful for comparing spectral features across illumination conditions.

    Args:
        dataset: xarray Dataset with a ``wavelength`` coordinate (nm) and a
            ``reflectance`` variable with dimensions (wavelength, y, x).
        wavelength_range: Optional ``(min_nm, max_nm)`` tuple.  When provided,
            continuum removal is applied only to bands within the closed
            interval ``[min_nm, max_nm]``; bands outside the range are not
            included in the output.  When ``None`` (default), the full spectrum
            is used.

    Returns:
        DataArray of continuum-removed reflectance values in [0, 1] with
        dimensions (wavelength, y, x).  The wavelength coordinate reflects the
        selected range if ``wavelength_range`` was specified.
    """
    refl = dataset["reflectance"]

    if wavelength_range is not None:
        min_wl, max_wl = wavelength_range
        wl_coord = refl.coords["wavelength"]
        mask = (wl_coord >= min_wl) & (wl_coord <= max_wl)
        refl = refl.sel(wavelength=mask)

    wavelengths = refl.coords["wavelength"].values.astype(np.float64)

    def _apply_cr(spectrum: np.ndarray) -> np.ndarray:
        return _continuum_removal_spectrum(spectrum, wavelengths)

    result = xr.apply_ufunc(
        _apply_cr,
        refl,
        input_core_dims=[["wavelength"]],
        output_core_dims=[["wavelength"]],
        vectorize=True,
        dask="parallelized",
        output_dtypes=[np.float64],
        dask_gufunc_kwargs={"output_sizes": {"wavelength": len(wavelengths)}},
    )
    # apply_ufunc may reorder dims; transpose back to (wavelength, y, x)
    return result.transpose("wavelength", ...)
