"""Scene I/O for Planet Tanager-1 HDF5 hyperspectral data.

Public API
----------
load_scene(filepath, wavelength_range=None) -> xarray.Dataset
    Load a Tanager scene, optionally subsetting by wavelength range.
    Auto-detects swath vs. ortho product layouts.

load_ortho_scene(filepath, wavelength_range=None) -> xarray.Dataset
    Load an ortho-rectified Tanager surface-reflectance product directly
    via h5py. Used by ``load_scene`` when ``hypercoast.read_tanager`` cannot
    handle the file (ortho products lack lat/lon arrays).

get_spatial_info(dataset) -> dict
    Extract CRS, bounds, resolution, and shape from a loaded Dataset.

Notes
-----
Loading a wavelength subset (``wavelength_range``) on swath products reads
the full scene from disk first then slices in memory. HyperCoast's ``bands``
parameter accepts integer indices, not wavelength values, so a two-pass
approach (read metadata → compute indices → slice) would still require
opening the file twice. The ortho path slices contiguous band ranges
directly via h5py and avoids reading the full cube when a narrow range is
requested.
"""

import logging
import re
from os import PathLike
from typing import Optional, Union

import numpy as np
import xarray as xr

log = logging.getLogger(__name__)

# Type alias matching common filepath arguments.
FilePath = Union[str, PathLike]

# HDF5 group/dataset paths used by ortho SR products.
_ORTHO_GRID_GROUP = "HDFEOS/GRIDS/HYP"
_ORTHO_SR_DATASET = "HDFEOS/GRIDS/HYP/Data Fields/surface_reflectance"
_ORTHO_STRUCT_METADATA = "HDFEOS INFORMATION/StructMetadata.0"


def load_scene(
    filepath: FilePath,
    wavelength_range: Optional[tuple[float, float]] = None,
) -> xr.Dataset:
    """Load a Planet Tanager-1 HDF5 scene as an xarray Dataset.

    Auto-detects the HDF5 layout. Swath/basic products are read via
    ``hypercoast.read_tanager``; ortho-rectified surface-reflectance products
    are read via :func:`load_ortho_scene` (HyperCoast cannot read those because
    they lack the ``Latitude``/``Longitude`` datasets it requires).

    When ``wavelength_range`` is supplied the swath path reads the full scene
    into memory and then slices; the ortho path slices contiguous band ranges
    directly on disk (see module docstring).

    Args:
        filepath: Path to a Tanager ``.h5`` file (local or HTTPS URL).
        wavelength_range: Optional ``(min_wl, max_wl)`` tuple in nanometres
            (nm). When supplied only bands whose centre wavelength falls within
            ``[min_wl, max_wl]`` (inclusive) are retained.

    Returns:
        xr.Dataset: Dataset with dims ``(wavelength, y, x)``.  The wavelength
        coordinate is in nm.  Data variables depend on the product type
        (``toa_radiance`` for radiance products, ``surface_reflectance`` plus a
        ``toa_radiance`` alias for SR products).

    Raises:
        ValueError: If the file cannot be read, is not a valid Tanager HDF5
            file, or ``wavelength_range`` does not select any bands.
    """
    import hypercoast  # heavy dep — imported here to keep module fast at import time

    path_str = str(filepath)
    log.debug("Loading Tanager scene from %s", path_str)

    try:
        ds: xr.Dataset = hypercoast.read_tanager(filepath)
    except (OSError, KeyError) as exc:
        raise ValueError(
            f"Cannot read Tanager HDF5 file {path_str!r}: {exc}"
        ) from exc
    except ValueError as exc:
        # HyperCoast raises ValueError on ortho products because they have no
        # Latitude/Longitude datasets. Fall back to the direct ortho reader.
        if _looks_like_missing_latlon_error(exc):
            log.debug(
                "HyperCoast could not locate lat/lon in %s; falling back to "
                "load_ortho_scene (likely an ortho-rectified product)",
                path_str,
            )
            try:
                return load_ortho_scene(filepath, wavelength_range=wavelength_range)
            except ValueError as ortho_exc:
                raise ValueError(
                    f"Cannot read Tanager HDF5 file {path_str!r}: HyperCoast "
                    f"swath read failed ({exc}) and ortho fallback failed "
                    f"({ortho_exc})"
                ) from ortho_exc
        raise ValueError(
            f"Invalid or corrupted Tanager HDF5 file {path_str!r}: {exc}"
        ) from exc

    # HyperCoast guarantees (wavelength, y, x); assert so callers catch drift.
    expected = ("wavelength", "y", "x")
    data_var = ds.attrs.get("data_var", next(iter(ds.data_vars)))
    actual = tuple(ds[data_var].dims)
    if actual != expected:
        raise ValueError(
            f"Unexpected dataset dimensions from HyperCoast: expected "
            f"{expected}, got {actual} in {path_str!r}"
        )

    n_bands = ds.sizes["wavelength"]
    log.debug("Loaded scene: %d bands, shape y=%d x=%d", n_bands, ds.sizes["y"], ds.sizes["x"])

    if wavelength_range is not None:
        min_wl, max_wl = wavelength_range
        wl = ds["wavelength"].values
        mask = (wl >= min_wl) & (wl <= max_wl)
        n_selected = int(mask.sum())
        if n_selected == 0:
            raise ValueError(
                f"wavelength_range ({min_wl}, {max_wl}) nm selects no bands from "
                f"scene with wavelengths [{wl.min():.1f}, {wl.max():.1f}] nm in "
                f"{path_str!r}"
            )
        ds = ds.isel(wavelength=np.where(mask)[0])
        log.debug(
            "Subset to %d bands in range [%.1f, %.1f] nm",
            n_selected,
            min_wl,
            max_wl,
        )

    return ds


