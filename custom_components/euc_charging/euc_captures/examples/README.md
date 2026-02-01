# EUC Example Captures

This directory contains synthetic example capture files demonstrating the data format for each supported EUC brand.

## Available Examples

| File | Brand | Model | Scenario | Notes |
|------|-------|-------|----------|-------|
| `veteran_sherman_charging.json` | Veteran | Sherman S (24S) | Charging | Shows voltage increasing, positive current |
| `kingsong_s18_idle.json` | KingSong | KS-S18 (20S) | Idle | Wheel at rest, low current draw |
| `gotway_monster_riding.json` | Gotway | Monster Pro (30S) | Riding | Active riding at 20-25 km/h |

## File Format

Each capture file contains:

```json
{
  "device_name": "Device Name",
  "device_address": "MAC Address",
  "brand": "Brand Name",
  "model": "Model Description",
  "capture_timestamp": "ISO 8601 timestamp",
  "scenario": "idle|charging|riding",
  "packets": [
    {
      "timestamp": "Packet timestamp",
      "raw_hex": "Raw hex bytes",
      "decoded": {
        "protocol": "Protocol name",
        "voltage": 100.0,
        "speed": 0.0,
        "...": "other fields"
      }
    }
  ],
  "notes": "Additional information"
}
```

## Using These Examples

These files are intended to:

1. **Demonstrate expected data format** for contributors adding new models
2. **Test protocol decoders** without physical hardware
3. **Validate data analysis tools** (euc_analyzer.py)
4. **Document protocol structure** for each brand

## Creating Your Own Captures

To create real captures from your EUC, use the `euc_logger.py` tool:

```bash
# Scan for devices
python3 euc_logger.py scan

# Capture data
python3 euc_logger.py capture --address XX:XX:XX:XX:XX:XX --duration 60

# View captured data
python3 euc_logger.py list
python3 euc_logger.py view <capture_file>
```

See `DATA_CAPTURE_GUIDE.md` for detailed instructions.

## Notes on Synthetic Data

These examples contain synthetic (generated) data for demonstration purposes:
- Raw hex values are illustrative, not from actual devices
- Checksums may not be correctly calculated
- They show the expected structure and data ranges
- Real captures will have more variation and noise

For analysis and decoder development, always prefer real captures from actual hardware.
