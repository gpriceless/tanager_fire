"""Spectral band operations for Tanager-1 hyperspectral imagery.

This module provides wavelength-based band selection and bad-band masking
for xarray Datasets produced by the tanager.io loader.  All operations
return new Datasets; the input is never modified in place.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

import numpy as np
import xarray as xr

from tanager.config import BAD_BAND_RANGES

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
