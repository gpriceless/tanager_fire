"""Scene I/O for Planet Tanager-1 HDF5 hyperspectral data.

Public API
----------
load_scene(filepath, wavelength_range=None) -> xarray.Dataset
    Load a Tanager scene, optionally subsetting by wavelength range.

get_spatial_info(dataset) -> dict
    Extract CRS, bounds, resolution, and shape from a loaded Dataset.

Notes
-----
Loading a wavelength subset (``wavelength_range``) currently reads the full
scene from disk first, then slices in memory. HyperCoast's ``bands`` parameter
accepts integer indices, not wavelength values, so a two-pass approach (read
metadata → compute indices → slice) would still require opening the file
twice. The simpler one-pass approach is used here; memory footprint is O(full
scene).
"""

import logging
from os import PathLike
from typing import Optional, Union

import numpy as np
import xarray as xr

log = logging.getLogger(__name__)

# Type alias matching common filepath arguments.
FilePath = Union[str, PathLike]


def load_scene(
    filepath: FilePath,
    wavelength_range: Optional[tuple[float, float]] = None,
) -> xr.Dataset:
    """Load a Planet Tanager-1 HDF5 scene as an xarray Dataset.

    Wraps ``hypercoast.read_tanager`` and guarantees dims ``(wavelength, y, x)``
    with the wavelength coordinate expressed in nanometres.

    When ``wavelength_range`` is supplied the full scene is first read into
    memory and then sliced; see module docstring for rationale.

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
