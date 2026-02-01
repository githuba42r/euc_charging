# Leaperkim Sherman S Bluetooth LE Client Project

## Project Status: ✅ Ready for Use

A complete Node.js implementation for reverse-engineering and connecting to the Leaperkim Sherman S Electric Unicycle via Bluetooth LE to retrieve battery charging status (level, voltage, current).

---

## Quick Start (3 Steps)

```bash
# 1. Enter project directory
cd /home/philg/working/euc-dump

# 2. Discover device services
sudo node discover.js

# 3. Capture and analyze data
sudo node client.js
# Let run while device charges for 5+ minutes, then Ctrl+C
```

---

## What's Included

### Core Scripts
- **discover.js** - Scan for device and enumerate BLE services/characteristics
- **client.js** - Connect to device and capture battery data in real-time
- **decoder.js** - Parse raw BLE data into human-readable battery metrics
- **test-decoder.js** - Test and validate the decoder

### Documentation
- **GETTING_STARTED.md** - Step-by-step guide for first-time use
- **REVERSE_ENGINEERING.md** - Detailed protocol reverse-engineering guide
- **ESPHOME_GUIDE.md** - Home Assistant integration (future)
- **QUICK_REFERENCE.md** - Command reference card
- **README.md** - Project overview

### Configuration
- **config.js** - Template for protocol configuration
- **package.json** - Node.js dependencies and scripts

---

## Key Features

✅ **Automatic Device Discovery**
- Scans for your device by MAC address (88:25:83:F3:5D:30)
- Automatically connects and discovers services

✅ **Multi-Mode Data Collection**
- Subscribes to characteristic notifications (preferred)
- Falls back to periodic reads if device doesn't support notifications
- Attempts to read all accessible characteristics

✅ **Intelligent Data Analysis**
- Decoder provides multiple interpretations for each data sample
- Confidence scores for each hypothesis
- Recognizes standard BLE battery service format
- Handles custom proprietary data structures

✅ **Comprehensive Logging**
- Real-time console output
- Persistent file logging to `battery_data.log`
- Timestamped entries with hex and ASCII representation

✅ **Test Framework**
- Synthetic test data generation
- Log file analysis
- Decoder validation

✅ **ESPHome Ready**
- Template configurations for Home Assistant integration
- Sample C++ component code
- YAML configuration examples

---

## Technology Stack

- **Node.js** (v20+) - JavaScript runtime
- **Noble** - Bluetooth LE library for Linux/Mac/Windows
- **Home Assistant/ESPHome** - Future integration target

---

## Project Structure

```
euc-dump/
├── 📄 index.md                    (This file - Project overview)
├── 📄 GETTING_STARTED.md          (Step-by-step guide)
├── 📄 QUICK_REFERENCE.md          (Command reference)
├── 📄 REVERSE_ENGINEERING.md      (Detailed protocol docs)
├── 📄 ESPHOME_GUIDE.md            (Future HA integration)
│
├── 📄 package.json                (Node.js config)
├── 🔧 setup.sh                    (Setup script)
│
├── discover.js                    (BLE service discovery)
├── client.js                      (Main BLE client)
├── decoder.js                     (Data parsing)
├── test-decoder.js                (Test harness)
├── config.js                      (Configuration template)
│
└── battery_data.log               (Generated - captured data)
```

---

## Usage Examples

### 1. First Time Setup
```bash
./setup.sh
# Checks Node.js, Bluetooth tools, installs dependencies
```

### 2. Discover Device Services
```bash
sudo node discover.js
# Output: All available services and characteristics
# Time: ~30 seconds
```

### 3. Connect and Capture Data
```bash
sudo node client.js
# Keep running while device charges
# Logs to battery_data.log
# Press Ctrl+C to stop
```

### 4. Analyze Captured Data
```bash
node test-decoder.js
# Shows interpretations of captured data
# No sudo needed - works on log files
```

### 5. Test with Sample Data
```bash
# In Node.js REPL
const TestHarness = require('./test-decoder.js');
const harness = new TestHarness();
harness.testManualData('2a19', '55'); // 85% battery
```

### Using npm Scripts
```bash
npm run discover   # sudo node discover.js
npm run client     # sudo node client.js
npm run analyze    # node test-decoder.js
```

---

## Device Information

| Property | Value |
|----------|-------|
| Device | Leaperkim Sherman S Electric Unicycle |
| MAC Address | 88:25:83:F3:5D:30 |
| Data Needed | Battery Level, Voltage, Current |
| Goal | Charge Status Monitoring |
| Target | Home Assistant + ESPHome |

---

## Reverse Engineering Workflow

### Step 1: Device Discovery (30 seconds)
```bash
sudo node discover.js
```
Find all available services and characteristics.

### Step 2: Data Capture (5-10 minutes)
```bash
sudo node client.js
```
While device is charging, capture raw BLE data.

### Step 3: Analysis (immediate)
```bash
node test-decoder.js
```
Review captured data for patterns.

### Step 4: Documentation
Update `config.js` and `REVERSE_ENGINEERING.md` with findings.

### Step 5: Validation
Run decoder again to verify format is correct.

