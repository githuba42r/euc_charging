# EUC Charging Monitor - Development Repository

This repository contains the source code for the **EUC Charging Monitor** Home Assistant custom integration.

## Project Structure

```
euc-dump/                          # Development workspace
└── custom_components/
    └── euc_charging/              # 🎯 PROJECT ROOT (distribute this directory)
        ├── __init__.py           # Integration entry point
        ├── manifest.json         # Integration metadata (v2.0.0)
        ├── config_flow.py        # Configuration UI
        ├── coordinator.py        # BLE coordinator
        ├── decoders.py           # Protocol decoders
        ├── sensor.py             # Sensor entities
        ├── binary_sensor.py      # Binary sensors
        ├── charge_tracker.py     # Charge tracking
        ├── const.py              # Constants
        ├── README.md             # Main documentation
        ├── LICENSE               # MIT License
        ├── hacs.json             # HACS configuration
        ├── .github/              # CI/CD and issue templates
        ├── tests/                # Unit tests
        ├── euc_logger.py         # Developer tool: packet capture
        ├── euc_analyzer.py       # Developer tool: packet analysis
        ├── euc_captures/         # Example packet captures
        ├── requirements.txt      # Python dependencies
        └── docs/                 # Additional documentation
```

## Quick Start

### For Users

Install via HACS:

1. Add custom repository: `https://github.com/githuba42r/euc_charging`
2. Search for "EUC Charging" and install
3. Restart Home Assistant
4. Add integration via UI: Settings → Devices & Services → Add Integration

### For Developers

The `custom_components/euc_charging/` directory is the **project root**:

```bash
# Clone repository
git clone https://github.com/githuba42r/euc_charging.git
cd euc_charging/custom_components/euc_charging

# Install dependencies
pip install -r requirements.txt

# Run tests
python tests/test_protocol_basics.py

# Capture EUC packets
./euc_logger.py --device "YOUR_EUC" --duration 60

# Analyze captured data
./euc_analyzer.py euc_captures/capture_TIMESTAMP.json
```

See **[CONTRIBUTING.md](custom_components/euc_charging/CONTRIBUTING.md)** for full development guide.

## What Gets Distributed

When users install via HACS, they receive the **`euc_charging/`** directory which contains:
- Integration code (Python modules)
- Configuration files (manifest.json, hacs.json)
- Documentation (README.md, guides)
- Developer tools (optional, for contributors)
- Tests (optional, for validation)

## Documentation

All documentation is in `custom_components/euc_charging/`:

- **[README.md](custom_components/euc_charging/README.md)** - Main documentation
- **[CONTRIBUTING.md](custom_components/euc_charging/CONTRIBUTING.md)** - Contribution guide
- **[PROTOCOL_DIAGRAMS.md](custom_components/euc_charging/PROTOCOL_DIAGRAMS.md)** - Protocol specifications
- **[DATA_CAPTURE_GUIDE.md](custom_components/euc_charging/DATA_CAPTURE_GUIDE.md)** - How to capture packets
- **[DATA_ANALYSIS_GUIDE.md](custom_components/euc_charging/DATA_ANALYSIS_GUIDE.md)** - How to analyze data

## Supported EUC Brands

- ✅ **Veteran/Leaperkim** (Sherman, Abrams, Patton)
- ✅ **KingSong** (All models)
- ✅ **Gotway/Begode** (All models)
- ⚠️ **InMotion V1** (V10, V10F) - Needs testing
- ⚠️ **InMotion V2** (V11, V12, V13, V14) - Needs testing
- ⚠️ **Ninebot** (S2, E+, P) - Needs testing
- ⚠️ **Ninebot Z** (Z6, Z8, Z10) - Needs testing

## License

MIT License - See [LICENSE](custom_components/euc_charging/LICENSE)

## Support

- **Issues**: https://github.com/githuba42r/euc_charging/issues
- **Discussions**: https://github.com/githuba42r/euc_charging/discussions
- **Author**: Phil Gersekowski (@githuba42r)

## Version

**Current**: v2.0.0 - Multi-brand support with automatic protocol detection
