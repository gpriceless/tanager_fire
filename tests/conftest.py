"""Shared pytest fixtures for Tanager test suite.

Provides synthetic hyperspectral datasets that match Tanager-1 sensor
characteristics (426 bands, 380–2500 nm, Float32 reflectance) without
requiring real HDF5 files.
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr


# ---------------------------------------------------------------------------
# Constants matching Tanager-1 sensor spec
# ---------------------------------------------------------------------------

_N_BANDS: int = 426
_WL_MIN_NM: float = 380.0
_WL_MAX_NM: float = 2500.0
_N_ROWS: int = 50
_N_COLS: int = 50


def _make_wavelengths() -> np.ndarray:
    """Return the 426-element wavelength array in nanometres."""
    return np.linspace(_WL_MIN_NM, _WL_MAX_NM, _N_BANDS)


# ---------------------------------------------------------------------------
# Task 1 — Basic synthetic dataset
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_tanager_dataset() -> xr.Dataset:
    """Synthetic Tanager-1 dataset with random Float32 reflectance.

    Returns:
        xr.Dataset with:
            - variable ``reflectance`` of shape (426, 50, 50), dtype float32,
              values clipped to [0, 1]
            - coords: wavelength (nm), y (pixel row), x (pixel col)
    """
    wavelengths = _make_wavelengths()
    rng = np.random.default_rng(42)
    data = rng.random((_N_BANDS, _N_ROWS, _N_COLS)).astype(np.float32)
    data = np.clip(data, 0.0, 1.0)

    return xr.Dataset(
        {"reflectance": (["wavelength", "y", "x"], data)},
        coords={
            "wavelength": wavelengths,
            "y": np.arange(_N_ROWS),
            "x": np.arange(_N_COLS),
        },
    )


# ---------------------------------------------------------------------------
# Task 2 — Fixture factory with known spectral profiles
# ---------------------------------------------------------------------------


def _build_vegetation_spectrum(wavelengths: np.ndarray) -> np.ndarray:
    """Return a vegetation reflectance spectrum (one pixel, all bands).

    Key features:
        - Chlorophyll absorption dip at ~680 nm (~0.05)
        - High NIR plateau 750–1300 nm (~0.40–0.50)
        - Cellulose/lignin feature near 2100 nm (dip from ~0.20 → ~0.12)
        - Low SWIR-2 shoulder toward 2500 nm (~0.08)

    Args:
        wavelengths: 1-D wavelength array in nm.

    Returns:
        1-D float32 reflectance array, same length as *wavelengths*.
    """
    spec = np.zeros(len(wavelengths), dtype=np.float32)
    for i, wl in enumerate(wavelengths):
        if wl < 680.0:
            # VNIR rising from ~0.05 at blue to a red edge
            spec[i] = 0.05 + (wl - 380.0) / (680.0 - 380.0) * 0.05
        elif wl < 750.0:
            # Red-edge — rapid rise from chlorophyll dip to NIR plateau
            spec[i] = 0.05 + (wl - 680.0) / (750.0 - 680.0) * 0.40
        elif wl < 1300.0:
            # NIR plateau
            spec[i] = 0.45
        elif wl < 1800.0:
            # SWIR-1 transition (includes cellulose shoulder)
            spec[i] = 0.45 - (wl - 1300.0) / (1800.0 - 1300.0) * 0.25
        elif wl < 2150.0:
            # Cellulose/lignin absorption feature around 2100 nm
            dist = abs(wl - 2100.0)
            spec[i] = max(0.08, 0.20 - (1.0 - dist / 200.0) * 0.12)
        else:
            # SWIR-2 tail
            spec[i] = 0.08
    return spec


def _build_char_spectrum(wavelengths: np.ndarray) -> np.ndarray:
    """Return a charcoal/burned-surface reflectance spectrum.

    Key features:
        - Very low, flat reflectance throughout VNIR/NIR (~0.02–0.05)
        - Slight rise in SWIR toward 2500 nm (~0.07)

    Args:
        wavelengths: 1-D wavelength array in nm.

    Returns:
        1-D float32 reflectance array, same length as *wavelengths*.
    """
    spec = np.zeros(len(wavelengths), dtype=np.float32)
    for i, wl in enumerate(wavelengths):
        if wl < 1500.0:
            spec[i] = 0.02 + (wl - 380.0) / (1500.0 - 380.0) * 0.02
        else:
            spec[i] = 0.04 + (wl - 1500.0) / (2500.0 - 1500.0) * 0.03
    return spec


def _build_soil_spectrum(wavelengths: np.ndarray) -> np.ndarray:
    """Return a dry bare-soil reflectance spectrum.

    Key features:
        - Monotonically increasing from ~0.10 in visible to ~0.30 in SWIR-2

    Args:
        wavelengths: 1-D wavelength array in nm.

    Returns:
        1-D float32 reflectance array, same length as *wavelengths*.
    """
    spec = (
        0.10 + (wavelengths - _WL_MIN_NM) / (_WL_MAX_NM - _WL_MIN_NM) * 0.20
    ).astype(np.float32)
    return np.clip(spec, 0.0, 1.0)


# Map signature name → builder function
_SIGNATURE_BUILDERS: dict[str, object] = {
    "vegetation": _build_vegetation_spectrum,
    "char": _build_char_spectrum,
    "soil": _build_soil_spectrum,
}

# Pixel-block layout within the 50-row grid
_SIGNATURE_ROW_BLOCKS: dict[str, tuple[int, int]] = {
    "vegetation": (0, 15),
    "char": (15, 30),
    "soil": (30, 45),
    # rows 45–50: random background (no named signature)
}


@pytest.fixture
def synthetic_tanager_dataset_with_signatures():
    """Fixture factory that returns Tanager-1 datasets with known spectral profiles.

    Usage::

        def test_example(synthetic_tanager_dataset_with_signatures):
            ds = synthetic_tanager_dataset_with_signatures()
            ds_veg_only = synthetic_tanager_dataset_with_signatures(["vegetation"])

    Each signature occupies a distinct rectangular pixel block:
        - vegetation: y[0:15]  (rows 0–14)
        - char:       y[15:30] (rows 15–29)
        - soil:       y[30:45] (rows 30–44)
        - random:     y[45:50] (rows 45–49, always present as background)

    Args (of the returned callable):
        signatures: List of signature names to embed.  Valid values are
            ``"vegetation"``, ``"char"``, ``"soil"``.  Defaults to all three.

    Returns:
        Function that accepts an optional *signatures* list and returns an
        xr.Dataset with variable ``reflectance`` (shape 426×50×50, float32),
        coords ``wavelength`` (nm), ``y``, ``x``.
    """

    def _factory(
        signatures: list[str] | None = None,
    ) -> xr.Dataset:
        """Build synthetic dataset with embedded spectral signatures.

        Args:
            signatures: Signature names to embed.  Defaults to
                ``["vegetation", "char", "soil"]``.

        Returns:
            xr.Dataset with known reflectance patterns per pixel block.

        Raises:
            ValueError: If an unknown signature name is provided.
        """
        if signatures is None:
            signatures = ["vegetation", "char", "soil"]

        unknown = set(signatures) - set(_SIGNATURE_BUILDERS)
        if unknown:
            raise ValueError(
                f"Unknown signature(s): {sorted(unknown)}. "
                f"Valid options: {sorted(_SIGNATURE_BUILDERS)}"
            )

        wavelengths = _make_wavelengths()
        rng = np.random.default_rng(0)
        # Start with random background clipped to [0, 1]
        data = rng.random((_N_BANDS, _N_ROWS, _N_COLS)).astype(np.float32)
        data = np.clip(data, 0.0, 1.0)

        for sig_name in signatures:
            builder = _SIGNATURE_BUILDERS[sig_name]
            row_start, row_end = _SIGNATURE_ROW_BLOCKS[sig_name]
            spectrum = builder(wavelengths)  # shape (426,)
            # Broadcast spectrum across all pixels in the block
            # data shape: (wavelength, y, x)
            data[:, row_start:row_end, :] = spectrum[:, np.newaxis, np.newaxis]

        return xr.Dataset(
            {"reflectance": (["wavelength", "y", "x"], data)},
            coords={
                "wavelength": wavelengths,
                "y": np.arange(_N_ROWS),
                "x": np.arange(_N_COLS),
            },
        )

    return _factory
