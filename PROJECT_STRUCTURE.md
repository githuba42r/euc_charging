# Project Structure - HACS Compliant

This document describes the final project structure for the EUC Charging Monitor integration, fully compliant with HACS requirements.

## Directory Structure

```
euc_charging/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md              # Bug report template
│   │   ├── feature_request.md         # Feature request template
│   │   └── new_model.md               # New EUC model support template
│   └── workflows/
│       └── validate.yml               # HACS/Hassfest validation workflow
│
├── custom_components/
│   └── euc_charging/                  # Main integration directory
│       ├── __init__.py                # Integration setup and entry point
│       ├── binary_sensor.py           # Binary sensor entities (charging, connected)
│       ├── charge_tracker.py          # Charge tracking and time estimation
│       ├── config_flow.py             # Configuration UI flow
│       ├── const.py                   # Constants, UUIDs, brand definitions
│       ├── coordinator.py             # Data coordinator with BLE communication
│       ├── decoders.py                # Protocol decoders for all brands (~1600 lines)
│       ├── icon.png                   # Integration icon
│       ├── logo.png                   # Integration logo
│       ├── manifest.json              # Integration metadata (REQUIRED)
│       ├── README.md                  # Detailed integration documentation
│       ├── sensor.py                  # Sensor entities (battery, voltage, etc.)
│       └── translations/
│           └── en.json                # English translations
│
├── euc_captures/
│   └── examples/                      # Example capture files
│       ├── gotway_monster_riding.json # Gotway example
│       ├── kingsong_s18_idle.json    # KingSong example
│       ├── veteran_sherman_charging.json # Veteran example
│       └── README.md                  # Examples documentation
│
├── tests/
│   ├── test_decoders.py              # Unit tests for decoders
│   └── test_protocol_basics.py       # Basic protocol tests (standalone)
│
├── CONTRIBUTING.md                    # Developer contribution guide (~450 lines)
├── DATA_ANALYSIS_GUIDE.md            # Protocol analysis guide (~800 lines)
├── DATA_CAPTURE_GUIDE.md             # Data capture instructions (~600 lines)
├── euc_analyzer.py                   # Protocol analysis tool (~440 lines)
├── euc_logger.py                     # BLE data capture tool (~550 lines)
├── hacs.json                         # HACS configuration (REQUIRED)
├── IMPLEMENTATION_STATUS.md          # Implementation status and roadmap
├── LICENSE                           # MIT License (REQUIRED)
├── PROTOCOL_DIAGRAMS.md              # Protocol specifications with diagrams
├── README.md                         # Main project README (REQUIRED)
├── RELEASE_NOTES_v2.0.0.md          # Release notes for v2.0.0
└── requirements.txt                  # Python dependencies (for tools)
```

## HACS Requirements Checklist

### ✅ Required Files

- [x] `README.md` in repository root
- [x] `custom_components/{domain}/manifest.json`
- [x] `custom_components/{domain}/__init__.py`
- [x] `hacs.json` configuration file
- [x] `LICENSE` file (MIT)

### ✅ manifest.json Requirements

```json
{
  "domain": "euc_charging",
  "name": "EUC Charging Monitor",
  "codeowners": ["@githuba42r"],
  "config_flow": true,
  "dependencies": ["bluetooth"],
  "documentation": "https://github.com/githuba42r/euc_charging",
  "iot_class": "local_push",
  "issue_tracker": "https://github.com/githuba42r/euc_charging/issues",
  "version": "2.0.0"
}
```

Required fields present:
- [x] `domain`
- [x] `name`
- [x] `documentation` (valid URL)
- [x] `issue_tracker` (valid URL)
- [x] `version` (semver format)

### ✅ hacs.json Configuration

```json
{
  "name": "EUC Charging Monitor",
  "content_in_root": false,
  "render_readme": true,
  "homeassistant": "2023.1.0"
}
```

Configuration:
- [x] `content_in_root: false` (integration in custom_components/)
- [x] `render_readme: true` (display README on HACS)
- [x] `homeassistant` minimum version specified

### ✅ Repository Structure

- [x] Integration code in `custom_components/{domain}/`
- [x] Not in repository root
- [x] All Python files have proper imports
- [x] Config flow implemented
- [x] Translations directory present

### ✅ Documentation

- [x] Comprehensive README.md in root
- [x] Installation instructions
- [x] Configuration guide
- [x] Troubleshooting section
- [x] Contributing guidelines
- [x] License information

### ✅ GitHub Features

- [x] Issue templates (bug, feature, new model)
- [x] GitHub Actions workflow (HACS validation)
- [x] Proper repository metadata

### ✅ Code Quality

- [x] Type hints where appropriate
- [x] Logging implemented
- [x] Error handling
- [x] Config flow validation
- [x] Unit tests

