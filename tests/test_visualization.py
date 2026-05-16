"""Integration tests for PRODUCT_STYLES, plot_map, and save_figure.

Focuses on CRS-aware (georeferenced) DataArray rendering — the path that
other unit test files do not cover.  Each test uses a synthetic DataArray
with EPSG:32611 CRS metadata written via ``da.rio.write_crs``.

Complements (but does not duplicate) the granular tests in:
- tests/test_product_styles.py
- tests/test_plot_map.py
- tests/test_save_figure.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive backend; must be set before pyplot import

import matplotlib.pyplot as plt
import numpy as np
import pytest
import xarray as xr

import rioxarray  # noqa: F401 — registers the .rio accessor on xr.DataArray

from tanager.visualization import PRODUCT_STYLES, ProductStyle, plot_map, save_figure


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def make_georef_da(nx: int = 50, ny: int = 50) -> xr.DataArray:
    """Return a synthetic DataArray with EPSG:32611 CRS (UTM zone 11N).

    Coordinates are UTM easting/northing in metres so that ``plot_map``
    engages the geo-axes rendering path (Easting/Northing labels, km ticks).
    """
    x = np.linspace(340_000, 350_000, nx)
    y = np.linspace(3_780_000, 3_790_000, ny)
    rng = np.random.default_rng(0)
    data = rng.random((ny, nx)).astype(np.float32)
    da = xr.DataArray(data, coords={"y": y, "x": x}, dims=["y", "x"])
    da = da.rio.write_crs("EPSG:32611")
    return da


@pytest.fixture()
def georef_da() -> xr.DataArray:
    """50×50 DataArray with EPSG:32611 CRS — the primary fixture for this module."""
    return make_georef_da()


@pytest.fixture()
def georef_da_with_nan() -> xr.DataArray:
    """50×50 DataArray with EPSG:32611 CRS and a rectangular NaN patch."""
    da = make_georef_da()
    arr = da.values.copy()
    arr[15:35, 15:35] = np.nan
    da = da.copy(data=arr)
    return da.rio.write_crs("EPSG:32611")


@pytest.fixture()
def simple_fig():
    """Minimal matplotlib Figure for save_figure tests."""
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    yield fig
    plt.close(fig)


# ---------------------------------------------------------------------------
# PRODUCT_STYLES — structural checks
# ---------------------------------------------------------------------------


EXPECTED_PRODUCT_KEYS = frozenset(
    {"nbr", "ndvi", "ndwi", "dnbr", "cbi", "severity", "char", "pv", "npv", "soil", "lfmc"}
)


class TestProductStylesAllKeys:
    """PRODUCT_STYLES must contain exactly the 11 product keys."""

    def test_all_11_keys_present(self):
        assert set(PRODUCT_STYLES.keys()) == EXPECTED_PRODUCT_KEYS

    def test_has_no_extra_keys(self):
        unexpected = set(PRODUCT_STYLES.keys()) - EXPECTED_PRODUCT_KEYS
        assert not unexpected, f"Unexpected keys: {unexpected}"


class TestProductStylesCorrectTypes:
    """Each value in PRODUCT_STYLES must be a ProductStyle with valid fields."""

    @pytest.mark.parametrize("key", sorted(EXPECTED_PRODUCT_KEYS))
    def test_value_is_product_style(self, key):
        assert isinstance(PRODUCT_STYLES[key], ProductStyle)

    @pytest.mark.parametrize("key", sorted(EXPECTED_PRODUCT_KEYS))
    def test_cmap_is_non_empty_string(self, key):
        assert isinstance(PRODUCT_STYLES[key].cmap, str)
        assert PRODUCT_STYLES[key].cmap

    @pytest.mark.parametrize("key", sorted(EXPECTED_PRODUCT_KEYS))
    def test_vmin_less_than_vmax(self, key):
        style = PRODUCT_STYLES[key]
        assert style.vmin < style.vmax

    @pytest.mark.parametrize("key", sorted(EXPECTED_PRODUCT_KEYS))
    def test_label_is_non_empty_string(self, key):
        assert isinstance(PRODUCT_STYLES[key].label, str)
        assert PRODUCT_STYLES[key].label


# ---------------------------------------------------------------------------
# plot_map — CRS-aware integration tests
# ---------------------------------------------------------------------------


class TestPlotMapReturnsFigure:
    """plot_map must return a matplotlib Figure for georeferenced input."""

    def test_plot_map_returns_figure(self, georef_da):
        from matplotlib.figure import Figure

        fig = plot_map(georef_da)
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)


class TestPlotMapAxesAreUTMNotPixels:
    """With UTM x/y coordinates, xlim must be in metres (> 100 000), not pixels."""

    def test_xlim_is_utm_metres(self, georef_da):
        fig = plot_map(georef_da)
        try:
            ax = fig.get_axes()[0]
            xlo, xhi = ax.get_xlim()
            # UTM easting for zone 11N is always > 100 000 m.
            # Pixel-space x would be in [0, 50], so this assertion distinguishes the paths.
            assert xlo > 100_000, (
                f"xlim lower bound {xlo:.1f} looks like pixel-space, expected UTM metres"
            )
            assert xhi > 100_000, (
                f"xlim upper bound {xhi:.1f} looks like pixel-space, expected UTM metres"
            )
        finally:
            plt.close(fig)


class TestPlotMapColorbarPresent:
    """A colorbar axis must be appended to the figure."""

    def test_colorbar_present(self, georef_da):
        fig = plot_map(georef_da, product_name="nbr")
        try:
            # imshow axis + colorbar axis = at least 2 axes.
            assert len(fig.get_axes()) > 1, "Expected colorbar axis, found only one axis"
        finally:
            plt.close(fig)


class TestPlotMapWithProductName:
    """product_name must look up PRODUCT_STYLES and apply its settings."""

    def test_product_name_uses_style_lookup(self, georef_da):
        from matplotlib.figure import Figure

        fig = plot_map(georef_da, product_name="dnbr")
        try:
            assert isinstance(fig, Figure)
            # Colorbar label should reflect the dnbr style label.
            cb_ax = fig.get_axes()[1]
            assert PRODUCT_STYLES["dnbr"].label in cb_ax.get_ylabel()
        finally:
            plt.close(fig)

    @pytest.mark.parametrize("product", sorted(EXPECTED_PRODUCT_KEYS))
    def test_all_product_styles_render_without_error(self, georef_da, product):
        fig = plot_map(georef_da, product_name=product)
        try:
            assert len(fig.get_axes()) >= 1
        finally:
            plt.close(fig)


class TestPlotMapNanHandling:
    """DataArrays with NaN values must render without raising errors."""

    def test_nan_patch_renders_without_error(self, georef_da_with_nan):
        from matplotlib.figure import Figure

        fig = plot_map(georef_da_with_nan, product_name="nbr")
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)

    def test_all_nan_renders_without_error(self, georef_da):
        all_nan = georef_da.copy(data=np.full(georef_da.shape, np.nan))
        all_nan = all_nan.rio.write_crs("EPSG:32611")
        from matplotlib.figure import Figure

        fig = plot_map(all_nan, product_name="lfmc")
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)


class TestPlotMapWithCrsMetadata:
    """DataArray with .rio.crs set must work correctly through the full render path."""

    def test_crs_da_renders_utm_axes(self, georef_da):
        """Axes labels and xlim confirm geo rendering, not pixel rendering."""
        fig = plot_map(georef_da, product_name="ndvi")
        try:
            ax = fig.get_axes()[0]
            # UTM axes set Easting/Northing labels
            assert ax.get_xlabel() == "Easting (km)"
            assert ax.get_ylabel() == "Northing (km)"
        finally:
            plt.close(fig)

    def test_crs_da_xlim_reflects_coordinate_extent(self, georef_da):
        """xlim should span the DataArray's x coordinate range (in metres)."""
        fig = plot_map(georef_da)
        try:
            ax = fig.get_axes()[0]
            xlo, xhi = ax.get_xlim()
            # x goes from 340 000 to 350 000; half-pixel expansion stays nearby
            assert xlo < 340_000, f"xlim lower {xlo} should be just below 340 000"
            assert xhi > 350_000, f"xlim upper {xhi} should be just above 350 000"
        finally:
            plt.close(fig)

    def test_different_crs_same_utm_axes(self):
        """A DA with a different UTM CRS should still produce geo axes."""
        x = np.linspace(500_000, 510_000, 30)
        y = np.linspace(4_200_000, 4_210_000, 30)
        data = np.random.default_rng(7).random((30, 30))
        da = xr.DataArray(data, coords={"y": y, "x": x}, dims=["y", "x"])
        da = da.rio.write_crs("EPSG:32610")  # UTM zone 10N
        fig = plot_map(da)
        try:
            ax = fig.get_axes()[0]
            xlo, xhi = ax.get_xlim()
            assert xlo > 100_000  # definitely UTM metres, not pixels
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# save_figure — integration tests with real filesystem writes
# ---------------------------------------------------------------------------


