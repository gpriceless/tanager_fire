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


# ---------------------------------------------------------------------------
# Integration tests — basemap, perimeters, and scalebar working together
# ---------------------------------------------------------------------------


class TestAddBasemapWithMockedContextily:
    """add_basemap must call contextily and return ax unchanged when mocked."""

    def test_mock_is_called(self, georef_da):
        """Verify contextily.add_basemap is invoked when add_basemap is called."""
        from unittest.mock import patch
        from tanager.visualization import add_basemap

        fig, ax = plt.subplots()
        ax.set_xlim(340_000, 350_000)
        ax.set_ylim(3_780_000, 3_790_000)
        try:
            with patch("contextily.add_basemap") as mock_ctx:
                result = add_basemap(ax)
            assert mock_ctx.called
        finally:
            plt.close(fig)

    def test_ax_returned_unchanged(self, georef_da):
        """add_basemap must return the exact same Axes object."""
        from unittest.mock import patch
        from tanager.visualization import add_basemap

        fig, ax = plt.subplots()
        ax.set_xlim(340_000, 350_000)
        ax.set_ylim(3_780_000, 3_790_000)
        try:
            with patch("contextily.add_basemap"):
                result = add_basemap(ax)
            assert result is ax
        finally:
            plt.close(fig)

    def test_xlim_ylim_preserved_after_call(self, georef_da):
        """Axes limits must not be altered by add_basemap."""
        from unittest.mock import patch
        from tanager.visualization import add_basemap

        fig, ax = plt.subplots()
        ax.set_xlim(340_000, 350_000)
        ax.set_ylim(3_780_000, 3_790_000)
        xlim_before = ax.get_xlim()
        ylim_before = ax.get_ylim()
        try:
            with patch("contextily.add_basemap"):
                add_basemap(ax)
            assert ax.get_xlim() == xlim_before
            assert ax.get_ylim() == ylim_before
        finally:
            plt.close(fig)


class TestAddBasemapOfflineGracefulDegradation:
    """add_basemap must not raise and must return ax when contextily fails."""

    def test_oserror_does_not_propagate(self):
        """OSError from contextily is swallowed; no exception escapes."""
        from unittest.mock import patch
        from tanager.visualization import add_basemap

        fig, ax = plt.subplots()
        ax.set_xlim(340_000, 350_000)
        ax.set_ylim(3_780_000, 3_790_000)
        try:
            with patch("contextily.add_basemap", side_effect=OSError("Network unreachable")):
                result = add_basemap(ax)
            assert result is ax
        finally:
            plt.close(fig)

    def test_ax_returned_after_network_failure(self):
        """ax is returned even when the tile fetch raises."""
        from unittest.mock import patch
        from tanager.visualization import add_basemap

        fig, ax = plt.subplots()
        ax.set_xlim(340_000, 350_000)
        ax.set_ylim(3_780_000, 3_790_000)
        try:
            with patch("contextily.add_basemap", side_effect=OSError("DNS failure")):
                result = add_basemap(ax)
            # ax is unchanged; no AttributeError, no None return
            assert result is ax
        finally:
            plt.close(fig)


