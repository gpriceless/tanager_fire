"""Unit tests for tanager.io.

The ``load_scene`` and ``get_spatial_info`` tests mock
``hypercoast.read_tanager`` so no HDF5 file is required. The ortho-path
tests synthesize a minimal HDF5 file on disk (h5py is already a runtime
dependency) so they exercise the real h5py read path.

Live verification on full Tanager scenes (713×791 etc., 426 bands, EPSG:32611)
is covered by ``tests/test_io_ortho_realdata.py`` when real ortho files are
present in ``data/raw/fire``.

Test naming: <function>_<scenario>_<expected_outcome>
"""

from pathlib import Path
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
# Ortho SR product loading (LGT-303)
# ---------------------------------------------------------------------------
#
# Ortho-rectified products lack the Latitude/Longitude datasets HyperCoast
# requires, so ``load_ortho_scene`` reads ``HDFEOS/GRIDS/HYP`` directly via
# h5py. These tests synthesize a minimal but valid HDF5 file matching the
# real ortho schema so they exercise the actual h5py code path.


def _write_synthetic_ortho_h5(
    path: Path,
    *,
    n_bands: int = 16,
    y_dim: int = 4,
    x_dim: int = 5,
    wl_min: float = 400.0,
    wl_max: float = 2400.0,
    upper_left: tuple[float, float] = (329340.0, 3775800.0),
    lower_right: tuple[float, float] = (353070.0, 3754410.0),
    epsg_code: int = 32611,
    fill_value: float = -9999.0,
    insert_fill_pixels: bool = True,
    write_epsg_attr: bool = True,
    zone_code: int = 11,
) -> np.ndarray:
    """Create a minimal HDF5 file matching Tanager ortho SR layout.

    Returns the wavelength array used so tests can assert exact band values.
    """
    import h5py

    wavelengths = np.linspace(wl_min, wl_max, n_bands).astype(np.float32)
    fwhm = np.full(n_bands, 5.5, dtype=np.float32)
    good = np.ones(n_bands, dtype=np.uint8)

    rng = np.random.default_rng(0)
    cube = rng.random((n_bands, y_dim, x_dim)).astype(np.float32)
    if insert_fill_pixels:
        cube[:, 0, 0] = fill_value  # corner pixel is nodata across all bands

    struct_metadata = (
        "GROUP=GridStructure\n"
        "\tGROUP=GRID_1\n"
        '\t\tGridName="HYP"\n'
        f"\t\tBand={n_bands}\n"
        f"\t\tXDim={x_dim}\n"
        f"\t\tYDim={y_dim}\n"
        f"\t\tUpperLeftPointMtrs=({upper_left[0]:.2f},{upper_left[1]:.2f})\n"
        f"\t\tLowerRightMtrs=({lower_right[0]:.2f},{lower_right[1]:.2f})\n"
        "\t\tProjection=HE5_GCTP_UTM\n"
        f"\t\tZoneCode={zone_code}\n"
        "\t\tSphereCode=12\n"
        "\t\tGridOrigin=HE5_HDFE_GD_UL\n"
        "\tEND_GROUP=GRID_1\n"
        "END_GROUP=GridStructure\n"
    )

    with h5py.File(path, "w") as f:
        sr = f.create_dataset(
            "HDFEOS/GRIDS/HYP/Data Fields/surface_reflectance", data=cube
        )
        sr.attrs["wavelengths"] = wavelengths
        sr.attrs["wavelengths_units"] = np.bytes_("nm")
        sr.attrs["fwhm"] = fwhm
        sr.attrs["fwhm_units"] = np.bytes_("nm")
        sr.attrs["good_wavelengths"] = good
        sr.attrs["_FillValue"] = np.float32(fill_value)
        sr.attrs["Unit"] = np.bytes_("Unitless")

        hyp = f["HDFEOS/GRIDS/HYP"]
        hyp.attrs["strip_id"] = np.bytes_("test_strip_0001")
        hyp.attrs["created_at"] = np.bytes_("2026-04-27T00:00:00Z")
        if write_epsg_attr:
            hyp.attrs["epsg_code"] = np.int64(epsg_code)

        f.create_dataset(
            "HDFEOS INFORMATION/StructMetadata.0", data=np.bytes_(struct_metadata)
        )

    return wavelengths


