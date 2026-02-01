# Leaperkim Sherman S (LK3336) BLE Client

Python-based Bluetooth LE client for monitoring Leaperkim Sherman S electric unicycle telemetry data.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Or use the virtual environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Discover device and enumerate services
python discover.py

# Connect and capture telemetry data
python client.py

# Analyze captured data
python decoder.py --log
```

## Device Information

- **Device Name**: LK3336
- **MAC Address**: 88:25:83:F3:5D:30
- **BLE Service**: `0000ffe0-0000-1000-8000-00805f9b34fb`
- **Data Characteristic**: `0000ffe1-0000-1000-8000-00805f9b34fb` (read/write/notify)

## Protocol

The Sherman S uses a custom BLE protocol with two main frame types:

### Telemetry Frame (DC 5A header)
- Bytes 0-1: Header `0xDC 0x5A`
- Bytes 4-5: Voltage (uint16 BE, /100 for volts)
- Other fields: Under investigation

### BMS Frame (0B xx header)
- Contains cell voltages and battery management data

## Files

| File | Description |
|------|-------------|
| `discover.py` | Scan and enumerate device services |
| `client.py` | Connect and capture telemetry data |
| `decoder.py` | Decode BLE packets into readable data |
| `analyze.py` | Analyze captured log files |
| `requirements.txt` | Python dependencies |

## Data Output

Captured data is logged to `battery_data.log` in the format:
```
timestamp | hex_data
```

Example decoded telemetry:
```
Voltage: 91.29V | Battery: 67.0% | Charging: True
```

## Home Assistant Integration

This project is designed for future Home Assistant integration. The client can publish telemetry data via MQTT for use with Home Assistant sensors.

## Requirements

- Python 3.11+
- Linux with BlueZ (Bluetooth stack)
- `bleak` - Cross-platform BLE library

## Troubleshooting

1. **Device not found**: Ensure the EUC is powered on and in range
2. **Permission denied**: May need to run with `sudo` or configure BlueZ permissions
3. **Connection fails**: Try `bluetoothctl` to verify Bluetooth is working

```bash
bluetoothctl
> scan on
# Look for LK3336 or 88:25:83:F3:5D:30
```