class TestLoadFirePerimetersWithSyntheticGeoJSON:
    """load_fire_perimeters reads a small synthetic GeoJSON fixture correctly."""

    def test_returns_geodataframe_with_geometry(self):
        """A minimal GeoJSON file produces a GeoDataFrame with a geometry column."""
        import json
        import geopandas as gpd
        from tanager.visualization import load_fire_perimeters

        feature = {
            "type": "Feature",
            "properties": {"name": "Test Fire"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-118.5, 34.0],
                        [-118.4, 34.0],
                        [-118.4, 34.1],
                        [-118.5, 34.1],
                        [-118.5, 34.0],
                    ]
                ],
            },
        }
        geojson = {"type": "FeatureCollection", "features": [feature]}

        with tempfile.NamedTemporaryFile(
            suffix=".geojson", mode="w", delete=False, dir=tempfile.gettempdir()
        ) as f:
            json.dump(geojson, f)
            tmp_path = Path(f.name)

        try:
            gdf = load_fire_perimeters(tmp_path)
            assert isinstance(gdf, gpd.GeoDataFrame)
            assert "geometry" in gdf.columns
            assert len(gdf) == 1
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_feature_property_accessible(self):
        """Properties from the GeoJSON are available as GeoDataFrame columns."""
        import json
        from tanager.visualization import load_fire_perimeters

        feature = {
            "type": "Feature",
            "properties": {"name": "Integration Fire", "area_ha": 500},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-118.3, 34.0],
                        [-118.2, 34.0],
                        [-118.2, 34.1],
                        [-118.3, 34.1],
                        [-118.3, 34.0],
                    ]
                ],
            },
        }
        geojson = {"type": "FeatureCollection", "features": [feature]}

        with tempfile.NamedTemporaryFile(
            suffix=".geojson", mode="w", delete=False, dir=tempfile.gettempdir()
        ) as f:
            json.dump(geojson, f)
            tmp_path = Path(f.name)

        try:
            gdf = load_fire_perimeters(tmp_path)
            assert gdf.iloc[0]["name"] == "Integration Fire"
        finally:
            tmp_path.unlink(missing_ok=True)


class TestOverlayPerimetersDrawsOnAxes:
    """overlay_perimeters must add collections or lines to the axes."""

    def _make_synthetic_gdf(self):
        """Return a one-polygon GeoDataFrame in EPSG:4326."""
        import geopandas as gpd
        from shapely.geometry import Polygon

        poly = Polygon(
            [(-118.5, 34.0), (-118.4, 34.0), (-118.4, 34.1), (-118.5, 34.1)]
        )
        return gpd.GeoDataFrame(
            {"name": ["Synthetic Fire"]}, geometry=[poly], crs="EPSG:4326"
        )

    def test_collection_added_to_axes(self):
        """At least one collection or line must appear on ax after the call."""
        from tanager.visualization import overlay_perimeters

        fig, ax = plt.subplots()
        ax.set_xlim(340_000, 350_000)
        ax.set_ylim(3_780_000, 3_790_000)
        gdf = self._make_synthetic_gdf()
        try:
            overlay_perimeters(ax, gdf, label=False)
            assert len(ax.collections) > 0 or len(ax.lines) > 0
        finally:
            plt.close(fig)

    def test_returns_same_axes_object(self):
        """overlay_perimeters must return the identical Axes passed in."""
        from tanager.visualization import overlay_perimeters

        fig, ax = plt.subplots()
        ax.set_xlim(340_000, 350_000)
        ax.set_ylim(3_780_000, 3_790_000)
        gdf = self._make_synthetic_gdf()
        try:
            result = overlay_perimeters(ax, gdf, label=False)
            assert result is ax
        finally:
            plt.close(fig)

    def test_label_text_appears_when_requested(self):
        """When label=True, a text annotation is added to ax."""
        from tanager.visualization import overlay_perimeters

        fig, ax = plt.subplots()
        ax.set_xlim(340_000, 350_000)
        ax.set_ylim(3_780_000, 3_790_000)
        gdf = self._make_synthetic_gdf()
        try:
            overlay_perimeters(ax, gdf, label=True)
            assert len(ax.texts) > 0
        finally:
            plt.close(fig)


class TestAddScalebarAddsPatch:
    """add_scalebar must add a Rectangle patch with the correct width."""

    def _make_ax(self):
        """Return a Figure and Axes with UTM-scale limits."""
        fig, ax = plt.subplots()
        ax.set_xlim(340_000, 350_000)
        ax.set_ylim(3_780_000, 3_790_000)
        return fig, ax

    def test_patch_is_added(self):
        """A Rectangle patch must appear in ax.patches."""
        from tanager.visualization import add_scalebar

        fig, ax = self._make_ax()
        try:
            add_scalebar(ax, 5)
            assert len(ax.patches) >= 1
        finally:
            plt.close(fig)

    def test_patch_width_matches_requested_km(self):
        """Bar width in data coordinates must equal length_km * 1000 metres."""
        from tanager.visualization import add_scalebar

        fig, ax = self._make_ax()
        try:
            add_scalebar(ax, 5)
            rect = ax.patches[0]
            assert rect.get_width() == pytest.approx(5000.0)
        finally:
            plt.close(fig)

    def test_text_label_is_present(self):
        """A '5 km' label must be placed above the bar."""
        from tanager.visualization import add_scalebar

        fig, ax = self._make_ax()
        try:
            add_scalebar(ax, 5)
            labels = [t.get_text() for t in ax.texts]
            assert "5 km" in labels
        finally:
            plt.close(fig)

    def test_different_lengths_produce_correct_widths(self):
        """1 km and 10 km requests must produce 1 000 and 10 000 m widths."""
        from tanager.visualization import add_scalebar

        for km, expected_m in [(1, 1000.0), (10, 10_000.0)]:
            fig, ax = self._make_ax()
            try:
                add_scalebar(ax, km)
                assert ax.patches[0].get_width() == pytest.approx(expected_m)
            finally:
                plt.close(fig)