@pytest.fixture
def synthetic_ortho_h5(tmp_path) -> Path:
    """Write a synthetic ortho SR file and return its path."""
    path = tmp_path / "ortho.h5"
    _write_synthetic_ortho_h5(path)
    return path


class TestLoadOrthoScene:
    def test_returns_dataset_with_expected_dims(self, synthetic_ortho_h5):
        from tanager.io import load_ortho_scene

        ds = load_ortho_scene(synthetic_ortho_h5)

        assert isinstance(ds, xr.Dataset)
        assert tuple(ds["surface_reflectance"].dims) == ("wavelength", "y", "x")
        assert ds.sizes == {"wavelength": 16, "y": 4, "x": 5}

    def test_wavelength_coord_matches_hdf5(self, tmp_path):
        from tanager.io import load_ortho_scene

        path = tmp_path / "ortho.h5"
        wl_expected = _write_synthetic_ortho_h5(path)

        ds = load_ortho_scene(path)
        np.testing.assert_allclose(
            ds.coords["wavelength"].values, wl_expected, rtol=0, atol=1e-6
        )

    def test_xy_coords_are_utm_pixel_centers(self, synthetic_ortho_h5):
        """x/y coords should be UTM pixel centres derived from corner metadata."""
        from tanager.io import load_ortho_scene

        ds = load_ortho_scene(synthetic_ortho_h5)
        # UL=(329340, 3775800), LR=(353070, 3754410), 5x4 pixels
        # x_res = (353070 - 329340) / 5 = 4746
        # y_res = (3775800 - 3754410) / 4 = 5347.5
        x_res = (353070.0 - 329340.0) / 5
        y_res = (3775800.0 - 3754410.0) / 4
        assert ds.coords["x"].values[0] == pytest.approx(329340.0 + 0.5 * x_res)
        assert ds.coords["x"].values[-1] == pytest.approx(353070.0 - 0.5 * x_res)
        # y descends north→south
        assert ds.coords["y"].values[0] == pytest.approx(3775800.0 - 0.5 * y_res)
        assert ds.coords["y"].values[-1] == pytest.approx(3754410.0 + 0.5 * y_res)
        assert ds.coords["y"].values[0] > ds.coords["y"].values[-1]

    def test_crs_from_epsg_attr(self, synthetic_ortho_h5):
        from tanager.io import load_ortho_scene

        ds = load_ortho_scene(synthetic_ortho_h5)
        assert ds.attrs["crs"] == "EPSG:32611"
        assert ds.attrs["epsg"] == 32611

    def test_crs_falls_back_to_utm_zone(self, tmp_path):
        """When epsg_code attr is absent, derive EPSG from UTM zone."""
        from tanager.io import load_ortho_scene

        path = tmp_path / "ortho_no_epsg.h5"
        _write_synthetic_ortho_h5(path, write_epsg_attr=False, zone_code=11)
        ds = load_ortho_scene(path)
        # Northern UTM zone 11 → EPSG:32611
        assert ds.attrs["crs"] == "EPSG:32611"

    def test_fill_values_are_nan(self, synthetic_ortho_h5):
        from tanager.io import load_ortho_scene

        ds = load_ortho_scene(synthetic_ortho_h5)
        # Corner pixel (0,0) was filled with -9999 in the fixture
        assert np.isnan(ds["surface_reflectance"].values[:, 0, 0]).all()
        assert (ds["surface_reflectance"].values == -9999.0).sum() == 0

    def test_includes_toa_radiance_alias(self, synthetic_ortho_h5):
        from tanager.io import load_ortho_scene

        ds = load_ortho_scene(synthetic_ortho_h5)
        assert "toa_radiance" in ds.data_vars
        assert ds.attrs["data_var"] == "surface_reflectance"

    def test_includes_fwhm_and_good_wavelengths(self, synthetic_ortho_h5):
        from tanager.io import load_ortho_scene

        ds = load_ortho_scene(synthetic_ortho_h5)
        assert "fwhm" in ds.coords
        assert "good_wavelengths" in ds.coords
        assert ds.coords["fwhm"].dims == ("wavelength",)
        assert ds.coords["good_wavelengths"].dims == ("wavelength",)

    def test_wavelength_range_subsets_bands(self, tmp_path):
        from tanager.io import load_ortho_scene

        path = tmp_path / "ortho.h5"
        _write_synthetic_ortho_h5(path, n_bands=20, wl_min=400.0, wl_max=2400.0)

        ds = load_ortho_scene(path, wavelength_range=(800.0, 1200.0))
        wl = ds.coords["wavelength"].values
        assert float(wl.min()) >= 800.0
        assert float(wl.max()) <= 1200.0
        assert ds.sizes["wavelength"] < 20

    def test_wavelength_range_no_match_raises(self, synthetic_ortho_h5):
        from tanager.io import load_ortho_scene

        with pytest.raises(ValueError, match="selects no bands"):
            load_ortho_scene(synthetic_ortho_h5, wavelength_range=(3000.0, 4000.0))

    def test_missing_sr_dataset_raises(self, tmp_path):
        """Files without HDFEOS/GRIDS/HYP/Data Fields/surface_reflectance fail clearly."""
        import h5py

        from tanager.io import load_ortho_scene

        path = tmp_path / "not_ortho.h5"
        with h5py.File(path, "w") as f:
            f.create_dataset("foo/bar", data=np.zeros(3))
        with pytest.raises(ValueError, match="not a Tanager ortho SR product"):
            load_ortho_scene(path)

    def test_unreadable_file_raises_value_error(self, tmp_path):
        from tanager.io import load_ortho_scene

        path = tmp_path / "missing.h5"
        # File doesn't exist — h5py raises OSError; we wrap as ValueError.
        with pytest.raises(ValueError, match="Cannot read Tanager HDF5 file"):
            load_ortho_scene(path)

    def test_get_spatial_info_works(self, synthetic_ortho_h5):
        from tanager.io import get_spatial_info, load_ortho_scene

        ds = load_ortho_scene(synthetic_ortho_h5)
        info = get_spatial_info(ds)
        assert info["crs"] == "EPSG:32611"
        assert info["shape"] == (4, 5)
        assert info["resolution"] is not None


