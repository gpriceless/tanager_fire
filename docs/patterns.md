# Code Patterns — Tanager Competition

## Data Structures

### Hyperspectral Cube
- **Shape**: xarray.Dataset with dims (wavelength, y, x)
- **Exemplar**: (to be established by io.py — first module to produce this structure)
- **Convention**: wavelength in nm, spatial coords in native CRS, reflectance as Float32 [0, 1]

### Spectral Index Output
- **Shape**: xarray.DataArray with dims (y, x), no wavelength dim
- **Convention**: normalized indices in [-1, 1], NaN for invalid pixels (never Inf)
- **Exemplar**: spectral.nbr() (first index function)

### Boolean Mask
- **Shape**: xarray.DataArray with dims (y, x), dtype bool
- **Convention**: True = valid/land, False = masked/water/cloud/nodata
- **Exemplar**: masks.nodata_mask() (first mask function)

## Module Patterns

### Config Module (config.py)
- **Shape**: module-level constants (SENSOR, BAD_BAND_RANGES, FIRE_SCENES, BAND_ALIASES, DATA_DIR)
- **Convention**: SENSOR as SimpleNamespace (dot access), others as list/dict/Path
- **No imports from other tanager modules**

### I/O Adapter (io.py, catalog.py)
- **Shape**: thin wrapper around external library (HyperCoast, pystac)
- **Convention**: translate external API to our conventions, catch external exceptions and re-raise as ValueError/ConnectionError
- **No analysis logic in I/O modules**

### Pure Computation (spectral.py, masks.py)
- **Shape**: function takes xarray.Dataset, returns xarray.Dataset or DataArray
- **Convention**: no side effects, no file I/O, no network calls
- **Logging**: use Python `logging` module for informational messages (band counts, etc.)

## Test Patterns

### Fixtures
- **Convention**: synthetic xarray.Dataset from conftest.py, 426 bands, 50x50 pixels
- **Known signatures**: vegetation (high NIR), char (low flat), soil (monotonic rise)
- **Exemplar**: tests/conftest.py::synthetic_tanager_dataset

### Catalog Tests
- **Convention**: mock pystac.Catalog.from_file() — no live network calls in unit tests
- **Live verification**: separate manual verify steps (documented in tasks.md)

## Dependency Direction (ENFORCED)

```
config  <-- catalog
config  <-- io
config  <-- spectral
spectral <-- masks
```

One-way only. No circular imports.
