"""Tests for load_fire_perimeters — NIFC perimeter GeoDataFrame loader.

Covers:
- Happy path: GeoJSON with geometry column returns GeoDataFrame
- Feature properties are preserved
- Multiple features are loaded
- FileNotFoundError raised for missing file
- ValueError raised when geometry column is absent (mocked)
- Optional crs reprojection is applied
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tanager.visualization import load_fire_perimeters


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_geojson(features: list, suffix: str = ".geojson") -> Path:
    """Write a FeatureCollection to a temp file and return its path."""
    geojson = {"type": "FeatureCollection", "features": features}
    with tempfile.NamedTemporaryFile(
        suffix=suffix, mode="w", delete=False, dir=tempfile.gettempdir()
    ) as f:
        json.dump(geojson, f)
        return Path(f.name)


_SINGLE_FEATURE = [
    {
        "type": "Feature",
        "properties": {"name": "Palisades Fire"},
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
]

_TWO_FEATURES = _SINGLE_FEATURE + [
    {
        "type": "Feature",
        "properties": {"name": "Eaton Fire"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-118.1, 34.1],
                    [-118.0, 34.1],
                    [-118.0, 34.2],
                    [-118.1, 34.2],
                    [-118.1, 34.1],
                ]
            ],
        },
    }
]


# ---------------------------------------------------------------------------
# Happy-path: return value shape
# ---------------------------------------------------------------------------


class TestLoadFirePerimetersReturnsGeoDataFrame:
    """load_fire_perimeters must return a GeoDataFrame with a geometry column."""

    def test_returns_geodataframe(self):
        import geopandas as gpd

        path = _write_geojson(_SINGLE_FEATURE)
        gdf = load_fire_perimeters(path)
        assert isinstance(gdf, gpd.GeoDataFrame)

    def test_geometry_column_present(self):
        path = _write_geojson(_SINGLE_FEATURE)
        gdf = load_fire_perimeters(path)
        assert "geometry" in gdf.columns

    def test_single_feature_length_one(self):
        path = _write_geojson(_SINGLE_FEATURE)
        gdf = load_fire_perimeters(path)
        assert len(gdf) == 1

    def test_feature_property_preserved(self):
        path = _write_geojson(_SINGLE_FEATURE)
        gdf = load_fire_perimeters(path)
        assert gdf.iloc[0]["name"] == "Palisades Fire"

    def test_string_path_accepted(self):
        """load_fire_perimeters must accept a plain str as well as Path."""
        path = _write_geojson(_SINGLE_FEATURE)
        gdf = load_fire_perimeters(str(path))
        assert len(gdf) == 1


class TestLoadFirePerimetersMultipleFeatures:
    """Multiple features in the file are all loaded."""

    def test_two_features_returned(self):
        path = _write_geojson(_TWO_FEATURES)
        gdf = load_fire_perimeters(path)
        assert len(gdf) == 2

    def test_all_names_preserved(self):
        path = _write_geojson(_TWO_FEATURES)
        gdf = load_fire_perimeters(path)
        names = set(gdf["name"].tolist())
        assert names == {"Palisades Fire", "Eaton Fire"}


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestLoadFirePerimetersFileNotFound:
    """FileNotFoundError raised for non-existent paths."""

    def test_missing_geojson_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_fire_perimeters("/nonexistent/path/perimeter.geojson")

    def test_missing_path_object_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_fire_perimeters(Path("/tmp/does_not_exist_tanager_test.geojson"))

    def test_error_message_contains_path(self):
        missing = Path("/tmp/missing_tanager_perimeter.geojson")
        with pytest.raises(FileNotFoundError, match=str(missing)):
            load_fire_perimeters(missing)


class TestLoadFirePerimetersNoGeometry:
    """ValueError raised when the loaded GeoDataFrame lacks a geometry column."""

    def test_no_geometry_column_raises_value_error(self):
        import geopandas as gpd
        import pandas as pd

        # Build a mock GeoDataFrame that has no geometry column.
        mock_gdf = MagicMock(spec=gpd.GeoDataFrame)
        mock_gdf.columns = pd.Index(["name", "area"])

        path = _write_geojson(_SINGLE_FEATURE)
        with patch("geopandas.read_file", return_value=mock_gdf):
            with pytest.raises(ValueError, match="geometry"):
                load_fire_perimeters(path)


# ---------------------------------------------------------------------------
# CRS reprojection
# ---------------------------------------------------------------------------


class TestLoadFirePerimetersCrsReprojection:
    """When crs is supplied, the GeoDataFrame is reprojected."""

    def test_crs_reprojection_applied(self):
        path = _write_geojson(_SINGLE_FEATURE)
        # EPSG:4326 is the native CRS of GeoJSON; reproject to UTM zone 11N.
        gdf = load_fire_perimeters(path, crs="EPSG:32611")
        assert gdf.crs is not None
        assert gdf.crs.to_epsg() == 32611

    def test_no_crs_argument_preserves_native_crs(self):
        path = _write_geojson(_SINGLE_FEATURE)
        gdf = load_fire_perimeters(path)
        # GeoJSON is always WGS-84 (EPSG:4326)
        assert gdf.crs is not None
        assert gdf.crs.to_epsg() == 4326
