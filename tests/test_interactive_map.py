"""Tests for interactive_map — leafmap/folium interactive map function.

Tests use mocking to avoid requiring a live Jupyter environment or tile server.
All scenarios are tested against the mocked leafmap (primary) and folium (fallback) backends.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest
import xarray as xr

import rioxarray  # noqa: F401 — registers .rio accessor


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def make_utm_da(nx: int = 50, ny: int = 50, seed: int = 0) -> xr.DataArray:
    """Return a synthetic DataArray in EPSG:32611 (UTM zone 11N)."""
    x = np.linspace(340_000, 350_000, nx)
    y = np.linspace(3_780_000, 3_790_000, ny)
    rng = np.random.default_rng(seed)
    data = rng.random((ny, nx)).astype(np.float32)
    da = xr.DataArray(data, coords={"y": y, "x": x}, dims=["y", "x"])
    return da.rio.write_crs("EPSG:32611")


def make_4326_da(nx: int = 30, ny: int = 30, seed: int = 1) -> xr.DataArray:
    """Return a synthetic DataArray already in EPSG:4326."""
    x = np.linspace(-118.7, -118.6, nx)
    y = np.linspace(34.1, 34.2, ny)
    rng = np.random.default_rng(seed)
    data = rng.random((ny, nx)).astype(np.float32)
    da = xr.DataArray(data, coords={"y": y, "x": x}, dims=["y", "x"])
    return da.rio.write_crs("EPSG:4326")


def make_perimeter_gdf():
    """Return a one-polygon GeoDataFrame in EPSG:4326."""
    import geopandas as gpd
    from shapely.geometry import Polygon

    poly = Polygon([(-118.5, 34.0), (-118.4, 34.0), (-118.4, 34.1), (-118.5, 34.1)])
    return gpd.GeoDataFrame({"name": ["Test Fire"]}, geometry=[poly], crs="EPSG:4326")


@pytest.fixture()
def utm_da() -> xr.DataArray:
    return make_utm_da()


@pytest.fixture()
def mock_leafmap():
    """MagicMock substituting for the leafmap module."""
    mock = MagicMock()
    mock_map = MagicMock()
    mock.Map.return_value = mock_map
    return mock


@pytest.fixture()
def mock_folium():
    """MagicMock substituting for the folium module."""
    mock = MagicMock()
    mock_map = MagicMock()
    mock.Map.return_value = mock_map
    return mock


# ---------------------------------------------------------------------------
# Helper: patch sys.modules so leafmap is unavailable
# ---------------------------------------------------------------------------


def _with_leafmap_absent(fn, *args, **kwargs):
    """Call *fn* with leafmap absent from sys.modules."""
    saved = sys.modules.get("leafmap", None)
    sys.modules["leafmap"] = None  # None causes ImportError on 'import leafmap'
    try:
        return fn(*args, **kwargs)
    finally:
        if saved is None:
            sys.modules.pop("leafmap", None)
        else:
            sys.modules["leafmap"] = saved


# ---------------------------------------------------------------------------
# TestInteractiveMapReturnsMap — basic return-value and Map-object tests
# ---------------------------------------------------------------------------


class TestInteractiveMapReturnsMap:
    """interactive_map must return the Map object produced by leafmap.Map."""

    def test_returns_leafmap_map_object(self, utm_da, mock_leafmap):
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            result = interactive_map([(utm_da, "nbr")])

        assert result is mock_leafmap.Map.return_value

    def test_returns_map_with_no_layers(self, mock_leafmap):
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            result = interactive_map()

        assert result is mock_leafmap.Map.return_value

    def test_none_layers_same_as_empty(self, mock_leafmap):
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            result = interactive_map(layers=None)

        assert result is mock_leafmap.Map.return_value


# ---------------------------------------------------------------------------
# TestInteractiveMapLeafmapCenterZoom — center, zoom, and basemap arguments
# ---------------------------------------------------------------------------


class TestInteractiveMapLeafmapCenterZoom:
    """leafmap.Map must receive the correct center, zoom, and basemap arguments."""

    def test_default_satellite_basemap(self, utm_da, mock_leafmap):
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")])

        call_kwargs = mock_leafmap.Map.call_args[1]
        assert call_kwargs.get("basemap") == "Esri.WorldImagery"

    def test_explicit_center_passed_through(self, utm_da, mock_leafmap):
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")], center=(35.0, -120.0))

        call_kwargs = mock_leafmap.Map.call_args[1]
        assert call_kwargs["center"] == [35.0, -120.0]

    def test_explicit_zoom_passed_through(self, utm_da, mock_leafmap):
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")], zoom=8)

        call_kwargs = mock_leafmap.Map.call_args[1]
        assert call_kwargs["zoom"] == 8

    def test_center_defaults_to_layer_centroid(self, utm_da, mock_leafmap):
        """When center is None, it should default to the centroid of the first layer."""
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")])

        call_kwargs = mock_leafmap.Map.call_args[1]
        lat, lon = call_kwargs["center"]
        # EPSG:32611 UTM zone 11N maps to roughly lon=-118.x, lat=34.x
        assert -120.0 < lon < -118.0, f"Lon {lon} out of expected range for zone 11N"
        assert 33.0 < lat < 36.0, f"Lat {lat} out of expected range for zone 11N"

    def test_center_defaults_to_continental_us_when_no_layers(self, mock_leafmap):
        """With no layers, center must fall back to continental US centroid."""
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map()

        call_kwargs = mock_leafmap.Map.call_args[1]
        lat, lon = call_kwargs["center"]
        # continental US default is (39.5, -98.35)
        assert abs(lat - 39.5) < 1.0
        assert abs(lon - (-98.35)) < 1.0

    def test_osm_basemap_alias(self, utm_da, mock_leafmap):
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")], basemap="osm")

        call_kwargs = mock_leafmap.Map.call_args[1]
        assert call_kwargs.get("basemap") == "OpenStreetMap"

    def test_unknown_basemap_passed_through_raw(self, utm_da, mock_leafmap):
        """An unrecognised basemap string must be forwarded to leafmap unchanged."""
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")], basemap="CustomXYZ")

        call_kwargs = mock_leafmap.Map.call_args[1]
        assert call_kwargs.get("basemap") == "CustomXYZ"


# ---------------------------------------------------------------------------
# TestInteractiveMapAddRaster — raster layer addition
# ---------------------------------------------------------------------------


class TestInteractiveMapAddRaster:
    """add_raster must be called once per layer with correct style arguments."""

    def test_add_raster_called_once_for_single_layer(self, utm_da, mock_leafmap):
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")])

        mock_map = mock_leafmap.Map.return_value
        assert mock_map.add_raster.call_count == 1

    def test_add_raster_receives_nbr_style(self, utm_da, mock_leafmap):
        """add_raster must be given the NBR colormap and scale from PRODUCT_STYLES."""
        from tanager.visualization import interactive_map
        from tanager.visualization import PRODUCT_STYLES

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")])

        mock_map = mock_leafmap.Map.return_value
        call_kwargs = mock_map.add_raster.call_args[1]
        style = PRODUCT_STYLES["nbr"]
        assert call_kwargs["colormap"] == style.cmap
        assert call_kwargs["vmin"] == style.vmin
        assert call_kwargs["vmax"] == style.vmax
        assert call_kwargs["layer_name"] == "nbr"

    def test_add_raster_receives_tif_path(self, utm_da, mock_leafmap):
        """add_raster first positional arg must be a path string ending in .tif."""
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")])

        mock_map = mock_leafmap.Map.return_value
        raster_path = mock_map.add_raster.call_args[0][0]
        assert raster_path.endswith(".tif"), f"Expected .tif path, got {raster_path!r}"

    def test_tif_file_exists_on_disk(self, utm_da, mock_leafmap):
        """The temp GeoTIFF written for add_raster must exist on disk."""
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")])

        mock_map = mock_leafmap.Map.return_value
        raster_path = mock_map.add_raster.call_args[0][0]
        assert Path(raster_path).exists(), f"Temp raster {raster_path!r} not found on disk"

    def test_add_raster_called_twice_for_two_layers(self, utm_da, mock_leafmap):
        from tanager.visualization import interactive_map

        da2 = make_utm_da(seed=5)
        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr"), (da2, "ndvi")])

        mock_map = mock_leafmap.Map.return_value
        assert mock_map.add_raster.call_count == 2

    def test_unknown_product_name_still_calls_add_raster(self, utm_da, mock_leafmap):
        """An unrecognised product_name must still call add_raster (with None style)."""
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "unknown_product")])

        mock_map = mock_leafmap.Map.return_value
        assert mock_map.add_raster.call_count == 1
        call_kwargs = mock_map.add_raster.call_args[1]
        assert call_kwargs["colormap"] is None

    def test_reprojection_to_4326_before_write(self, mock_leafmap):
        """A UTM DataArray must be reprojected to EPSG:4326 before writing the GeoTIFF."""
        from tanager.visualization import interactive_map

        da_utm = make_utm_da()
        calls_seen: list = []

        original_to_raster = None

        def _spy_to_raster(da, path):
            calls_seen.append({"da": da, "path": path})
            da.rio.to_raster(path)

        # We can verify indirectly: the raster at the temp path must have EPSG:4326 CRS
        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(da_utm, "nbr")])

        mock_map = mock_leafmap.Map.return_value
        raster_path = mock_map.add_raster.call_args[0][0]

        # Read back the written tif and verify CRS
        import rasterio
        with rasterio.open(raster_path) as src:
            crs_str = src.crs.to_epsg()
        assert crs_str == 4326, f"Expected EPSG:4326 in written TIF, got EPSG:{crs_str}"


# ---------------------------------------------------------------------------
# TestInteractiveMapLayerControl — layer control widget
# ---------------------------------------------------------------------------


class TestInteractiveMapLayerControl:
    """add_layer_control must always be called."""

    def test_layer_control_added_with_layers(self, utm_da, mock_leafmap):
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")])

        mock_map = mock_leafmap.Map.return_value
        assert mock_map.add_layer_control.called

    def test_layer_control_added_without_layers(self, mock_leafmap):
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map()

        mock_map = mock_leafmap.Map.return_value
        assert mock_map.add_layer_control.called


# ---------------------------------------------------------------------------
# TestInteractiveMapPerimeters — fire perimeter overlays
# ---------------------------------------------------------------------------


class TestInteractiveMapPerimeters:
    """Fire perimeters must be added as a GeoJSON layer when provided."""

    def test_perimeters_as_geodataframe(self, utm_da, mock_leafmap):
        """GeoDataFrame perimeters must trigger add_geojson on the map."""
        from tanager.visualization import interactive_map

        gdf = make_perimeter_gdf()
        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")], perimeters=gdf)

        mock_map = mock_leafmap.Map.return_value
        assert mock_map.add_geojson.called

    def test_perimeters_geojson_layer_name(self, utm_da, mock_leafmap):
        from tanager.visualization import interactive_map

        gdf = make_perimeter_gdf()
        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")], perimeters=gdf)

        mock_map = mock_leafmap.Map.return_value
        call_kwargs = mock_map.add_geojson.call_args[1]
        assert call_kwargs.get("layer_name") == "Fire Perimeters"

    def test_perimeters_as_path(self, utm_da, mock_leafmap):
        """Perimeters given as a file path must be loaded and added."""
        from tanager.visualization import interactive_map

        # Write a minimal GeoJSON to a temp file
        feature = {
            "type": "Feature",
            "properties": {"name": "Path Test Fire"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-118.5, 34.0], [-118.4, 34.0],
                    [-118.4, 34.1], [-118.5, 34.1],
                    [-118.5, 34.0],
                ]],
            },
        }
        geojson = {"type": "FeatureCollection", "features": [feature]}

        with tempfile.NamedTemporaryFile(
            suffix=".geojson", mode="w", delete=False, dir=tempfile.gettempdir()
        ) as f:
            json.dump(geojson, f)
            tmp_path = Path(f.name)

        try:
            with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
                interactive_map([(utm_da, "nbr")], perimeters=tmp_path)

            mock_map = mock_leafmap.Map.return_value
            assert mock_map.add_geojson.called, "add_geojson not called for path perimeters"
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_no_perimeters_no_geojson_call(self, utm_da, mock_leafmap):
        """When perimeters=None, add_geojson must not be called."""
        from tanager.visualization import interactive_map

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            interactive_map([(utm_da, "nbr")], perimeters=None)

        mock_map = mock_leafmap.Map.return_value
        assert not mock_map.add_geojson.called


# ---------------------------------------------------------------------------
# TestInteractiveMapFoliumFallback — folium path
# ---------------------------------------------------------------------------


class TestInteractiveMapFoliumFallback:
    """When leafmap is absent, folium.Map must be used as the fallback."""

    def test_returns_folium_map_when_leafmap_absent(self, utm_da, mock_folium):
        from tanager.visualization import interactive_map

        saved = sys.modules.get("leafmap", ...)
        sys.modules["leafmap"] = None  # force ImportError

        try:
            with patch.dict("sys.modules", {"folium": mock_folium}):
                result = interactive_map([(utm_da, "nbr")])
        finally:
            if saved is ...:
                sys.modules.pop("leafmap", None)
            else:
                sys.modules["leafmap"] = saved

        assert result is mock_folium.Map.return_value

    def test_folium_map_receives_center(self, utm_da, mock_folium):
        from tanager.visualization import interactive_map

        saved = sys.modules.get("leafmap", ...)
        sys.modules["leafmap"] = None

        try:
            with patch.dict("sys.modules", {"folium": mock_folium}):
                interactive_map([(utm_da, "nbr")], center=(34.5, -118.5))
        finally:
            if saved is ...:
                sys.modules.pop("leafmap", None)
            else:
                sys.modules["leafmap"] = saved

        call_kwargs = mock_folium.Map.call_args[1]
        assert call_kwargs["location"] == [34.5, -118.5]

    def test_folium_image_overlay_added(self, utm_da, mock_folium):
        """folium.raster_layers.ImageOverlay must be instantiated for each raster layer."""
        from tanager.visualization import interactive_map

        saved = sys.modules.get("leafmap", ...)
        sys.modules["leafmap"] = None

        try:
            with patch.dict("sys.modules", {"folium": mock_folium}):
                interactive_map([(utm_da, "nbr")])
        finally:
            if saved is ...:
                sys.modules.pop("leafmap", None)
            else:
                sys.modules["leafmap"] = saved

        # ImageOverlay must have been called
        assert mock_folium.raster_layers.ImageOverlay.called

    def test_folium_layer_control_added(self, utm_da, mock_folium):
        from tanager.visualization import interactive_map

        saved = sys.modules.get("leafmap", ...)
        sys.modules["leafmap"] = None

        try:
            with patch.dict("sys.modules", {"folium": mock_folium}):
                interactive_map([(utm_da, "nbr")])
        finally:
            if saved is ...:
                sys.modules.pop("leafmap", None)
            else:
                sys.modules["leafmap"] = saved

        assert mock_folium.LayerControl.called


# ---------------------------------------------------------------------------
# TestInteractiveMapImportError — both backends absent
# ---------------------------------------------------------------------------


class TestInteractiveMapImportError:
    """ImportError must be raised with a helpful message when both backends are missing."""

    def test_raises_import_error_when_both_absent(self, utm_da):
        from tanager.visualization import interactive_map

        saved_leafmap = sys.modules.get("leafmap", ...)
        saved_folium = sys.modules.get("folium", ...)
        sys.modules["leafmap"] = None
        sys.modules["folium"] = None

        try:
            with pytest.raises(ImportError, match="leafmap.*folium"):
                interactive_map([(utm_da, "nbr")])
        finally:
            for name, saved in [("leafmap", saved_leafmap), ("folium", saved_folium)]:
                if saved is ...:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = saved

    def test_import_error_message_mentions_install(self, utm_da):
        from tanager.visualization import interactive_map

        saved_leafmap = sys.modules.get("leafmap", ...)
        saved_folium = sys.modules.get("folium", ...)
        sys.modules["leafmap"] = None
        sys.modules["folium"] = None

        try:
            with pytest.raises(ImportError) as exc_info:
                interactive_map([(utm_da, "nbr")])
            assert "pip install" in str(exc_info.value)
        finally:
            for name, saved in [("leafmap", saved_leafmap), ("folium", saved_folium)]:
                if saved is ...:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = saved


# ---------------------------------------------------------------------------
# TestInteractiveMapInputVariety — various DataArray configurations
# ---------------------------------------------------------------------------


class TestInteractiveMapInputVariety:
    """interactive_map must handle DataArrays with different CRS and multiple layers."""

    def test_already_4326_da_no_reprojection_needed(self, mock_leafmap):
        """A DataArray already in EPSG:4326 must be handled without error."""
        from tanager.visualization import interactive_map

        da_4326 = make_4326_da()
        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            result = interactive_map([(da_4326, "nbr")])

        assert result is mock_leafmap.Map.return_value
        mock_map = mock_leafmap.Map.return_value
        assert mock_map.add_raster.call_count == 1

    def test_multiple_layers_with_different_products(self, mock_leafmap):
        from tanager.visualization import interactive_map

        da1 = make_utm_da(seed=10)
        da2 = make_utm_da(seed=11)
        da3 = make_utm_da(seed=12)

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            result = interactive_map([(da1, "nbr"), (da2, "dnbr"), (da3, "lfmc")])

        mock_map = mock_leafmap.Map.return_value
        assert mock_map.add_raster.call_count == 3

        # Each layer must get the correct product name
        names = [c[1]["layer_name"] for c in mock_map.add_raster.call_args_list]
        assert names == ["nbr", "dnbr", "lfmc"]

    def test_layer_with_nan_values_renders_without_error(self, mock_leafmap):
        """DataArrays containing NaN must not cause an error in interactive_map."""
        from tanager.visualization import interactive_map

        da_nan = make_utm_da(seed=7)
        arr = da_nan.values.copy()
        arr[10:20, 10:20] = np.nan
        da_nan = da_nan.copy(data=arr)

        with patch.dict("sys.modules", {"leafmap": mock_leafmap}):
            result = interactive_map([(da_nan, "nbr")])

        assert result is mock_leafmap.Map.return_value
