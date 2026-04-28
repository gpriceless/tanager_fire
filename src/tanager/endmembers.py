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
