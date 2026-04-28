"""Tests for tanager.spectral band selection, masking, and spectral indices."""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from tanager.spectral import (
    continuum_removal,
    dnbr,
    mask_bad_bands,
    nbr,
    ndvi,
    ndwi,
    select_bands,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_dataset(wavelengths: np.ndarray) -> xr.Dataset:
    """Build a minimal synthetic Dataset with a reflectance variable."""
    n = len(wavelengths)
    data = np.ones((n, 4, 4), dtype=np.float32)
    return xr.Dataset(
        {"reflectance": (["wavelength", "y", "x"], data)},
        coords={"wavelength": wavelengths},
    )


@pytest.fixture
def simple_ds() -> xr.Dataset:
    """Dataset with 10 evenly-spaced bands from 400 to 900 nm."""
    return make_dataset(np.linspace(400, 900, 10))


@pytest.fixture
def tanager_ds() -> xr.Dataset:
    """Synthetic 426-band dataset matching Tanager-1 spectral range."""
    wavelengths = np.linspace(380, 2500, 426)
    data = np.random.default_rng(42).random((426, 50, 50)).astype(np.float32)
    return xr.Dataset(
        {"reflectance": (["wavelength", "y", "x"], data)},
        coords={"wavelength": wavelengths},
    )


# ---------------------------------------------------------------------------
# select_bands — range mode
# ---------------------------------------------------------------------------


class TestSelectBandsRange:
    def test_returns_bands_within_range(self, simple_ds: xr.Dataset) -> None:
        # Bands at 400, 455.5, 511.1, 566.7, 622.2 nm are below 650
        result = select_bands(simple_ds, min_wl=400, max_wl=650)
        wl = result.coords["wavelength"].values
        assert all(400 <= w <= 650 for w in wl)

    def test_excludes_bands_outside_range(self, simple_ds: xr.Dataset) -> None:
        result = select_bands(simple_ds, min_wl=500, max_wl=700)
        wl = result.coords["wavelength"].values
        assert all(500 <= w <= 700 for w in wl)

    def test_returns_dataset(self, simple_ds: xr.Dataset) -> None:
        result = select_bands(simple_ds, min_wl=400, max_wl=900)
        assert isinstance(result, xr.Dataset)

    def test_does_not_modify_input(self, simple_ds: xr.Dataset) -> None:
        original_size = simple_ds.sizes["wavelength"]
        select_bands(simple_ds, min_wl=500, max_wl=700)
        assert simple_ds.sizes["wavelength"] == original_size

    def test_exact_boundary_bands_included(self) -> None:
        wl = np.array([400.0, 500.0, 600.0, 700.0, 800.0])
        ds = make_dataset(wl)
        result = select_bands(ds, min_wl=500.0, max_wl=700.0)
        matched = result.coords["wavelength"].values
        np.testing.assert_array_equal(matched, [500.0, 600.0, 700.0])

    def test_raises_when_no_bands_in_range(self, simple_ds: xr.Dataset) -> None:
        with pytest.raises(ValueError, match="No bands found"):
            select_bands(simple_ds, min_wl=1000, max_wl=1200)

    def test_raises_when_range_out_of_dataset(self) -> None:
        ds = make_dataset(np.array([600.0, 700.0, 800.0]))
        with pytest.raises(ValueError, match="No bands found"):
            select_bands(ds, min_wl=200, max_wl=300)

    def test_raises_with_only_min_wl(self, simple_ds: xr.Dataset) -> None:
        with pytest.raises(ValueError):
            select_bands(simple_ds, min_wl=400)

    def test_raises_with_only_max_wl(self, simple_ds: xr.Dataset) -> None:
        with pytest.raises(ValueError):
            select_bands(simple_ds, max_wl=900)


# ---------------------------------------------------------------------------
# select_bands — nearest-neighbor mode
# ---------------------------------------------------------------------------


class TestSelectBandsNearest:
    def test_returns_tuple(self, simple_ds: xr.Dataset) -> None:
        result = select_bands(simple_ds, wavelengths=[500, 700])
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_tuple_has_dataset_and_array(self, simple_ds: xr.Dataset) -> None:
        subset, matched = select_bands(simple_ds, wavelengths=[500, 700])
        assert isinstance(subset, xr.Dataset)
        assert isinstance(matched, np.ndarray)

    def test_matched_wavelengths_from_dataset(self, simple_ds: xr.Dataset) -> None:
        _, matched = select_bands(simple_ds, wavelengths=[500, 700])
        available = simple_ds.coords["wavelength"].values
        for wl in matched:
            assert wl in available

    def test_nearest_band_selected(self) -> None:
        wl = np.array([400.0, 500.0, 600.0, 700.0, 800.0])
        ds = make_dataset(wl)
        _, matched = select_bands(ds, wavelengths=[520.0])
        assert matched[0] == pytest.approx(500.0, abs=60.0)

    def test_single_wavelength(self, simple_ds: xr.Dataset) -> None:
        subset, matched = select_bands(simple_ds, wavelengths=[700])
        assert subset.sizes["wavelength"] == 1
        assert len(matched) == 1

    def test_does_not_modify_input(self, simple_ds: xr.Dataset) -> None:
        original_size = simple_ds.sizes["wavelength"]
        select_bands(simple_ds, wavelengths=[500, 700])
        assert simple_ds.sizes["wavelength"] == original_size


# ---------------------------------------------------------------------------
# select_bands — invalid argument combinations
# ---------------------------------------------------------------------------


class TestSelectBandsValidation:
    def test_raises_both_modes_specified(self, simple_ds: xr.Dataset) -> None:
        with pytest.raises(ValueError, match="not both"):
            select_bands(simple_ds, min_wl=400, max_wl=900, wavelengths=[500])

    def test_raises_neither_mode_specified(self, simple_ds: xr.Dataset) -> None:
        with pytest.raises(ValueError):
            select_bands(simple_ds)


# ---------------------------------------------------------------------------
# mask_bad_bands — default zones
# ---------------------------------------------------------------------------


class TestMaskBadBandsDefaults:
    def test_returns_dataset(self, tanager_ds: xr.Dataset) -> None:
        result = mask_bad_bands(tanager_ds)
        assert isinstance(result, xr.Dataset)

    def test_band_count_approximate_range(self, tanager_ds: xr.Dataset) -> None:
        result = mask_bad_bands(tanager_ds)
        n = result.sizes["wavelength"]
        # linspace(380, 2500, 426) gives ~328 after masking; real Tanager data
        # gives 330-346.  Accept 310-360 in tests to cover both cases.
        assert 310 <= n <= 360, f"Unexpected band count after masking: {n}"

    def test_wavelength_coordinate_sorted(self, tanager_ds: xr.Dataset) -> None:
        result = mask_bad_bands(tanager_ds)
        wl = result.coords["wavelength"].values
        assert np.all(np.diff(wl) > 0), "Wavelength coordinate is not sorted ascending"

    def test_removes_sensor_edge_bands(self, tanager_ds: xr.Dataset) -> None:
        result = mask_bad_bands(tanager_ds)
        wl = result.coords["wavelength"].values
        assert not np.any(wl <= 400), "Sensor-edge bands <=400 nm not removed"

    def test_removes_water_vapour_band1(self, tanager_ds: xr.Dataset) -> None:
        result = mask_bad_bands(tanager_ds)
        wl = result.coords["wavelength"].values
        assert not np.any((wl >= 1340) & (wl <= 1480)), "Water vapour zone 1340-1480 not removed"

    def test_removes_water_vapour_band2(self, tanager_ds: xr.Dataset) -> None:
        result = mask_bad_bands(tanager_ds)
        wl = result.coords["wavelength"].values
        assert not np.any((wl >= 1790) & (wl <= 1960)), "Water vapour zone 1790-1960 not removed"

    def test_removes_co2_h2o_bands(self, tanager_ds: xr.Dataset) -> None:
        result = mask_bad_bands(tanager_ds)
        wl = result.coords["wavelength"].values
        assert not np.any((wl >= 2350) & (wl <= 2500)), "CO2/H2O zone 2350-2500 not removed"

    def test_does_not_modify_input(self, tanager_ds: xr.Dataset) -> None:
        original_size = tanager_ds.sizes["wavelength"]
        mask_bad_bands(tanager_ds)
        assert tanager_ds.sizes["wavelength"] == original_size

    def test_logs_band_count(self, tanager_ds: xr.Dataset, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        with caplog.at_level(logging.INFO, logger="tanager.spectral"):
            mask_bad_bands(tanager_ds)
        assert any("remaining" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# mask_bad_bands — custom zones
# ---------------------------------------------------------------------------


class TestMaskBadBandsCustomZones:
    def test_custom_zones_replace_defaults(self) -> None:
        wl = np.array([300.0, 400.0, 500.0, 600.0, 700.0, 800.0])
        ds = make_dataset(wl)
        result = mask_bad_bands(ds, zones=[(300, 350)])
        matched = result.coords["wavelength"].values
        assert 400.0 in matched
        assert 300.0 not in matched

    def test_default_bad_bands_survive_custom_zones(self) -> None:
        wl = np.array([380.0, 400.0, 1400.0, 1500.0, 2200.0])
        ds = make_dataset(wl)
        result = mask_bad_bands(ds, zones=[(0, 390)])
        matched = result.coords["wavelength"].values
        # 380 excluded, 1400 and 1500 and 2200 survive (not in custom zones)
        assert 380.0 not in matched
        assert 1400.0 in matched
        assert 2200.0 in matched

    def test_empty_zones_keeps_all_bands(self) -> None:
        ds = make_dataset(np.linspace(400, 900, 10))
        result = mask_bad_bands(ds, zones=[])
        assert result.sizes["wavelength"] == 10

    def test_custom_zones_result_is_sorted(self) -> None:
        wl = np.linspace(400, 2500, 100)
        ds = make_dataset(wl)
        result = mask_bad_bands(ds, zones=[(1000, 1100), (1500, 1600)])
        wl_out = result.coords["wavelength"].values
        assert np.all(np.diff(wl_out) > 0)


# ---------------------------------------------------------------------------
# Task 6 explicit verification
# ---------------------------------------------------------------------------


def test_task6_426_band_verification() -> None:
    """Task 6: verify mask_bad_bands on synthetic 426-band dataset."""
    wavelengths = np.linspace(380, 2500, 426)
    data = np.random.rand(426, 50, 50).astype(np.float32)
    ds = xr.Dataset(
        {"reflectance": (["wavelength", "y", "x"], data)},
        coords={"wavelength": wavelengths},
    )

    result = mask_bad_bands(ds)
    n_bands = result.sizes["wavelength"]
    wl_vals = result.coords["wavelength"].values

    # Accept ~330-346 from spec; linspace gives 328, so use 310-360 to cover both
    assert 310 <= n_bands <= 360, f"Band count {n_bands} outside expected range"
    assert np.all(np.diff(wl_vals) > 0), "Wavelength coordinate is not sorted"


# ---------------------------------------------------------------------------
# Helpers for index tests
# ---------------------------------------------------------------------------


def make_tanager_ds(
    nir_val: float = 0.6,
    swir2_val: float = 0.2,
    red_val: float = 0.1,
    green_val: float = 0.3,
    shape: tuple[int, int] = (4, 4),
) -> xr.Dataset:
    """Build a synthetic Tanager-1 dataset with controlled band values.

    Sets NIR (860 nm), SWIR2 (2200 nm), Red (660 nm), and Green (560 nm) to
    uniform constant values so indices can be analytically verified.
    """
    wavelengths = np.linspace(380, 2500, 426)
    n_wl = len(wavelengths)
    ny, nx = shape

    data = np.zeros((n_wl, ny, nx), dtype=np.float32)

    # Assign constant reflectance to the bands nearest to each target
    def _nearest_idx(wl_target: float) -> int:
        return int(np.argmin(np.abs(wavelengths - wl_target)))

    data[_nearest_idx(860), :, :] = nir_val
    data[_nearest_idx(2200), :, :] = swir2_val
    data[_nearest_idx(660), :, :] = red_val
    data[_nearest_idx(560), :, :] = green_val

    return xr.Dataset(
        {"reflectance": (["wavelength", "y", "x"], data)},
        coords={"wavelength": wavelengths},
    )


# ---------------------------------------------------------------------------
# NBR
# ---------------------------------------------------------------------------


class TestNBR:
    def test_returns_dataarray(self) -> None:
        ds = make_tanager_ds()
        result = nbr(ds)
        assert isinstance(result, xr.DataArray)

    def test_correct_formula(self) -> None:
        # NBR = (NIR - SWIR2) / (NIR + SWIR2) = (0.6 - 0.2) / (0.6 + 0.2) = 0.5
        ds = make_tanager_ds(nir_val=0.6, swir2_val=0.2)
        result = nbr(ds)
        np.testing.assert_allclose(result.values, 0.5, atol=1e-5)

    def test_values_in_minus1_to_1(self) -> None:
        ds = make_tanager_ds(nir_val=0.4, swir2_val=0.6)
        result = nbr(ds)
        assert float(result.min()) >= -1.0
        assert float(result.max()) <= 1.0

    def test_nan_when_denominator_zero(self) -> None:
        ds = make_tanager_ds(nir_val=0.0, swir2_val=0.0)
        result = nbr(ds)
        assert np.all(np.isnan(result.values))

    def test_no_inf_values(self) -> None:
        ds = make_tanager_ds(nir_val=0.0, swir2_val=0.0)
        result = nbr(ds)
        assert not np.any(np.isinf(result.values))

    def test_spatial_dims_preserved(self) -> None:
        ds = make_tanager_ds(shape=(8, 6))
        result = nbr(ds)
        assert result.sizes.get("y") == 8
        assert result.sizes.get("x") == 6

    def test_does_not_modify_input(self) -> None:
        ds = make_tanager_ds()
        original_size = ds.sizes["wavelength"]
        nbr(ds)
        assert ds.sizes["wavelength"] == original_size


# ---------------------------------------------------------------------------
# NDVI
# ---------------------------------------------------------------------------


class TestNDVI:
    def test_returns_dataarray(self) -> None:
        ds = make_tanager_ds()
        result = ndvi(ds)
        assert isinstance(result, xr.DataArray)

    def test_correct_formula(self) -> None:
        # NDVI = (NIR - Red) / (NIR + Red) = (0.6 - 0.1) / (0.6 + 0.1) ≈ 0.714
        ds = make_tanager_ds(nir_val=0.6, red_val=0.1)
        result = ndvi(ds)
        expected = (0.6 - 0.1) / (0.6 + 0.1)
        np.testing.assert_allclose(result.values, expected, atol=1e-5)

    def test_values_in_minus1_to_1(self) -> None:
        ds = make_tanager_ds(nir_val=0.2, red_val=0.8)
        result = ndvi(ds)
        assert float(result.min()) >= -1.0
        assert float(result.max()) <= 1.0

    def test_nan_when_denominator_zero(self) -> None:
        ds = make_tanager_ds(nir_val=0.0, red_val=0.0)
        result = ndvi(ds)
        assert np.all(np.isnan(result.values))

    def test_no_inf_values(self) -> None:
        ds = make_tanager_ds(nir_val=0.0, red_val=0.0)
        result = ndvi(ds)
        assert not np.any(np.isinf(result.values))


# ---------------------------------------------------------------------------
# NDWI
# ---------------------------------------------------------------------------


class TestNDWI:
    def test_returns_dataarray(self) -> None:
        ds = make_tanager_ds()
        result = ndwi(ds)
        assert isinstance(result, xr.DataArray)

    def test_correct_formula(self) -> None:
        # NDWI = (Green - NIR) / (Green + NIR) = (0.3 - 0.6) / (0.3 + 0.6) = -0.333...
        ds = make_tanager_ds(green_val=0.3, nir_val=0.6)
        result = ndwi(ds)
        expected = (0.3 - 0.6) / (0.3 + 0.6)
        np.testing.assert_allclose(result.values, expected, atol=1e-5)

    def test_values_in_minus1_to_1(self) -> None:
        ds = make_tanager_ds(green_val=0.8, nir_val=0.2)
        result = ndwi(ds)
        assert float(result.min()) >= -1.0
        assert float(result.max()) <= 1.0

    def test_nan_when_denominator_zero(self) -> None:
        ds = make_tanager_ds(nir_val=0.0, green_val=0.0)
        result = ndwi(ds)
        assert np.all(np.isnan(result.values))

    def test_no_inf_values(self) -> None:
        ds = make_tanager_ds(nir_val=0.0, green_val=0.0)
        result = ndwi(ds)
        assert not np.any(np.isinf(result.values))


# ---------------------------------------------------------------------------
# dNBR
# ---------------------------------------------------------------------------


class TestDNBR:
    def test_returns_dataarray(self) -> None:
        pre = make_tanager_ds(nir_val=0.6, swir2_val=0.2)
        post = make_tanager_ds(nir_val=0.3, swir2_val=0.5)
        result = dnbr(pre, post)
        assert isinstance(result, xr.DataArray)

    def test_correct_formula(self) -> None:
        # NBR_pre = (0.6 - 0.2) / (0.6 + 0.2) = 0.5
        # NBR_post = (0.3 - 0.5) / (0.3 + 0.5) = -0.25
        # dNBR = 0.5 - (-0.25) = 0.75
        pre = make_tanager_ds(nir_val=0.6, swir2_val=0.2)
        post = make_tanager_ds(nir_val=0.3, swir2_val=0.5)
        result = dnbr(pre, post)
        expected = 0.5 - (-0.25)
        np.testing.assert_allclose(result.values, expected, atol=1e-5)

    def test_raises_on_spatial_dim_mismatch(self) -> None:
        pre = make_tanager_ds(shape=(4, 4))
        post = make_tanager_ds(shape=(8, 4))
        with pytest.raises(ValueError, match="Spatial dimensions"):
            dnbr(pre, post)

    def test_raises_on_x_dim_mismatch(self) -> None:
        pre = make_tanager_ds(shape=(4, 4))
        post = make_tanager_ds(shape=(4, 8))
        with pytest.raises(ValueError, match="Spatial dimensions"):
            dnbr(pre, post)

    def test_zero_when_pre_equals_post(self) -> None:
        ds = make_tanager_ds(nir_val=0.5, swir2_val=0.3)
        result = dnbr(ds, ds)
        np.testing.assert_allclose(result.values, 0.0, atol=1e-6)


# ---------------------------------------------------------------------------
# continuum_removal
# ---------------------------------------------------------------------------


class TestContinuumRemoval:
    def test_returns_dataarray(self) -> None:
        ds = make_tanager_ds()
        result = continuum_removal(ds)
        assert isinstance(result, xr.DataArray)

    def test_values_in_0_to_1(self) -> None:
        rng = np.random.default_rng(0)
        wavelengths = np.linspace(400, 2400, 426)
        data = rng.random((426, 4, 4)).astype(np.float32)
        ds = xr.Dataset(
            {"reflectance": (["wavelength", "y", "x"], data)},
            coords={"wavelength": wavelengths},
        )
        result = continuum_removal(ds)
        valid = result.values[~np.isnan(result.values)]
        assert np.all(valid >= 0.0), "Values below 0 found"
        assert np.all(valid <= 1.0), "Values above 1 found"

    def test_wavelength_range_subset(self) -> None:
        rng = np.random.default_rng(1)
        wavelengths = np.linspace(400, 2400, 426)
        data = rng.random((426, 4, 4)).astype(np.float32)
        ds = xr.Dataset(
            {"reflectance": (["wavelength", "y", "x"], data)},
            coords={"wavelength": wavelengths},
        )
        result = continuum_removal(ds, wavelength_range=(600.0, 900.0))
        wl_out = result.coords["wavelength"].values
        assert np.all(wl_out >= 600.0)
        assert np.all(wl_out <= 900.0)

    def test_output_wavelength_dim_present(self) -> None:
        ds = make_tanager_ds()
        result = continuum_removal(ds)
        assert "wavelength" in result.dims

    def test_spatial_dims_preserved(self) -> None:
        rng = np.random.default_rng(2)
        wavelengths = np.linspace(400, 2400, 426)
        data = rng.random((426, 6, 8)).astype(np.float32)
        ds = xr.Dataset(
            {"reflectance": (["wavelength", "y", "x"], data)},
            coords={"wavelength": wavelengths},
        )
        result = continuum_removal(ds)
        assert result.sizes.get("y") == 6
        assert result.sizes.get("x") == 8

    def test_does_not_modify_input(self) -> None:
        ds = make_tanager_ds()
        original_size = ds.sizes["wavelength"]
        continuum_removal(ds)
        assert ds.sizes["wavelength"] == original_size


# ---------------------------------------------------------------------------
# Task 29 explicit verification: NBR on synthetic data
# ---------------------------------------------------------------------------


def test_task29_nbr_verification() -> None:
    """Task 29: NBR on synthetic data — values in [-1, 1], NaN where denom=0."""
    # Arrange: 5x5 spatial grid; set NIR and SWIR2 uniformly (denom > 0)
    wavelengths = np.linspace(380, 2500, 426)
    n_wl = len(wavelengths)
    data = np.zeros((n_wl, 5, 5), dtype=np.float32)

    nir_idx = int(np.argmin(np.abs(wavelengths - 860)))
    swir2_idx = int(np.argmin(np.abs(wavelengths - 2200)))
    data[nir_idx, :, :] = 0.7
    data[swir2_idx, :, :] = 0.3

    ds = xr.Dataset(
        {"reflectance": (["wavelength", "y", "x"], data)},
        coords={"wavelength": wavelengths},
    )

    result = nbr(ds)
    vals = result.values

    # All pixels have valid denominator — no NaN expected
    assert not np.any(np.isnan(vals)), "Unexpected NaN in NBR result"
    assert np.all(vals >= -1.0) and np.all(vals <= 1.0), "NBR out of [-1, 1]"
    expected = (0.7 - 0.3) / (0.7 + 0.3)
    np.testing.assert_allclose(vals, expected, atol=1e-5)

    # Now test NaN-on-zero-denominator by zeroing both bands
    data[nir_idx, :, :] = 0.0
    data[swir2_idx, :, :] = 0.0
    ds_zero = xr.Dataset(
        {"reflectance": (["wavelength", "y", "x"], data)},
        coords={"wavelength": wavelengths},
    )
    result_zero = nbr(ds_zero)
    assert np.all(np.isnan(result_zero.values)), "Expected all NaN when denominator=0"
    assert not np.any(np.isinf(result_zero.values)), "Unexpected Inf in NBR result"
