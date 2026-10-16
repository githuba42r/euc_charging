# EUC Charging Monitor

A comprehensive Home Assistant integration for monitoring Electric Unicycle (EUC) charging status and telemetry via Bluetooth Low Energy (BLE).

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/githuba42r/euc_charging.svg)](https://github.com/githuba42r/euc_charging/releases)
[![License](https://img.shields.io/github/license/githuba42r/euc_charging.svg)](LICENSE)

## Features

### Multi-Brand Support

| Brand | Status | Charging detection |
|---|---|---|
| **Veteran/Leaperkim** - Sherman, Abrams, Patton, Lynx, Oryx, etc. | ✅ Supported — verified on real hardware (Sherman S) | Wheel flag, plus charging current |
| **KingSong** | ✅ Implemented — not yet verified on a real wheel | Experimental (current / voltage inference) |
| **Gotway/Begode** | ✅ Implemented — not yet verified on a real wheel | Experimental (voltage inference) |
| **InMotion V1** - V5, V8, V10 | ✅ Implemented — not yet verified on a real wheel | Experimental (current / voltage inference) |
| **InMotion V2** - V9, V11-V14, P6, E20 | ✅ Implemented — not yet verified on a real wheel | Wheel flag |
| **Ninebot** - One series (S2, A1, C, E+, P) | ✅ Implemented — not yet verified on a real wheel | Wheel flag |
| **Ninebot Z** - Z6, Z8, Z10 | ✅ Implemented — not yet verified on a real wheel | Wheel flag |

All parsers follow the wheels' Bluetooth protocols as implemented by WheelLog and
the EUC World app (see [Credits](#credits)). Only Leaperkim/Veteran has been
tested against a real wheel so far — **captures from other wheels are very
welcome**, see [Contributing](#contributing).

- **Experimental charging detection:** wheels that don't report a charging flag
  are inferred from sustained negative battery current while stationary and/or a
  steady voltage rise at standstill (ignoring post-ride voltage recovery). The
  Charging sensor's `charging_method` attribute shows which method was used.
- **Gotway/Begode:** the pack voltage depends on the model. It is detected from
  the wheel's name/firmware where possible; otherwise Home Assistant raises a
  Repairs notice to pick your model (also under the integration's **Configure**).
- **InMotion V1:** wheels with a custom password are supported — you're asked for
  the password during setup (default `000000`), and a Repairs notice appears if
  the wheel doesn't respond.
- **Not yet supported:** smart-BMS (per-cell) data.

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

This integration is installed through [HACS](https://hacs.xyz) as a custom repository. If you don't have HACS yet, follow the [HACS installation guide](https://hacs.xyz/docs/use/download/download/) first.

#### One-click install

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=githuba42r&repository=euc_charging&category=integration)

1. Click the button above and confirm your Home Assistant URL if asked
2. HACS opens the **EUC Charging Monitor** repository — click **Download** (bottom right) and confirm
3. Restart Home Assistant (**Settings → System → ⋮ → Restart Home Assistant**)
4. Add the integration:

   [![Open your Home Assistant instance and start setting up the EUC Charging Monitor integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=euc_charging)

#### Add the repository manually in HACS

1. Open **HACS** from the Home Assistant sidebar
2. Click **⋮** (top right) → **Custom repositories**
3. Repository: `https://github.com/githuba42r/euc_charging` — Type: **Integration** — click **Add**
4. Close the dialog, search HACS for **EUC Charging Monitor**, open it and click **Download**
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → + Add Integration** and search for **EUC Charging Monitor**

#### Updating

HACS checks this repository for new releases and shows an update under **Settings → Updates** when one is available. Install it, then restart Home Assistant.

> Most wheels and TPMS sensors are discovered automatically once the integration is installed — look for a **Discovered** card under **Settings → Devices & Services**.

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

## Smart Charging Automations & Blueprints

Pair the integration with a Zigbee smart plug to charge your wheel automatically:
**nightly top-up to 95%**, **ride-day charge to 100%** with a readiness check,
a **monthly extended balance charge**, and safety cut-offs — plus an optional
Zigbee button by the charger.

- 📖 **Guide:** [docs/charging-automations.md](docs/charging-automations.md) — strategies, hardware (plug and button with purchase links), helpers and tips
- 🧩 **Blueprints:** [blueprints/automation/euc_charging/](blueprints/automation/euc_charging/) — import with one click from the guide
- 📦 **Complete package:** [examples/packages/euc_charging.yaml](examples/packages/euc_charging.yaml) — helpers + all automations in one file
- 🛠️ **Blueprint usage examples:** [examples/blueprint_usage/automations.yaml](examples/blueprint_usage/automations.yaml)

| Blueprint | Import |
|---|---|
| Scheduled charge start | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fgithuba42r%2Feuc_charging%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Feuc_charging%2Fscheduled_charge.yaml) |
| Stop charging at a limit | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fgithuba42r%2Feuc_charging%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Feuc_charging%2Fcharge_limit.yaml) |
| Charge complete | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fgithuba42r%2Feuc_charging%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Feuc_charging%2Fcharge_complete.yaml) |
| Extended balance charge | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fgithuba42r%2Feuc_charging%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Feuc_charging%2Fbalance_charge.yaml) |
| Charger off when the wheel isn't charging | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fgithuba42r%2Feuc_charging%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Feuc_charging%2Fcharger_idle_off.yaml) |
| Ride day readiness check | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fgithuba42r%2Feuc_charging%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Feuc_charging%2Fride_ready_check.yaml) |

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
- **Protocol Research**: Bluetooth packet parsing was developed using the
  [WheelLog Android app](https://github.com/Wheellog/Wheellog.Android) as the
  protocol reference, and the parsers were validated and verified against the
  [EUC World](https://euc.world) Android app's handling of each wheel brand
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