class TestLoadSceneOrthoFallback:
    """load_scene should fall back to ortho path when HyperCoast can't handle the file."""

    def test_falls_back_when_hypercoast_misses_latlon(self, tmp_path):
        from tanager.io import load_scene

        path = tmp_path / "ortho.h5"
        _write_synthetic_ortho_h5(path)
        latlon_err = ValueError(
            "Could not locate Latitude/Longitude datasets in the Tanager HDF5 file."
        )
        with patch("hypercoast.read_tanager", side_effect=latlon_err):
            ds = load_scene(path)
        assert ds.attrs["product"] == "ortho_sr"
        assert tuple(ds["surface_reflectance"].dims) == ("wavelength", "y", "x")

    def test_unrelated_value_error_does_not_fall_back(self, tmp_path):
        """A ValueError that is not about lat/lon must not silently fall back."""
        from tanager.io import load_scene

        fake = tmp_path / "scene.h5"
        fake.touch()
        with patch(
            "hypercoast.read_tanager",
            side_effect=ValueError("HDF5 cube is corrupted"),
        ):
            with pytest.raises(ValueError, match="Invalid or corrupted"):
                load_scene(fake)

    def test_subset_propagates_through_fallback(self, tmp_path):
        from tanager.io import load_scene

        path = tmp_path / "ortho.h5"
        _write_synthetic_ortho_h5(path, n_bands=20, wl_min=400.0, wl_max=2400.0)
        latlon_err = ValueError("Could not locate Latitude/Longitude datasets")
        with patch("hypercoast.read_tanager", side_effect=latlon_err):
            ds = load_scene(path, wavelength_range=(800.0, 1200.0))
        wl = ds.coords["wavelength"].values
        assert float(wl.min()) >= 800.0
        assert float(wl.max()) <= 1200.0


# ---------------------------------------------------------------------------
# Integration note
# ---------------------------------------------------------------------------
#
# Live verification requires a downloaded Tanager .h5 file.  To verify:
#
#   from tanager.io import load_scene, get_spatial_info
#   from tanager.config import SENSOR, DATA_DIR
#
#   scene_file = DATA_DIR / "20250123_185507_64_4001_ortho_sr_hdf5.h5"
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
#   assert info["crs"] == "EPSG:32611"
