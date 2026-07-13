# Code Patterns — Tanager Competition

## Data Structures

### Hyperspectral Cube
- **Shape**: xarray.Dataset with dims (wavelength, y, x)
- **Exemplar**: src/tanager/io.py — `load_scene()` produces this structure
- **Convention**: wavelength in nm, spatial coords in native CRS, reflectance as Float32 [0, 1]

### Spectral Index Output
- **Shape**: xarray.DataArray with dims (y, x), no wavelength dim
- **Convention**: normalized indices in [-1, 1], NaN for invalid pixels (never Inf)
- **Exemplar**: src/tanager/spectral.py — `nbr()` (first index function)

### Boolean Mask
- **Shape**: xarray.DataArray with dims (y, x), dtype bool
- **Convention**: True = valid/land, False = masked/water/cloud/nodata
- **Exemplar**: src/tanager/masks.py — `nodata_mask()` (first mask function)

### Endmember Library
- **Shape**: xarray.DataArray with dims (spectrum_id, wavelength)
- **Convention**: spectrum_id is string coordinate, wavelength in nm, attrs: name, category, source
- **Category values**: char, ash, pv, npv, soil, shade
- **Exemplar**: src/tanager/endmembers.py — `load_usgs_library()` output

### Fraction Map
- **Shape**: xarray.Dataset with dims (y, x), variables per endmember class
- **Convention**: fractions sum to 1.0 (tolerance 0.01), NaN for failed pixels, metadata: unmixing_engine
- **Exemplar**: src/tanager/unmixing.py — `run_mesma()` output

## Module Patterns

### Config Module (config.py)
- **Shape**: module-level constants (SENSOR, BAD_BAND_RANGES, FIRE_SCENES, BAND_ALIASES, DATA_DIR)
- **Convention**: SENSOR as SimpleNamespace (dot access), others as list/dict/Path
- **No imports from other tanager modules**

### I/O Adapter (io.py, catalog.py)
- **Shape**: thin wrapper around external library (HyperCoast, pystac)
- **Convention**: translate external API to our conventions, catch external exceptions and re-raise as ValueError/ConnectionError
- **No analysis logic in I/O modules**

### Pure Computation (spectral.py, masks.py, endmembers.py, unmixing.py, severity.py, lfmc.py)
- **Shape**: function takes xarray.Dataset, returns xarray.Dataset or DataArray
- **Convention**: no side effects, no file I/O, no network calls
- **Logging**: use Python `logging` module for informational messages (band counts, etc.)
- **Heavy deps**: import at function level (matplotlib, sklearn), not module level

### Validation Module (validation.py)
- **Shape**: accuracy metrics + reference data loaders
- **Convention**: top of dependency tree — may import from any tanager module, nothing imports from it

## Test Patterns

### Fixtures
- **Convention**: synthetic xarray.Dataset from conftest.py, 426 bands, 50x50 pixels
- **Known signatures**: vegetation (high NIR), char (low flat), soil (monotonic rise)
- **Exemplar**: tests/conftest.py::synthetic_tanager_dataset

### Mocking External I/O
- **Convention**: mock pystac.Catalog.from_file(), hypercoast.read_tanager(), SPy EcostressDatabase — no live network calls in unit tests
- **Exemplar**: tests/test_catalog.py for mock patterns

### ML Model Tests
- **Convention**: generate synthetic X, y with known relationship; verify model R² > 0 and output shapes
- **Exemplar**: tests/test_severity.py, tests/test_lfmc.py

## Dependency Direction (ENFORCED)

```
config  <-- catalog
config  <-- io
config  <-- spectral
config  <-- endmembers
config  <-- unmixing
config  <-- severity
config  <-- lfmc
spectral <-- masks
spectral <-- endmembers
spectral <-- lfmc
spectral <-- severity
endmembers <-- unmixing
unmixing <-- severity
(any)    <-- validation
```

One-way only. No circular imports. validation.py is a leaf — nothing imports from it.