class TestSaveFigureCreatesFiles:
    """save_figure must write actual files in the requested formats."""

    def test_creates_png_file(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, Path(td) / "output", ["png"])
            assert paths[0].exists()
            assert paths[0].stat().st_size > 0

    def test_creates_pdf_file(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, Path(td) / "output", ["pdf"])
            assert paths[0].exists()

    def test_creates_multiple_formats(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, Path(td) / "fig", ["png", "pdf", "svg"])
            assert len(paths) == 3
            assert all(p.exists() for p in paths)

    def test_returns_path_objects(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, Path(td) / "fig", ["png"])
            assert all(isinstance(p, Path) for p in paths)


class TestSaveFigureCreatesDirectories:
    """save_figure must create parent directories that do not yet exist."""

    def test_creates_nested_parent_dirs(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "level1" / "level2" / "level3" / "fig"
            paths = save_figure(simple_fig, target, ["png"])
            assert paths[0].exists()

    def test_works_when_parent_already_exists(self, simple_fig):
        with tempfile.TemporaryDirectory() as td:
            paths = save_figure(simple_fig, Path(td) / "fig", ["png"])
            assert paths[0].exists()

    def test_from_plot_map_georef_figure(self, georef_da):
        """End-to-end: render georef DA → save to disk."""
        fig = plot_map(georef_da, product_name="nbr")
        try:
            with tempfile.TemporaryDirectory() as td:
                paths = save_figure(fig, Path(td) / "nbr_map", ["png"])
                assert paths[0].exists()
                assert paths[0].stat().st_size > 0
        finally:
            plt.close(fig)