class TestEndToEndPlotMapBasemapPerimetersScalebar:
    """Full pipeline: plot_map → overlay_perimeters → add_scalebar, mocked basemap."""

    def test_all_elements_present_on_figure(self, georef_da):
        """After running the full pipeline the figure must have all expected elements."""
        import json
        import geopandas as gpd
        from shapely.geometry import Polygon
        from unittest.mock import patch
        from tanager.visualization import plot_map, overlay_perimeters, add_scalebar

        # Step 1: render the base map with a mocked basemap tile call.
        with patch("contextily.add_basemap"):
            fig = plot_map(georef_da, basemap=True, product_name="nbr")

        try:
            ax = fig.get_axes()[0]

            # Step 2: overlay a synthetic perimeter.
            poly = Polygon(
                [(-118.5, 34.0), (-118.4, 34.0), (-118.4, 34.1), (-118.5, 34.1)]
            )
            gdf = gpd.GeoDataFrame(
                {"name": ["Integration Fire"]}, geometry=[poly], crs="EPSG:4326"
            )
            overlay_perimeters(ax, gdf, label=True)

            # Step 3: add a scale bar.
            add_scalebar(ax, 5)

            # Assertions — figure has all expected elements.
            from matplotlib.figure import Figure
            assert isinstance(fig, Figure)

            # Colorbar axis present (from plot_map).
            assert len(fig.get_axes()) > 1

            # Perimeter boundary: collections or lines.
            assert len(ax.collections) > 0 or len(ax.lines) > 0

            # Scalebar patch present.
            assert len(ax.patches) >= 1

            # Scalebar label text present.
            scalebar_labels = [t.get_text() for t in ax.texts if "km" in t.get_text()]
            assert scalebar_labels, "Expected at least one '… km' label from add_scalebar"
        finally:
            plt.close(fig)

    def test_network_failure_does_not_abort_pipeline(self, georef_da):
        """Even when the basemap tile fetch fails, the rest of the pipeline works."""
        import geopandas as gpd
        from shapely.geometry import Polygon
        from unittest.mock import patch
        from tanager.visualization import plot_map, overlay_perimeters, add_scalebar
        from matplotlib.figure import Figure

        with patch("contextily.add_basemap", side_effect=OSError("no network")):
            fig = plot_map(georef_da, basemap=True)

        try:
            assert isinstance(fig, Figure)
            ax = fig.get_axes()[0]

            poly = Polygon(
                [(-118.5, 34.0), (-118.4, 34.0), (-118.4, 34.1), (-118.5, 34.1)]
            )
            gdf = gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326")
            overlay_perimeters(ax, gdf, label=False)
            add_scalebar(ax, 3)

            assert len(ax.patches) >= 1
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# plot_before_after — side-by-side pre/post comparison
# ---------------------------------------------------------------------------


def _make_pre_da() -> xr.DataArray:
    """Pre-fire DataArray (smaller spatial extent, 70x70)."""
    x = np.linspace(340_000, 347_000, 70)
    y = np.linspace(3_780_000, 3_787_000, 70)
    rng = np.random.default_rng(1)
    return xr.DataArray(rng.random((70, 70)) * 0.8, coords={"y": y, "x": x}, dims=["y", "x"])


