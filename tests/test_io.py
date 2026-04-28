"""Unit tests for tanager.io.

All tests mock ``hypercoast.read_tanager`` so no HDF5 file is required.
Live verification (426 bands, 380–2500 nm wavelength range) is covered by
the integration comment at the bottom of this file.

Test naming: <function>_<scenario>_<expected_outcome>
"""

from unittest.mock import patch

import numpy as np
import pytest
import xarray as xr

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dataset(
    n_bands: int = 426,
    n_rows: int = 4,
    n_cols: int = 5,
    wl_min: float = 380.0,
    wl_max: float = 2500.0,
    attrs: dict | None = None,
    has_xy_coords: bool = False,
) -> xr.Dataset:
    """Build a minimal mock Tanager Dataset that matches HyperCoast output."""
    wavelengths = np.linspace(wl_min, wl_max, n_bands)
    data = np.zeros((n_bands, n_rows, n_cols), dtype=float)
    lat = np.zeros((n_rows, n_cols))
    lon = np.zeros((n_rows, n_cols))

    coords: dict = {
        "wavelength": wavelengths,
        "latitude": (("y", "x"), lat),
        "longitude": (("y", "x"), lon),
    }

    if has_xy_coords:
        coords["x"] = np.linspace(10.0, 14.0, n_cols)
        coords["y"] = np.linspace(50.0, 46.0, n_rows)  # descending (north → south)

    da = xr.DataArray(data, dims=("wavelength", "y", "x"), coords=coords, name="toa_radiance")
    ds = xr.Dataset(
        {"toa_radiance": da},
        coords=coords,
        attrs=attrs or {"source": "Planet Tanager HDF5", "product": "basic_radiance", "data_var": "toa_radiance"},
    )
    return ds


# ---------------------------------------------------------------------------
# load_scene — basic loading
# ---------------------------------------------------------------------------