def _looks_like_missing_latlon_error(exc: BaseException) -> bool:
    """Detect HyperCoast's 'no lat/lon' error so we can fall back to ortho path.

    HyperCoast's ``read_tanager`` raises a generic ``ValueError`` when it
    cannot locate Latitude/Longitude datasets — exactly the case for ortho
    grid products. Match on stable substrings rather than exact text so we
    survive minor wording changes upstream.
    """
    msg = str(exc).lower()
    return ("latitude" in msg or "lat/lon" in msg) and (
        "could not" in msg or "not found" in msg or "locate" in msg
    )


_STRUCT_METADATA_PATTERNS = {
    "x_dim": re.compile(r"\bXDim\s*=\s*(\d+)"),
    "y_dim": re.compile(r"\bYDim\s*=\s*(\d+)"),
    "upper_left": re.compile(
        r"UpperLeftPointMtrs\s*=\s*\(\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\)"
    ),
    "lower_right": re.compile(
        r"LowerRightMtrs\s*=\s*\(\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\)"
    ),
    "zone_code": re.compile(r"\bZoneCode\s*=\s*(-?\d+)"),
    "grid_origin": re.compile(r"\bGridOrigin\s*=\s*([A-Za-z0-9_]+)"),
    "projection": re.compile(r"\bProjection\s*=\s*([A-Za-z0-9_]+)"),
}


def _parse_struct_metadata(text: str) -> dict:
    """Parse the relevant fields out of HDF-EOS5 ``StructMetadata.0`` text.

    Only the fields needed to construct UTM x/y coords are extracted. The
    metadata blob is INI-like but the official HDF-EOS5 parsers are heavyweight,
    so a small regex pass keeps this module free of extra dependencies.
    """
    result: dict = {}
    for key in ("x_dim", "y_dim", "zone_code"):
        m = _STRUCT_METADATA_PATTERNS[key].search(text)
        if m:
            result[key] = int(m.group(1))

    for key in ("upper_left", "lower_right"):
        m = _STRUCT_METADATA_PATTERNS[key].search(text)
        if m:
            result[key] = (float(m.group(1)), float(m.group(2)))

    for key in ("grid_origin", "projection"):
        m = _STRUCT_METADATA_PATTERNS[key].search(text)
        if m:
            result[key] = m.group(1)

    required = {"x_dim", "y_dim", "upper_left", "lower_right"}
    missing = required - result.keys()
    if missing:
        raise ValueError(
            f"StructMetadata.0 is missing required fields: {sorted(missing)}"
        )
    return result


