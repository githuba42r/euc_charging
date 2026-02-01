# Quick Reference Card

## Essential Commands

### Discovery
```bash
sudo node discover.js
```
Output: All BLE services and characteristics of your device

### Data Capture
```bash
sudo node client.js
```
Output: Real-time battery data and `battery_data.log`

### Analyze Captured Data
```bash
node test-decoder.js
```
Output: Possible interpretations of captured data

### Run Setup
```bash
./setup.sh
```
Check prerequisites and install dependencies

---

## What You Need to Do

### 1. First Run
```bash
cd /home/philg/working/euc-dump
sudo node discover.js
```
**Look for:** Service UUIDs and characteristic UUIDs

### 2. Capture Data
Keep your device charging and run:
```bash
sudo node client.js
# Let it run for 5-10 minutes
# Press Ctrl+C to stop
```
**Creates:** `battery_data.log`

### 3. Analyze
```bash
node test-decoder.js
```
**Output:** Matches between raw data and expected values

### 4. Update Config
Edit `config.js` with discovered UUIDs and format

---

## File Overview

| File | Purpose | Run As |
|------|---------|--------|
| `discover.js` | Find device services | `sudo` |
| `client.js` | Connect & capture data | `sudo` |
| `decoder.js` | Parse battery data | - |
| `test-decoder.js` | Test decoder on logs | - |
| `config.js` | Configuration template | - |

---

## Expected Values (Leaperkim Sherman S)

| Metric | Min | Max | Unit | Notes |
|--------|-----|-----|------|-------|
| Battery Level | 0 | 100 | % | Single digit: 0-100 |
| Voltage | 45 | 67 | V | Typical range |
| Current | -10 | 10 | A | Negative = discharge |

---

## Troubleshooting Checklist

- [ ] Device is powered on
- [ ] Device is in BLE range (< 10m)
- [ ] Bluetooth is enabled: `bluetoothctl show`
- [ ] Have run: `sudo node discover.js` first
- [ ] For permission issues: `sudo usermod -a -G bluetooth $USER`

---

## Key Files to Update

After discovery, edit these files with your findings:

1. **REVERSE_ENGINEERING.md** - Record discovered services
2. **config.js** - Fill in UUIDs and data format
3. **decoder.js** - Update parsing if custom format

---

## Data Format Template

Once discovered, your data likely follows this pattern:

```
Byte 0:     Battery Level        (0-100 as uint8)
Bytes 1-2:  Voltage              (millivolts as uint16 LE)
Bytes 3-4:  Charging Current     (milliamps as int16 LE signed)
```

---

## Home Assistant Later

After successful Node.js implementation:

1. Deploy ESPHome Bluetooth Proxy on ESP32
2. Use protocol discovered above
3. Create Home Assistant sensors
4. Set up automations (e.g., alerts at low battery)

See: `ESPHOME_GUIDE.md`

---

## Useful Links

- **Bluetooth GATT Services:** https://www.bluetooth.com/specifications/gatt/services/
- **ESPHome Docs:** https://esphome.io/
- **Home Assistant:** https://www.home-assistant.io/

---

**Current Status:** Ready to discover
**Next Action:** Run `sudo node discover.js`
