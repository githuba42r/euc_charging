# EUC Charging Home Assistant Integration

A comprehensive Home Assistant integration for Electric Unicycles (EUCs) that supports multiple brands and provides detailed battery monitoring, charging status, and ride statistics.

## Features

- **Multi-Brand Support**: Works with KingSong, Gotway/Begode, Veteran/Leaperkim, and more
- **Automatic Protocol Detection**: Automatically identifies your EUC brand and model
- **Real-time Monitoring**: Voltage, battery percentage, speed, distance, temperature, and more
- **Charging Intelligence**: Accurate charge time estimates using Li-ion charge curve modeling
- **ESPHome Bluetooth Proxy**: Works with ESPHome Bluetooth proxies for extended range
- **BLE Notifications**: Efficient event-driven architecture, no polling required

## Supported Brands and Models

### ✅ Fully Supported

#### Veteran / Leaperkim
- Sherman, Sherman S
- Abrams
- Patton, Patton S
- Lynx
- Sherman L
- Oryx
- Nosfet Apex, Nosfet Aero

**Features**: Full telemetry including voltage, speed, current, temperature, distance, pitch angle, firmware version, automatic model detection

#### KingSong
- All KingSong models (KS-14, KS-16, KS-18, KS-S series, etc.)
- Automatic voltage detection (16S through 42S)

**Features**: Voltage, speed, current, temperature, distance, automatic battery configuration detection

#### Gotway / Begode
- All Gotway/Begode models (MCM, Monster, MSX, Nikola, RS, Master, etc.)
- Automatic voltage detection

**Features**: Voltage, speed, current, temperature, distance, PWM, automatic battery configuration detection

### 🚧 Requires Active Communication (Community Contributions Welcome!)

The following brands require **bidirectional BLE communication** (not just passive monitoring). This requires additional coordinator-level changes to support write operations, keep-alive timers, and in some cases encryption. See [IMPLEMENTATION_STATUS.md](../../IMPLEMENTATION_STATUS.md) for details.

#### InMotion V1 Protocol
- V3, V5, V5F, V8, V8F, V8S
- V10, V10F, V10S, V10SF, V10T, V10FT
- Solowheel Glide 3
- R-series

**Status**: Protocol documented, requires write characteristic support and keep-alive timer

#### InMotion V2 Protocol
- V11, V11Y
- V12 HS/HT/PRO, V12S
- V13, V13 PRO
- V14 (50GB/50S)
- V9

**Status**: Protocol documented, requires write characteristic support and keep-alive timer

#### Ninebot
- Ninebot One (C, E, E+, P, A1, S2)
- Ninebot Mini

**Status**: Protocol documented, requires encryption key exchange and write characteristic support

#### Ninebot Z
- Ninebot Z6, Z8, Z10

**Status**: Protocol documented, requires encryption key exchange and write characteristic support

**Want to help?** If you own one of these models, you can contribute! See [CONTRIBUTING.md](../../CONTRIBUTING.md) and [IMPLEMENTATION_STATUS.md](../../IMPLEMENTATION_STATUS.md) for how to help add support.

## Installation

### HACS (Recommended - Coming Soon)

1. Open HACS in Home Assistant
2. Go to Integrations
3. Search for "EUC Charging"
4. Click Install

### Manual Installation

1. Copy the `euc_charging` directory to your Home Assistant's `custom_components` directory:
   ```
   /config/custom_components/euc_charging/
   ```
2. Restart Home Assistant
3. Go to **Settings > Devices & Services**
4. Click **Add Integration** and search for "EUC Charging"
5. Select your EUC from the discovered devices list

## Usage

### Prerequisites

- **Home Assistant 2023.1 or newer**
- **Bluetooth adapter** - Built-in or USB Bluetooth adapter
- **ESPHome Bluetooth Proxy** (optional but recommended for extended range)

### Setup

1. **Power on your EUC** - Make sure your EUC is powered on and within Bluetooth range
2. **Disconnect other apps** - Ensure no other app (official EUC app, WheelLog, etc.) is connected to your EUC
3. **Add the integration** - Home Assistant will automatically discover your EUC if it's in range
4. **Configure** - Select your EUC from the list or manually enter the MAC address

### ESPHome Bluetooth Proxy

For extended range and better reliability, use an ESP32 with ESPHome as a Bluetooth proxy:

```yaml
esphome:
  name: euc-ble-proxy
  
esp32:
  board: esp32dev
  framework:
    type: arduino

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

api:
  encryption:
    key: !secret api_encryption_key

bluetooth_proxy:
  active: true
```

Place the ESP32 near where you park your EUC, and the integration will automatically use it.

## Sensors

### Main Sensors

- **Voltage** (V) - Battery voltage with system voltage in attributes
- **Battery** (%) - Calculated percentage with charge time estimates
- **Current** (A) - Phase current (or battery current for some models)
- **Temperature** (°C) - Mainboard/controller temperature
- **Speed** (km/h) - Current speed
- **Trip Distance** (km) - Trip odometer
- **Total Distance** (km) - Total odometer
- **Charging** (binary) - Charging status

### Charging Sensors (when charging)

- **Time to 80%** - Estimated time to reach 80% charge
- **Time to 90%** - Estimated time to reach 90% charge
- **Time to 95%** - Estimated time to reach 95% charge
- **Time to 100%** - Estimated time to reach full charge
- **Charge Rate** (%/min) - Current charging rate

### Advanced Sensors (model-dependent)