def load_ortho_scene(
    filepath: FilePath,
    wavelength_range: Optional[tuple[float, float]] = None,
) -> xr.Dataset:
    """Load an ortho-rectified Tanager surface-reflectance product.

    Reads ``HDFEOS/GRIDS/HYP/Data Fields/surface_reflectance`` directly with
    h5py and constructs an xarray Dataset matching the schema expected by the
    rest of the pipeline. Used as the fallback for files where
    ``hypercoast.read_tanager`` raises ``ValueError`` because the lat/lon
    datasets it requires are absent (true for all ortho grid products).

    Args:
        filepath: Path to a Tanager ``ortho_sr`` ``.h5`` file.
        wavelength_range: Optional ``(min_wl, max_wl)`` tuple in nanometres.
            When supplied, only the contiguous band slice covering the range
            is read from disk, keeping memory bounded for narrow subsets.

    Returns:
        xr.Dataset with:

        - dims ``(wavelength, y, x)``
        - data variables ``surface_reflectance`` and ``toa_radiance`` (alias)
        - coords: ``wavelength`` (nm), ``y`` and ``x`` as UTM-metre pixel
          centres, plus ``fwhm`` (nm) and ``good_wavelengths`` (uint8) along
          the wavelength dimension
        - attrs: ``crs`` (``"EPSG:<code>"``), ``epsg``, ``data_var``,
          ``product``, ``source``, plus the ``strip_id`` and ``created_at``
          metadata copied from the HDF5 group

        Fill-value pixels (``-9999``) are converted to NaN.

    Raises:
        ValueError: If the file is missing required ortho-product structure
            (surface_reflectance dataset, StructMetadata.0, wavelengths
            attribute) or ``wavelength_range`` selects zero bands.
    """
    import h5py  # heavy dep — imported lazily

    path_str = str(filepath)
    log.debug("Loading ortho Tanager scene from %s", path_str)

    try:
        h5 = h5py.File(path_str, "r")
    except OSError as exc:
        raise ValueError(
            f"Cannot read Tanager HDF5 file {path_str!r}: {exc}"
        ) from exc

    with h5:
        if _ORTHO_SR_DATASET not in h5:
            raise ValueError(
                f"File {path_str!r} is not a Tanager ortho SR product "
                f"(missing dataset {_ORTHO_SR_DATASET!r})"
            )
        sr = h5[_ORTHO_SR_DATASET]
        sr_attrs = dict(sr.attrs)

        if "wavelengths" not in sr_attrs:
            raise ValueError(
                f"surface_reflectance dataset in {path_str!r} is missing the "
                f"'wavelengths' attribute"
            )

        wavelengths = np.asarray(sr_attrs["wavelengths"], dtype=np.float64)
        fwhm = (
            np.asarray(sr_attrs["fwhm"], dtype=np.float64)
            if "fwhm" in sr_attrs
            else None
        )
        good_wavelengths = (
            np.asarray(sr_attrs["good_wavelengths"], dtype=np.uint8)
            if "good_wavelengths" in sr_attrs
            else None
        )
        fill_value = (
            float(sr_attrs["_FillValue"]) if "_FillValue" in sr_attrs else -9999.0
        )

        n_bands = wavelengths.shape[0]
        if sr.shape[0] != n_bands:
            raise ValueError(
                f"surface_reflectance shape mismatch in {path_str!r}: dataset has "
                f"{sr.shape[0]} bands but 'wavelengths' attribute has {n_bands}"
            )

        # Decide which contiguous band slice to read.
        if wavelength_range is not None:
            min_wl, max_wl = wavelength_range
            mask = (wavelengths >= min_wl) & (wavelengths <= max_wl)
            n_selected = int(mask.sum())
            if n_selected == 0:
                raise ValueError(
                    f"wavelength_range ({min_wl}, {max_wl}) nm selects no bands "
                    f"from scene with wavelengths "
                    f"[{wavelengths.min():.1f}, {wavelengths.max():.1f}] nm in "
                    f"{path_str!r}"
                )
            indices = np.where(mask)[0]
            band_start = int(indices[0])
            band_stop = int(indices[-1]) + 1  # half-open for slicing
            band_slice = slice(band_start, band_stop)
            log.debug(
                "Subset to %d bands in range [%.1f, %.1f] nm (h5 slice [%d:%d])",
                n_selected,
                min_wl,
                max_wl,
                band_start,
                band_stop,
            )
        else:
            band_slice = slice(0, n_bands)

        # Read the cube. h5py returns a numpy array; cast fills to NaN.
        cube = sr[band_slice, :, :].astype(np.float32, copy=False)
        wavelengths_sel = wavelengths[band_slice]
        fwhm_sel = fwhm[band_slice] if fwhm is not None else None
        good_sel = (
            good_wavelengths[band_slice] if good_wavelengths is not None else None
        )

        # Mask fill values to NaN.
        cube = np.where(cube == fill_value, np.nan, cube)

        # Parse grid metadata.
        if _ORTHO_STRUCT_METADATA not in h5:
            raise ValueError(
                f"Ortho file {path_str!r} is missing {_ORTHO_STRUCT_METADATA!r}"
            )
        sm_raw = h5[_ORTHO_STRUCT_METADATA][()]
        sm_text = sm_raw.decode("utf-8") if isinstance(sm_raw, bytes) else str(sm_raw)
        grid = _parse_struct_metadata(sm_text)

        # EPSG: prefer explicit epsg_code on the HYP grid group; fall back to
        # UTM zone code from StructMetadata if present.
        hyp_attrs = (
            dict(h5[_ORTHO_GRID_GROUP].attrs) if _ORTHO_GRID_GROUP in h5 else {}
        )

    # Coords -----------------------------------------------------------------
    x_dim = grid["x_dim"]
    y_dim = grid["y_dim"]
    if cube.shape[1] != y_dim or cube.shape[2] != x_dim:
        raise ValueError(
            f"Cube shape {cube.shape[1:]} does not match StructMetadata grid "
            f"({y_dim}, {x_dim}) in {path_str!r}"
        )
    ulx, uly = grid["upper_left"]
    lrx, lry = grid["lower_right"]
    x_res = (lrx - ulx) / x_dim
    y_res = (uly - lry) / y_dim  # positive number; y descends north→south
    x_coords = ulx + (np.arange(x_dim) + 0.5) * x_res
    y_coords = uly - (np.arange(y_dim) + 0.5) * y_res

    # CRS --------------------------------------------------------------------
    epsg: Optional[int] = None
    if "epsg_code" in hyp_attrs:
        epsg = int(np.asarray(hyp_attrs["epsg_code"]).item())
    elif (
        grid.get("projection") == "HE5_GCTP_UTM"
        and "zone_code" in grid
        and grid["zone_code"] > 0
    ):
        # Northern-hemisphere UTM EPSG = 32600 + zone (Tanager fire scenes are
        # all northern hemisphere; if a southern scene is encountered the
        # explicit epsg_code attribute should be present).
        epsg = 32600 + grid["zone_code"]
    crs = f"EPSG:{epsg}" if epsg is not None else None

    # Build dataset ----------------------------------------------------------
    coords: dict = {
        "wavelength": wavelengths_sel,
        "y": y_coords,
        "x": x_coords,
    }
    if fwhm_sel is not None:
        coords["fwhm"] = (("wavelength",), fwhm_sel)
    if good_sel is not None:
        coords["good_wavelengths"] = (("wavelength",), good_sel)

    attrs: dict = {
        "source": "Planet Tanager HDF5",
        "product": "ortho_sr",
        "data_var": "surface_reflectance",
    }
    if crs is not None:
        attrs["crs"] = crs
    if epsg is not None:
        attrs["epsg"] = epsg
    for k in ("strip_id", "created_at"):
        if k in hyp_attrs:
            v = hyp_attrs[k]
            attrs[k] = v.decode() if isinstance(v, bytes) else v

    sr_da = xr.DataArray(
        cube,
        dims=("wavelength", "y", "x"),
        coords=coords,
        name="surface_reflectance",
    )

    ds = xr.Dataset(
        {
            "surface_reflectance": sr_da,
            # Keep the toa_radiance alias to match the swath-path schema so
            # downstream code that probes either name keeps working.
            "toa_radiance": sr_da,
        },
        coords=coords,
        attrs=attrs,
    )
    return ds