def _make_post_da() -> xr.DataArray:
    """Post-fire DataArray (larger spatial extent, 100x100)."""
    x = np.linspace(339_000, 350_000, 100)
    y = np.linspace(3_779_000, 3_790_000, 100)
    rng = np.random.default_rng(2)
    return xr.DataArray(rng.random((100, 100)) * 0.3, coords={"y": y, "x": x}, dims=["y", "x"])


class TestPlotBeforeAfterReturnsFigure:
    """plot_before_after must return a matplotlib Figure."""

    def test_returns_figure(self):
        from matplotlib.figure import Figure
        from tanager.visualization import plot_before_after

        pre, post = _make_pre_da(), _make_post_da()
        fig = plot_before_after(pre, post, "nbr")
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)


class TestPlotBeforeAfterTwoPanels:
    """Figure must contain at least 2 map axes (plus colorbar)."""

    def test_has_at_least_three_axes(self):
        """2 map panels + 1 shared colorbar = at least 3 axes."""
        from tanager.visualization import plot_before_after

        pre, post = _make_pre_da(), _make_post_da()
        fig = plot_before_after(pre, post, "nbr")
        try:
            assert len(fig.axes) >= 3, (
                f"Expected >= 3 axes (2 map + colorbar), got {len(fig.axes)}"
            )
        finally:
            plt.close(fig)

    def test_panel_titles_match_labels(self):
        """Panel titles must use the supplied pre_label and post_label strings."""
        from tanager.visualization import plot_before_after

        pre, post = _make_pre_da(), _make_post_da()
        fig = plot_before_after(
            pre, post, "nbr",
            pre_label="Dec 15 Pre-Fire",
            post_label="Jan 23 Post-Fire",
        )
        try:
            titles = [ax.get_title() for ax in fig.axes[:2]]
            assert titles[0] == "Dec 15 Pre-Fire"
            assert titles[1] == "Jan 23 Post-Fire"
        finally:
            plt.close(fig)

    def test_default_panel_titles_when_no_labels(self):
        """Default titles must be 'Pre-Fire' and 'Post-Fire'."""
        from tanager.visualization import plot_before_after

        pre, post = _make_pre_da(), _make_post_da()
        fig = plot_before_after(pre, post, "nbr")
        try:
            titles = [ax.get_title() for ax in fig.axes[:2]]
            assert titles[0] == "Pre-Fire"
            assert titles[1] == "Post-Fire"
        finally:
            plt.close(fig)


class TestPlotBeforeAfterUTMAxes:
    """Both panels must render UTM metre-scale axes (not pixel indices)."""

    def test_pre_panel_xlim_is_utm(self):
        from tanager.visualization import plot_before_after

        pre, post = _make_pre_da(), _make_post_da()
        fig = plot_before_after(pre, post, "nbr")
        try:
            ax_pre = fig.axes[0]
            xlo, xhi = ax_pre.get_xlim()
            assert xlo > 100_000, f"Pre panel xlim lower {xlo} looks like pixels"
            assert xhi > 100_000, f"Pre panel xlim upper {xhi} looks like pixels"
        finally:
            plt.close(fig)

    def test_post_panel_xlim_is_utm(self):
        from tanager.visualization import plot_before_after

        pre, post = _make_pre_da(), _make_post_da()
        fig = plot_before_after(pre, post, "nbr")
        try:
            ax_post = fig.axes[1]
            xlo, xhi = ax_post.get_xlim()
            assert xlo > 100_000, f"Post panel xlim lower {xlo} looks like pixels"
            assert xhi > 100_000, f"Post panel xlim upper {xhi} looks like pixels"
        finally:
            plt.close(fig)

    def test_panels_have_different_extents_for_different_size_inputs(self):
        """Pre and post scenes with different extents should produce different xlims."""
        from tanager.visualization import plot_before_after

        pre, post = _make_pre_da(), _make_post_da()
        fig = plot_before_after(pre, post, "nbr")
        try:
            xlo_pre, xhi_pre = fig.axes[0].get_xlim()
            xlo_post, xhi_post = fig.axes[1].get_xlim()
            # Pre x runs 340–347k; post runs 339–350k — they differ
            assert xhi_post > xhi_pre, (
                f"Post xlim upper {xhi_post} should exceed pre {xhi_pre} for wider scene"
            )
        finally:
            plt.close(fig)