### Step 6: Integration
Implement in ESPHome or expand Node.js client.

---

## Expected Battery Data Patterns

### Standard Bluetooth Battery Service (UUID: 180F)
- Single characteristic: 2A19 (Battery Level)
- Format: Single byte (0-100%)
- Properties: read, notify

### Custom Battery Characteristic
Many devices use proprietary formats, typically:
- **3 bytes**: Level (1) + Voltage (2)
- **5 bytes**: Level (1) + Voltage (2) + Current (2)

### Value Ranges
- Battery Level: 0-100 (%)
- Voltage: 45-67 (V) for Sherman S
- Current: 0-5 (A) charging, can be negative when discharging

---

## Troubleshooting

### Device Not Found
```bash
# Check Bluetooth is enabled
bluetoothctl show

# Manual scan
bluetoothctl scan on

# Check device appears
bluetoothctl devices
```

### Permission Errors
```bash
# Option 1: Add to bluetooth group
sudo usermod -a -G bluetooth $USER
# Log out and back in

# Option 2: Use sudo
sudo node discover.js
```

### No Data Received
- Device may use read-based polling instead of notifications
- May require write command to enable data
- Try manual connection with bluetoothctl first

---

## Next Phases

### Phase 2: ESPHome Integration
- Deploy Bluetooth proxy on ESP32
- Create Home Assistant sensors
- Set up automations

### Phase 3: Advanced Features
- Historical data logging
- Battery health tracking
- Charge cycle analysis
- Email/SMS alerts

### Phase 4: Community Contribution
- Publish protocol documentation
- Share with EUC community
- Create generic unicycle battery monitor

---

## Dependencies

- **noble**: `^1.9.1` - Bluetooth LE library
  - Auto-installed via `npm install`
  - Handles Linux, Mac, Windows
  - Requires sudo for Bluetooth access

## System Requirements

- **Linux**: Bluetooth hardware + bluez
- **macOS**: Built-in Bluetooth
- **Windows**: Bluetooth adapter
- **Node.js**: v14 or later
- **npm**: v6 or later

---

## Security & Privacy

- No credentials stored in code
- No external API calls
- All data processed locally
- Optional Home Assistant integration requires network setup

---

## File Descriptions

### Executables
- **discover.js** - Scans for BLE devices and enumerates services
- **client.js** - Main BLE client for data collection
- **test-decoder.js** - Analysis tool for captured data

### Libraries
- **decoder.js** - Battery data parser (imported by client)
- **config.js** - Configuration template (for future use)

### Documentation
- **README.md** - Original project overview
- **GETTING_STARTED.md** - Beginner's guide (recommended start)
- **QUICK_REFERENCE.md** - Command cheat sheet
- **REVERSE_ENGINEERING.md** - Detailed technical guide
- **ESPHOME_GUIDE.md** - Home Assistant integration
- **INDEX.md** - This file

---

## Commands Reference

| Command | Purpose | Needs Sudo |
|---------|---------|-----------|
| `npm install` | Install dependencies | No |
| `npm run discover` | Find device | Yes |
| `npm run client` | Capture data | Yes |
| `npm run analyze` | Analyze logs | No |
| `./setup.sh` | Check setup | No |

---

## Tips for Success

1. **Run discovery first** - Always do this before anything else
2. **Device must be powered on** - And in BLE range
3. **Plug in for charging** - Data is most interesting during charging
4. **Let client run** - Capture for 5+ minutes for good sample
5. **Check logs** - `cat battery_data.log` to verify data
6. **Compare to device** - Cross-check with device's built-in display

---

## Resources

### Bluetooth Documentation
- [Bluetooth GATT Services](https://www.bluetooth.com/specifications/gatt/services/)
- [BLE Characteristic UUIDs](https://www.bluetooth.com/specifications/gatt/characteristics/)

### Related Projects
- [King Song Wheel Protocol](https://github.com/search?q=king+song+ble)
- [Inmotion Wheel Reverse Engineering](https://github.com/search?q=inmotion+ble)
- [Gotway Wheel Analysis](https://github.com/search?q=gotway+ble)

### Tools
- **nRF Connect** (Android) - Mobile BLE scanner
- **Wireshark** (Linux) - Packet capture
- **hcidump** (Linux) - Raw BLE sniffer
- **bluetoothctl** (Linux) - Bluetooth control

---

## License

MIT License - Feel free to use, modify, and share!

---

## Support

### Issues
- Check `TROUBLESHOOTING.md` section above
- Review device logs: `cat battery_data.log`
- Run: `node test-decoder.js`

### Questions
- See `REVERSE_ENGINEERING.md` for detailed explanations
- Check `QUICK_REFERENCE.md` for commands
- Read `ESPHOME_GUIDE.md` for integration help

---

## Project Timeline

- **Today**: Discovery & initial setup
- **Next**: Data capture & analysis
- **Later**: Protocol documentation
- **Future**: ESPHome integration
- **Eventually**: Home Assistant automations

---

**Start here:** Read `GETTING_STARTED.md` or `QUICK_REFERENCE.md`

**First action:** Run `sudo node discover.js`

Good luck! 🚀