## Integration Categories

**Category**: Integration (not plugin, theme, or other)

**HACS Category Validation**:
- ✅ Has config_flow
- ✅ Has translations
- ✅ Uses DataUpdateCoordinator
- ✅ Follows Home Assistant architecture

## Installation Methods

### Via HACS (Primary Method)

1. User adds custom repository: `https://github.com/githuba42r/euc_charging`
2. HACS validates repository structure
3. User installs from HACS UI
4. Integration appears in Settings → Integrations

### Manual Installation (Alternative)

1. User copies `custom_components/euc_charging` to their HA instance
2. Restarts Home Assistant
3. Adds via Settings → Integrations

## File Purposes

### Core Integration Files

| File | Purpose | Required |
|------|---------|----------|
| `__init__.py` | Entry point, platform setup | ✅ Yes |
| `manifest.json` | Integration metadata | ✅ Yes |
| `config_flow.py` | Configuration UI | ✅ Yes (config_flow: true) |
| `coordinator.py` | Data fetching and BLE | ✅ Yes |
| `const.py` | Constants and configuration | ⚠️ Recommended |
| `sensor.py` | Sensor entities | ⚠️ If has sensors |
| `binary_sensor.py` | Binary sensor entities | ⚠️ If has binary sensors |
| `translations/en.json` | UI text | ⚠️ Recommended |

### Protocol Implementation

| File | Purpose | Lines |
|------|---------|-------|
| `decoders.py` | All protocol decoders | ~1600 |
| `charge_tracker.py` | Charge tracking logic | ~300 |

### Developer Tools

| File | Purpose | Lines |
|------|---------|-------|
| `euc_logger.py` | BLE data capture | ~550 |
| `euc_analyzer.py` | Protocol analysis | ~440 |

### Documentation

| File | Purpose | Lines |
|------|---------|-------|
| `README.md` | Main documentation | ~350 |
| `CONTRIBUTING.md` | Developer guide | ~450 |
| `DATA_CAPTURE_GUIDE.md` | Capture instructions | ~600 |
| `DATA_ANALYSIS_GUIDE.md` | Analysis guide | ~800 |
| `PROTOCOL_DIAGRAMS.md` | Protocol specs | ~500 |

## Validation

### HACS Validation

Run HACS validation locally:

```bash
# Using HACS action locally
docker run --rm -v $(pwd):/github/workspace \
  ghcr.io/hacs/action:main
```

### Hassfest Validation

Run Home Assistant's hassfest validator:

```bash
# Using Home Assistant's hassfest
docker run --rm -v $(pwd)/custom_components/euc_charging:/config \
  homeassistant/home-assistant:latest \
  python -m homeassistant.scripts.hassfest
```

### Manual Validation Checklist

- [x] All imports use absolute paths
- [x] No circular dependencies
- [x] Config flow follows HA patterns
- [x] Entities use unique_id
- [x] Device registry implemented
- [x] Proper async/await usage
- [x] Error handling in place
- [x] Logging implemented

## Common HACS Issues and Solutions

### Issue: "No releases found"
**Solution**: Create a GitHub release with tag (e.g., v2.0.0)

### Issue: "Invalid manifest.json"
**Solution**: Validate JSON syntax and required fields

### Issue: "Integration not in custom_components"
**Solution**: Ensure `content_in_root: false` in hacs.json

### Issue: "Missing documentation"
**Solution**: Ensure `documentation` URL is valid in manifest.json

### Issue: "Config flow not found"
**Solution**: Ensure `config_flow: true` in manifest.json and config_flow.py exists

## Release Process

1. **Update version** in `manifest.json`
2. **Create release notes** (RELEASE_NOTES_vX.X.X.md)
3. **Commit changes** to main branch
4. **Create GitHub tag**: `git tag v2.0.0`
5. **Push tag**: `git push origin v2.0.0`
6. **Create GitHub release** with release notes
7. **HACS will auto-detect** the new release

## Verification Steps

Before submitting to HACS:

1. ✅ Run validation workflow
2. ✅ Test installation manually
3. ✅ Test config flow
4. ✅ Verify all entities appear
5. ✅ Check logs for errors
6. ✅ Test with actual EUC hardware
7. ✅ Verify documentation links work
8. ✅ Ensure GitHub Actions pass

## Status

**Current State**: ✅ **FULLY HACS COMPLIANT**

The project structure meets all HACS requirements and is ready for:
- Addition to HACS as a custom repository
- Submission to HACS default repository (optional)
- Distribution via GitHub releases

**Repository**: https://github.com/githuba42r/euc_charging
**Author**: Phil Gersekowski (@githuba42r)
**License**: MIT
**Version**: 2.0.0

---

*Last Updated: 2024-02-01*