- **Pitch Angle** (°) - Wheel pitch angle
- **Roll Angle** (°) - Wheel roll angle
- **PWM** (%) - Motor PWM percentage
- **Firmware Version** - EUC firmware version

## Battery Configurations

The integration automatically detects and correctly calculates battery percentage for different cell configurations:

- **16S** (67.2V) - Older KingSong models
- **20S** (84.0V) - KS-18L, KS-16X, many Gotway models
- **24S** (100.8V) - Sherman, Sherman S, KS-S19, most modern wheels
- **30S** (126.0V) - Patton, Patton S, KS-S20, KS-S22, high-performance models
- **36S** (151.2V) - Lynx, Sherman L, Nosfet Apex, extreme-range models
- **42S** (176.4V) - Oryx, extreme high-voltage models

## Command-Line Tools for Contributors

This integration includes tools to help contributors add support for new models:

### EUC Logger (`euc_logger.py`)

Capture BLE data from your EUC:

```bash
# Scan for nearby EUCs
python euc_logger.py scan

# Capture data (with auto-detection)
python euc_logger.py capture AA:BB:CC:DD:EE:FF --auto-detect --duration 60

# Capture with known brand
python euc_logger.py capture AA:BB:CC:DD:EE:FF --brand veteran --model "Sherman S" --duration 300

# List captures
python euc_logger.py list

# View a capture
python euc_logger.py view euc_captures/capture.json
```

### EUC Analyzer (`euc_analyzer.py`)

Analyze captured data to reverse engineer protocols:

```bash
# Analyze packet structure
python euc_analyzer.py analyze euc_captures/capture.json

# Compare two captures (e.g., idle vs charging)
python euc_analyzer.py compare capture_idle.json capture_charging.json

# Extract patterns
python euc_analyzer.py patterns euc_captures/capture.json
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for a complete guide on adding support for new models.

## Troubleshooting

### EUC Not Discovered

1. **Check Bluetooth** - Ensure Home Assistant can see Bluetooth devices (Settings > System > Hardware)
2. **Check range** - Make sure your EUC is within Bluetooth range (typically 10m)
3. **Disconnect other apps** - EUC can only connect to one BLE client at a time
4. **Restart Bluetooth** - Restart Home Assistant or reboot the host
5. **Check logs** - Look for errors in Home Assistant logs (Settings > System > Logs)

### Connection Drops

1. **Signal strength** - Check if EUC is too far from Bluetooth adapter
2. **Use ESP32 proxy** - Add an ESPHome Bluetooth proxy near your EUC
3. **Check interference** - Other 2.4GHz devices (WiFi, microwaves) can interfere
4. **Update firmware** - Ensure Home Assistant and ESPHome are up to date

### Incorrect Battery Percentage

1. **Check system voltage** - The integration should auto-detect, but you can verify in sensor attributes
2. **Battery age** - Old batteries may not reach full voltage
3. **Calibration** - Some EUC BMS may need calibration (charge to 100%, then fully discharge once)

### Charging Not Detected

1. **Check current sensor** - Should show negative values when charging
2. **Check charge_mode** - Look at sensor attributes for the raw charge_mode value
3. **Brand-specific** - Some brands don't report charging status explicitly

## Advanced Configuration

### Automation Examples

#### Notify When Charging Complete

```yaml
automation:
  - alias: "EUC Charging Complete"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sherman_s_battery
        above: 95
    condition:
      - condition: state
        entity_id: binary_sensor.sherman_s_charging
        state: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "EUC Charged"
          message: "Sherman S is at {{ states('sensor.sherman_s_battery') }}%"
```

#### Alert on Low Battery

```yaml
automation:
  - alias: "EUC Low Battery Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sherman_s_battery
        below: 20
    action:
      - service: notify.mobile_app
        data:
          title: "EUC Low Battery"
          message: "Sherman S battery at {{ states('sensor.sherman_s_battery') }}%"
```

#### Track Charging Sessions

```yaml
automation:
  - alias: "EUC Charging Started"
    trigger:
      - platform: state
        entity_id: binary_sensor.sherman_s_charging
        from: "off"
        to: "on"
    action:
      - service: input_datetime.set_datetime
        target:
          entity_id: input_datetime.euc_charge_start
        data:
          timestamp: "{{ now().timestamp() }}"
```

## Contributing

We welcome contributions! If you have an EUC model that isn't supported yet, you can help add it.

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- How to capture data from your EUC
- How to analyze the BLE protocol
- How to implement a decoder
- How to submit a pull request

## Credits

- **Protocol Research**: Based on analysis of [WheelLog Android app](https://github.com/Wheellog/Wheellog.Android)
- **Home Assistant Integration**: Built using Home Assistant's integration framework
- **BLE Library**: Uses [Bleak](https://github.com/hbldh/bleak) for cross-platform Bluetooth LE support

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

- **Issues**: Report bugs or request features on [GitHub Issues](https://github.com/githuba42r/euc_charging/issues)
- **Discussions**: Ask questions or share tips in [GitHub Discussions](https://github.com/githuba42r/euc_charging/discussions)
- **Discord**: Join the EUC community on Discord (link coming soon)

## Disclaimer

This integration is not affiliated with or endorsed by any EUC manufacturer. Use at your own risk. Always follow safe charging practices and manufacturer guidelines.

**Safety Reminder**: Never leave your EUC charging unattended. Always use the official charger and follow manufacturer guidelines.