def get_spatial_info(dataset: xr.Dataset) -> dict:
    """Extract spatial metadata from a loaded Tanager Dataset.

    Inspects ``dataset.attrs`` and coordinate arrays to assemble a dict
    describing the coordinate reference system, spatial extent, pixel spacing,
    and raster dimensions.

    CRS lookup order:
    1. ``dataset.attrs["crs"]``
    2. ``dataset.attrs["spatial_ref"]``
    3. ``dataset.attrs["epsg"]`` (wrapped as ``EPSG:<value>``)
    4. A ``"spatial_ref"`` coordinate variable if present
    5. ``None`` if none of the above are found

    Bounds and resolution are derived from the ``y`` and ``x`` dimension
    coordinates when present, or from the ``latitude`` / ``longitude``
    ancillary coordinates as a fallback (bearing in mind that lat/lon may be
    curvilinear, so the fallback bounds are approximate).

    Args:
        dataset: xarray.Dataset returned by :func:`load_scene`.

    Returns:
        dict with the following keys:

        - ``crs`` (str or None): CRS string (WKT, PROJ, or ``"EPSG:XXXX"``),
          or ``None`` if not determinable.
        - ``bounds`` (tuple[float, float, float, float]): Spatial extent as
          ``(x_min, y_min, x_max, y_max)`` in dataset coordinates.
        - ``resolution`` (tuple[float, float] or None): Pixel spacing
          ``(x_res, y_res)`` in dataset coordinate units (absolute values).
          ``None`` if fewer than two pixels exist along an axis.
        - ``shape`` (tuple[int, int]): Raster dimensions as ``(n_rows, n_cols)``
          i.e. ``(y_size, x_size)``.
    """
    # ------------------------------------------------------------------ CRS
    attrs = dataset.attrs
    crs: Optional[str] = None

    if "crs" in attrs:
        crs = str(attrs["crs"])
    elif "spatial_ref" in attrs:
        crs = str(attrs["spatial_ref"])
    elif "epsg" in attrs:
        crs = f"EPSG:{attrs['epsg']}"
    elif "spatial_ref" in dataset.coords:
        # rasterio writes CRS as a scalar coordinate named "spatial_ref"
        crs = str(dataset.coords["spatial_ref"].item())

    # ------------------------------------------------------------- Bounds / resolution
    n_rows = dataset.sizes["y"]
    n_cols = dataset.sizes["x"]
    shape = (n_rows, n_cols)

    if "x" in dataset.coords and "y" in dataset.coords:
        x_vals = dataset.coords["x"].values
        y_vals = dataset.coords["y"].values
        x_min = float(x_vals.min())
        x_max = float(x_vals.max())
        y_min = float(y_vals.min())
        y_max = float(y_vals.max())

        x_res: Optional[float] = (
            float(abs(np.diff(x_vals).mean())) if len(x_vals) >= 2 else None
        )
        y_res: Optional[float] = (
            float(abs(np.diff(y_vals).mean())) if len(y_vals) >= 2 else None
        )
        resolution: Optional[tuple] = (
            (x_res, y_res) if (x_res is not None and y_res is not None) else None
        )
    elif "longitude" in dataset.coords and "latitude" in dataset.coords:
        # Curvilinear fallback — bounds are approximate.
        lon_vals = dataset.coords["longitude"].values
        lat_vals = dataset.coords["latitude"].values
        x_min = float(np.nanmin(lon_vals))
        x_max = float(np.nanmax(lon_vals))
        y_min = float(np.nanmin(lat_vals))
        y_max = float(np.nanmax(lat_vals))
        resolution = None
        log.debug(
            "get_spatial_info: no projected x/y coords; bounds derived from "
            "curvilinear latitude/longitude (approximate)"
        )
    else:
        x_min = x_max = y_min = y_max = float("nan")
        resolution = None
        log.warning(
            "get_spatial_info: no spatial coordinate found; bounds set to NaN"
        )

    bounds = (x_min, y_min, x_max, y_max)

    return {
        "crs": crs,
        "bounds": bounds,
        "resolution": resolution,
        "shape": shape,
    }
