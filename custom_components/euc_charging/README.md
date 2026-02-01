# EUC Charging Monitor

A comprehensive Home Assistant integration for monitoring Electric Unicycle (EUC) charging status and telemetry via Bluetooth Low Energy (BLE).

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/githuba42r/euc_charging.svg)](https://github.com/githuba42r/euc_charging/releases)
[![License](https://img.shields.io/github/license/githuba42r/euc_charging.svg)](LICENSE)

## Features

### Multi-Brand Support

Full support for all major EUC manufacturers:

- ✅ **Veteran/Leaperkim** - Sherman, Abrams, Patton, Lynx, Oryx, etc.
- ✅ **KingSong** - All models with automatic voltage detection
- ✅ **Gotway/Begode** - Monster, MSX, Nikola, RS, MCM, etc.
- ✅ **InMotion** - V1 protocol (V5, V8, V10) and V2 protocol (V11-V14)
- ✅ **Ninebot** - Standard series and Z-series (Z6, Z8, Z10)

### Comprehensive Monitoring

- **Real-time telemetry**: Voltage, speed, distance, current, temperature
- **Battery status**: Percentage with non-linear Li-ion curve calculation
- **Charging detection**: Automatic detection of charging state
- **Charge time estimates**: Predicts time to full charge
- **Multi-configuration support**: 16S through 42S battery packs (67.2V to 176.4V)

### Smart Features

- **Automatic protocol detection** - Identifies your EUC brand automatically
- **ESPHome proxy support** - Extend Bluetooth range with ESPHome devices
- **Bidirectional communication** - Supports active request/response protocols
- **Encrypted protocols** - Full support for Ninebot encryption
- **Charge tracking** - Historical data and statistics

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add repository: `https://github.com/githuba42r/euc_charging`
6. Category: Integration
7. Click "Add"
8. Search for "EUC Charging Monitor"
9. Click "Download"
10. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/euc_charging` directory to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services
4. Click "+ Add Integration"
5. Search for "EUC Charging Monitor"

## Configuration

### Quick Setup

1. Power on your EUC
2. Go to Settings → Devices & Services → Add Integration
3. Search for "EUC Charging Monitor"
4. Your EUC should be auto-discovered
5. Select your device and click "Submit"

### Manual Setup

If auto-discovery doesn't work:

1. Note your EUC's Bluetooth MAC address
2. Add integration manually
3. Click "Manual Entry" when no devices are found
4. Enter the MAC address (format: `AA:BB:CC:DD:EE:FF`)

### ESPHome Bluetooth Proxy

Extend Bluetooth range using an ESP32:

```yaml
bluetooth_proxy:
  active: true
```

See [ESPHome Bluetooth Proxy docs](https://esphome.io/components/bluetooth_proxy.html) for details.

## Entities

The integration creates the following entities:

### Sensors

- `sensor.{device}_battery` - Battery percentage (0-100%)
- `sensor.{device}_voltage` - Current voltage (V)
- `sensor.{device}_current` - Current draw (A)
- `sensor.{device}_speed` - Current speed (km/h)
- `sensor.{device}_temperature` - Controller temperature (°C)
- `sensor.{device}_trip_distance` - Trip distance (km)
- `sensor.{device}_total_distance` - Total odometer (km)
- `sensor.{device}_pwm` - PWM duty cycle (%)
- `sensor.{device}_charge_time_remaining` - Estimated time to full charge
- `sensor.{device}_charge_rate` - Current charge rate (%/hour)

### Binary Sensors

- `binary_sensor.{device}_charging` - Charging status (on/off)
- `binary_sensor.{device}_connected` - BLE connection status

## Automations

### Charge Complete Notification

```yaml
automation:
  - alias: "EUC Charge Complete"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sherman_battery
        above: 99
    condition:
      - condition: state
        entity_id: binary_sensor.sherman_charging
        state: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "Sherman Charged"
          message: "Your EUC is fully charged!"
```

### Charge Started Alert

```yaml
automation:
  - alias: "EUC Charging Started"
    trigger:
      - platform: state
        entity_id: binary_sensor.sherman_charging
        from: "off"
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "Charging Started"
          message: "Sherman is now charging ({{ states('sensor.sherman_battery') }}%)"
```

## Contributing

We welcome contributions from the community! See our guides:

- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Developer guide for adding new models
- **[DATA_CAPTURE_GUIDE.md](DATA_CAPTURE_GUIDE.md)** - How to capture BLE data from your EUC
- **[DATA_ANALYSIS_GUIDE.md](DATA_ANALYSIS_GUIDE.md)** - Protocol reverse engineering guide
- **[PROTOCOL_DIAGRAMS.md](PROTOCOL_DIAGRAMS.md)** - Technical protocol specifications

### Tools for Contributors

We provide command-line tools to help add support for new EUC models:

#### euc_logger.py - Data Capture Tool

```bash
# Scan for nearby EUCs
python3 euc_logger.py scan

# Capture data from your EUC
python3 euc_logger.py capture --address AA:BB:CC:DD:EE:FF --duration 60

# View captured data
python3 euc_logger.py list
python3 euc_logger.py view <capture_file>
```

#### euc_analyzer.py - Protocol Analysis Tool

```bash
# Analyze captured data
python3 euc_analyzer.py analyze <capture_file>

# Compare two captures (e.g., idle vs charging)
python3 euc_analyzer.py compare <capture1> <capture2>

# Find repeating patterns
python3 euc_analyzer.py patterns <capture_file>
```

## Troubleshooting

### Device Not Found

1. **Check Bluetooth is enabled** - Ensure your device has Bluetooth
2. **Check distance** - EUC must be within 10m of Home Assistant
3. **Close other apps** - Disconnect from WheelLog, Darknessbot, etc.
4. **Try ESPHome proxy** - Extend range with an ESP32 proxy
5. **Manual entry** - Use MAC address if auto-discovery fails

### Connection Issues

1. **Check logs** - Settings → System → Logs → Filter by "euc_charging"
2. **Restart Home Assistant** - Sometimes needed after install
3. **Power cycle EUC** - Turn wheel off and back on
4. **Check ESPHome logs** - If using proxy, check ESP logs

### Data Not Updating

1. **Check connection** - `binary_sensor.{device}_connected` should be "on"
2. **Check protocol** - Look for "Protocol detected" message in logs
3. **Verify model** - Some models need specific implementations
4. **Submit issue** - Include logs and capture data

## Technical Details

### Supported Protocols

- **Veteran/Leaperkim**: Passive (DC 5A 5C framing)
- **KingSong**: Passive (AA 55 framing, 0xA9 live data)
- **Gotway/Begode**: Passive (55 AA DC 5A framing)
- **InMotion V1**: Bidirectional (AA AA CAN-style framing)
- **InMotion V2**: Bidirectional (DC 5A framing)
- **Ninebot**: Bidirectional with XOR encryption (55 AA framing)
- **Ninebot Z**: Bidirectional with XOR encryption (5A A5 framing)

### Battery Configurations

Supports 6 cell configurations:
- 16S (67.2V) - Small wheels
- 20S (84.0V) - Mid-size wheels (KS-S18, Ninebot Z6/Z8)
- 24S (100.8V) - Popular high-end (Sherman, V11)
- 30S (126.0V) - High voltage (Monster, Z10, V13)
- 36S (151.2V) - Extreme (some customs)
- 42S (176.4V) - Ultra high (V14, customs)

### Dependencies

- Home Assistant 2023.1.0 or newer
- Bluetooth support (built-in or ESPHome proxy)
- Python 3.11+

## Credits

- **Author**: Phil Gersekowski ([@githuba42r](https://github.com/githuba42r))
- **Protocol Research**: Based on [WheelLog Android app](https://github.com/Wheellog/Wheellog.Android)
- **BLE Library**: Uses [Bleak](https://github.com/hbldh/bleak) for Bluetooth LE communication

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Issues**: Report bugs or request features on [GitHub Issues](https://github.com/githuba42r/euc_charging/issues)
- **Discussions**: Ask questions or share tips in [GitHub Discussions](https://github.com/githuba42r/euc_charging/discussions)
- **Documentation**: See the [custom_components/euc_charging/README.md](custom_components/euc_charging/README.md) for detailed documentation

## Changelog

See [RELEASE_NOTES_v2.0.0.md](RELEASE_NOTES_v2.0.0.md) for the latest release notes.

---

**⚡ Happy riding! Stay safe and keep your EUC charged! ⚡**