class TestLoadSceneBasic:
    def test_returns_xarray_dataset(self, tmp_path):
        """load_scene wrapping read_tanager returns an xarray.Dataset."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        mock_ds = _make_dataset()
        with patch("hypercoast.read_tanager", return_value=mock_ds):
            from tanager.io import load_scene
            result = load_scene(fake_h5)
        assert isinstance(result, xr.Dataset)

    def test_dims_are_wavelength_y_x(self, tmp_path):
        """Returned dataset has exactly (wavelength, y, x) dimensions."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        mock_ds = _make_dataset()
        with patch("hypercoast.read_tanager", return_value=mock_ds):
            from tanager.io import load_scene
            result = load_scene(fake_h5)
        assert tuple(result["toa_radiance"].dims) == ("wavelength", "y", "x")

    def test_wavelength_coordinate_present(self, tmp_path):
        """Wavelength coordinate is present on the returned dataset."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        mock_ds = _make_dataset(n_bands=426, wl_min=380.0, wl_max=2500.0)
        with patch("hypercoast.read_tanager", return_value=mock_ds):
            from tanager.io import load_scene
            result = load_scene(fake_h5)
        assert "wavelength" in result.coords
        wl = result.coords["wavelength"].values
        assert len(wl) == 426
        assert float(wl.min()) == pytest.approx(380.0)
        assert float(wl.max()) == pytest.approx(2500.0)

    def test_passes_filepath_to_hypercoast(self, tmp_path):
        """load_scene forwards the filepath argument to hypercoast.read_tanager."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        mock_ds = _make_dataset()
        with patch("hypercoast.read_tanager", return_value=mock_ds) as mock_read:
            from tanager.io import load_scene
            load_scene(fake_h5)
        mock_read.assert_called_once_with(fake_h5)

    def test_accepts_string_path(self, tmp_path):
        """load_scene works when filepath is a str, not just a Path."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        mock_ds = _make_dataset()
        with patch("hypercoast.read_tanager", return_value=mock_ds):
            from tanager.io import load_scene
            result = load_scene(str(fake_h5))
        assert isinstance(result, xr.Dataset)


# ---------------------------------------------------------------------------
# load_scene — wavelength_range subsetting (Task 2)
# ---------------------------------------------------------------------------

class TestLoadSceneWavelengthRange:
    def test_subset_selects_correct_bands(self, tmp_path):
        """wavelength_range=(900, 1400) retains only bands in that range."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        mock_ds = _make_dataset(n_bands=426, wl_min=380.0, wl_max=2500.0)
        with patch("hypercoast.read_tanager", return_value=mock_ds):
            from tanager.io import load_scene
            result = load_scene(fake_h5, wavelength_range=(900.0, 1400.0))
        wl = result.coords["wavelength"].values
        assert float(wl.min()) >= 900.0
        assert float(wl.max()) <= 1400.0
        assert len(wl) > 0

    def test_subset_dims_still_wavelength_y_x(self, tmp_path):
        """After subsetting, dims remain (wavelength, y, x)."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        mock_ds = _make_dataset(n_bands=426)
        with patch("hypercoast.read_tanager", return_value=mock_ds):
            from tanager.io import load_scene
            result = load_scene(fake_h5, wavelength_range=(900.0, 1400.0))
        assert tuple(result["toa_radiance"].dims) == ("wavelength", "y", "x")

    def test_subset_fewer_bands_than_full_scene(self, tmp_path):
        """A valid wavelength_range returns fewer bands than the full 426."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        mock_ds = _make_dataset(n_bands=426)
        with patch("hypercoast.read_tanager", return_value=mock_ds):
            from tanager.io import load_scene
            full = load_scene(fake_h5)
            result = load_scene(fake_h5, wavelength_range=(900.0, 1400.0))
        assert result.sizes["wavelength"] < full.sizes["wavelength"]

    def test_no_range_returns_all_bands(self, tmp_path):
        """Without wavelength_range all 426 bands are returned."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        mock_ds = _make_dataset(n_bands=426)
        with patch("hypercoast.read_tanager", return_value=mock_ds):
            from tanager.io import load_scene
            result = load_scene(fake_h5)
        assert result.sizes["wavelength"] == 426

    def test_out_of_range_raises_value_error(self, tmp_path):
        """A wavelength_range outside the scene range raises ValueError."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        mock_ds = _make_dataset(n_bands=426, wl_min=380.0, wl_max=2500.0)
        with patch("hypercoast.read_tanager", return_value=mock_ds):
            from tanager.io import load_scene
            with pytest.raises(ValueError, match="selects no bands"):
                load_scene(fake_h5, wavelength_range=(3000.0, 4000.0))

    def test_inclusive_boundary_includes_edge_bands(self, tmp_path):
        """Boundary wavelengths are included (inclusive range)."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        mock_ds = _make_dataset(n_bands=10, wl_min=100.0, wl_max=1000.0)
        with patch("hypercoast.read_tanager", return_value=mock_ds):
            from tanager.io import load_scene
            wl_vals = np.linspace(100.0, 1000.0, 10)
            min_wl = float(wl_vals[0])
            max_wl = float(wl_vals[-1])
            result = load_scene(fake_h5, wavelength_range=(min_wl, max_wl))
        assert result.sizes["wavelength"] == 10


# ---------------------------------------------------------------------------
# load_scene — error handling (Task 4)
# ---------------------------------------------------------------------------

class TestLoadSceneErrors:
    def test_oserror_wrapped_as_value_error(self, tmp_path):
        """OSError (e.g., HDF5 read failure) is re-raised as ValueError."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        with patch("hypercoast.read_tanager", side_effect=OSError("permission denied")):
            from tanager.io import load_scene
            with pytest.raises(ValueError, match="Cannot read Tanager HDF5 file"):
                load_scene(fake_h5)

    def test_value_error_from_hypercoast_wrapped(self, tmp_path):
        """ValueError from HyperCoast is re-raised with filepath context."""
        fake_h5 = tmp_path / "corrupted.h5"
        fake_h5.touch()
        with patch("hypercoast.read_tanager", side_effect=ValueError("no cube found")):
            from tanager.io import load_scene
            with pytest.raises(ValueError, match="Invalid or corrupted Tanager HDF5"):
                load_scene(fake_h5)

    def test_key_error_from_hypercoast_wrapped(self, tmp_path):
        """KeyError (missing HDF5 dataset path) is re-raised as ValueError."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        with patch("hypercoast.read_tanager", side_effect=KeyError("missing_key")):
            from tanager.io import load_scene
            with pytest.raises(ValueError, match="Cannot read Tanager HDF5 file"):
                load_scene(fake_h5)

    def test_error_message_includes_filepath(self, tmp_path):
        """ValueError message always includes the filepath for debuggability."""
        fake_h5 = tmp_path / "bad_scene.h5"
        fake_h5.touch()
        with patch("hypercoast.read_tanager", side_effect=OSError("bad file")):
            from tanager.io import load_scene
            with pytest.raises(ValueError, match=str(fake_h5)):
                load_scene(fake_h5)

    def test_unexpected_dims_raise_value_error(self, tmp_path):
        """If HyperCoast returns unexpected dims, ValueError is raised."""
        fake_h5 = tmp_path / "scene.h5"
        fake_h5.touch()
        # Simulate a dataset with wrong dim order
        data = np.zeros((4, 5, 426))
        bad_ds = xr.Dataset(
            {"toa_radiance": xr.DataArray(data, dims=("y", "x", "wavelength"))},
            attrs={"data_var": "toa_radiance"},
        )
        with patch("hypercoast.read_tanager", return_value=bad_ds):
            from tanager.io import load_scene
            with pytest.raises(ValueError, match="Unexpected dataset dimensions"):
                load_scene(fake_h5)


# ---------------------------------------------------------------------------
# get_spatial_info (Task 3)
# ---------------------------------------------------------------------------

class TestGetSpatialInfo:
    def test_returns_dict_with_required_keys(self):
        """get_spatial_info returns dict with crs, bounds, resolution, shape."""
        ds = _make_dataset(has_xy_coords=True)
        from tanager.io import get_spatial_info
        result = get_spatial_info(ds)
        assert set(result.keys()) == {"crs", "bounds", "resolution", "shape"}

    def test_shape_matches_dataset_dims(self):
        """shape is (n_rows, n_cols) matching y and x sizes."""
        ds = _make_dataset(n_rows=10, n_cols=20, has_xy_coords=True)
        from tanager.io import get_spatial_info
        result = get_spatial_info(ds)
        assert result["shape"] == (10, 20)

    def test_crs_from_attrs_crs_key(self):
        """CRS is read from ds.attrs['crs'] when present."""
        ds = _make_dataset(has_xy_coords=True, attrs={
            "crs": "EPSG:32611",
            "source": "Planet Tanager HDF5",
            "product": "basic_radiance",
            "data_var": "toa_radiance",
        })
        from tanager.io import get_spatial_info
        result = get_spatial_info(ds)
        assert result["crs"] == "EPSG:32611"

    def test_crs_from_attrs_epsg_key(self):
        """CRS is assembled as 'EPSG:<value>' from ds.attrs['epsg']."""
        ds = _make_dataset(has_xy_coords=True, attrs={
            "epsg": 32611,
            "source": "Planet Tanager HDF5",
            "product": "basic_radiance",
            "data_var": "toa_radiance",
        })
        from tanager.io import get_spatial_info
        result = get_spatial_info(ds)
        assert result["crs"] == "EPSG:32611"

    def test_crs_none_when_missing(self):
        """CRS is None when no CRS metadata is present."""
        ds = _make_dataset(has_xy_coords=True, attrs={
            "source": "Planet Tanager HDF5",
            "product": "basic_radiance",
            "data_var": "toa_radiance",
        })
        from tanager.io import get_spatial_info
        result = get_spatial_info(ds)
        assert result["crs"] is None

    def test_bounds_from_xy_coords(self):
        """Bounds derived from x/y dimension coordinates when available."""
        ds = _make_dataset(n_rows=4, n_cols=5, has_xy_coords=True)
        x_vals = ds.coords["x"].values
        y_vals = ds.coords["y"].values
        from tanager.io import get_spatial_info
        result = get_spatial_info(ds)
        x_min, y_min, x_max, y_max = result["bounds"]
        assert x_min == pytest.approx(float(x_vals.min()))
        assert x_max == pytest.approx(float(x_vals.max()))
        assert y_min == pytest.approx(float(y_vals.min()))
        assert y_max == pytest.approx(float(y_vals.max()))

    def test_bounds_from_lat_lon_fallback(self):
        """When no x/y coords, bounds fall back to latitude/longitude."""
        ds = _make_dataset(n_rows=4, n_cols=5, has_xy_coords=False)
        # Set some non-zero lat/lon for the test to be meaningful
        ds["latitude"].values[:] = np.linspace(34.0, 34.3, 4)[:, None]
        ds["longitude"].values[:] = np.linspace(-118.5, -118.0, 5)[None, :]
        from tanager.io import get_spatial_info
        result = get_spatial_info(ds)
        x_min, y_min, x_max, y_max = result["bounds"]
        assert x_min == pytest.approx(-118.5)
        assert x_max == pytest.approx(-118.0)
        assert y_min == pytest.approx(34.0)
        assert y_max == pytest.approx(34.3)

    def test_resolution_from_xy_coords(self):
        """Resolution is computed as mean pixel spacing along x and y."""
        ds = _make_dataset(n_rows=4, n_cols=5, has_xy_coords=True)
        from tanager.io import get_spatial_info
        result = get_spatial_info(ds)
        assert result["resolution"] is not None
        x_res, y_res = result["resolution"]
        assert x_res > 0
        assert y_res > 0

    def test_resolution_none_when_single_pixel(self):
        """Resolution is None when a dimension has only one pixel."""
        ds = _make_dataset(n_rows=1, n_cols=1, has_xy_coords=True)
        from tanager.io import get_spatial_info
        result = get_spatial_info(ds)
        assert result["resolution"] is None

    def test_resolution_none_when_no_xy_coords(self):
        """Resolution is None when falling back to lat/lon coordinates."""
        ds = _make_dataset(n_rows=4, n_cols=5, has_xy_coords=False)
        from tanager.io import get_spatial_info
        result = get_spatial_info(ds)
        assert result["resolution"] is None

    def test_crs_from_spatial_ref_coord(self):
        """CRS is read from the 'spatial_ref' coordinate variable."""
        ds = _make_dataset(has_xy_coords=True, attrs={
            "source": "Planet Tanager HDF5",
            "product": "basic_radiance",
            "data_var": "toa_radiance",
        })
        ds = ds.assign_coords({"spatial_ref": xr.DataArray("EPSG:4326")})
        from tanager.io import get_spatial_info
        result = get_spatial_info(ds)
        assert result["crs"] == "EPSG:4326"


# ---------------------------------------------------------------------------
# Integration note (Task 5)
# ---------------------------------------------------------------------------
#
# Live verification requires a downloaded Tanager .h5 file.  To verify:
#
#   from tanager.io import load_scene, get_spatial_info
#   from tanager.config import SENSOR, DATA_DIR
#
#   scene_file = DATA_DIR / "20250123_185507_64_4001.h5"
#   ds = load_scene(scene_file)
#
#   assert ds.sizes["wavelength"] == SENSOR.n_bands          # 426
#   assert ds.sizes["y"] > 0
#   assert ds.sizes["x"] > 0
#   wl = ds.coords["wavelength"].values
#   assert wl.min() >= SENSOR.wavelength_min_nm              # 380
#   assert wl.max() <= SENSOR.wavelength_max_nm              # 2500
#
#   info = get_spatial_info(ds)
#   assert info["shape"] == (ds.sizes["y"], ds.sizes["x"])