class TestPlotBeforeAfterNaNHandling:
    """NaN values in pre or post must render without error."""

    def test_pre_with_nan_renders(self):
        from matplotlib.figure import Figure
        from tanager.visualization import plot_before_after

        pre = _make_pre_da()
        arr = pre.values.copy()
        arr[10:30, 10:30] = np.nan
        pre_nan = pre.copy(data=arr)
        post = _make_post_da()

        fig = plot_before_after(pre_nan, post, "nbr")
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)

    def test_post_all_nan_renders(self):
        from matplotlib.figure import Figure
        from tanager.visualization import plot_before_after

        pre = _make_pre_da()
        post = _make_post_da()
        post_nan = post.copy(data=np.full(post.shape, np.nan))

        fig = plot_before_after(pre, post_nan, "nbr")
        try:
            assert isinstance(fig, Figure)
        finally:
            plt.close(fig)


class TestPlotBeforeAfterAllProducts:
    """plot_before_after must render without error for every product in PRODUCT_STYLES."""

    @pytest.mark.parametrize("product", sorted({
        "nbr", "ndvi", "ndwi", "dnbr", "cbi", "severity", "char", "pv", "npv", "soil", "lfmc"
    }))
    def test_all_products_render(self, product):
        from tanager.visualization import plot_before_after

        pre, post = _make_pre_da(), _make_post_da()
        fig = plot_before_after(pre, post, product)
        try:
            assert len(fig.axes) >= 3
        finally:
            plt.close(fig)


class TestPlotBeforeAfterPublicationMode:
    """publication=True must set DPI to 300."""

    def test_publication_dpi(self):
        from tanager.visualization import plot_before_after

        pre, post = _make_pre_da(), _make_post_da()
        fig = plot_before_after(pre, post, "nbr", publication=True)
        try:
            assert fig.get_dpi() == 300
        finally:
            plt.close(fig)


class TestPlotBeforeAfterFirePerimeters:
    """When fire_perimeters is provided, both panels must get perimeter overlays."""

    def _make_perimeters(self):
        import geopandas as gpd
        from shapely.geometry import Polygon

        poly = Polygon(
            [(-118.5, 34.0), (-118.4, 34.0), (-118.4, 34.1), (-118.5, 34.1)]
        )
        return gpd.GeoDataFrame(
            {"name": ["Test Fire"]}, geometry=[poly], crs="EPSG:4326"
        )

    def test_perimeters_added_to_both_panels(self):
        """Each panel must gain at least one collection or line from the perimeter overlay."""
        from tanager.visualization import plot_before_after

        pre, post = _make_pre_da(), _make_post_da()
        perimeters = self._make_perimeters()

        fig = plot_before_after(pre, post, "nbr", fire_perimeters=perimeters)
        try:
            ax_pre = fig.axes[0]
            ax_post = fig.axes[1]
            pre_has_overlay = len(ax_pre.collections) > 0 or len(ax_pre.lines) > 0
            post_has_overlay = len(ax_post.collections) > 0 or len(ax_post.lines) > 0
            assert pre_has_overlay, "Pre-fire panel missing perimeter overlay"
            assert post_has_overlay, "Post-fire panel missing perimeter overlay"
        finally:
            plt.close(fig)


class TestPlotBeforeAfterBasemap:
    """When basemap=True, add_basemap must be called on both panels."""

    def test_basemap_called_on_both_panels(self):
        from unittest.mock import patch
        from tanager.visualization import plot_before_after

        pre, post = _make_pre_da(), _make_post_da()
        with patch("contextily.add_basemap") as mock_ctx:
            fig = plot_before_after(pre, post, "nbr", basemap=True)
        try:
            # add_basemap is called once per panel, so 2 calls total
            assert mock_ctx.call_count == 2, (
                f"Expected 2 contextily.add_basemap calls, got {mock_ctx.call_count}"
            )
        finally:
            plt.close(fig)
