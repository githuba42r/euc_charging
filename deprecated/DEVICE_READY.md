# ✅ Bluetooth Hardware Detected & Configured

## Great News!

Your system has Bluetooth hardware detected:
- **Bluetooth Adapter**: Intel AX211 Bluetooth (Bus 003 Device 005)
- **bluetoothctl**: Available and working
- **Status**: Ready to scan and connect

---

## What's Next?

### Step 1: Power On Your Leaperkim Device

Make sure your Leaperkim Sherman S is:
- ✅ Powered on
- ✅ In Bluetooth range (< 10 meters)
- ✅ Not already connected to another device

### Step 2: Run Discovery

Once your device is on and ready, run:

```bash
cd /home/philg/working/euc-dump
node discover-bluetoothctl.js
```

This will:
1. Scan for your device (MAC: 88:25:83:F3:5D:30)
2. Connect to it
3. List all services and characteristics
4. Show you the exact UUIDs you need

### Step 3: Record the Output

When you see output like this:

```
✓ Found target device! Connecting to 88:25:83:F3:5D:30...

Services and Characteristics:
============================

Service: 180f
  - 2a19 (Battery Level)
    
Service: custom-uuid
  - custom-char
```

Copy these UUIDs into REVERSE_ENGINEERING.md for documentation.

---

## Available Discovery Scripts

You have multiple options:

### Option 1: Using bluetoothctl wrapper (Recommended - No Permissions Needed)
```bash
node discover-bluetoothctl.js
```
✅ Works without sudo
✅ Uses standard Bluetooth tools
✅ Shows all discovered devices

### Option 2: Using node noble (Requires Bluetooth Group Permission)
```bash
node discover.js
```
⚠️ Requires: `sudo usermod -a -G bluetooth $USER` (then log out/in)
✅ More detailed output
✅ Direct BLE communication

### Option 3: Manual bluetoothctl
```bash
bluetoothctl
> scan on
> connect 88:25:83:F3:5D:30
> gatt.list-attributes
```
✅ Most direct control
✅ No scripting needed

---

## What Happens When Device is Found

When your Leaperkim is discovered, you'll see:

```
✓ Found target device! Connecting to 88:25:83:F3:5D:30...
✓ Connected

Services and Characteristics:
============================

[List of services and characteristics with UUIDs]
```

---

## Expected Services

Based on typical EV unicycle architecture, you should see:

### Standard Services (Very Likely)
- **180F** - Battery Service
  - **2A19** - Battery Level (0-100%)
  
### Device Info (Likely)
- **180A** - Device Information
  - **2A29** - Manufacturer Name
  - **2A24** - Model Number
  - **2A25** - Serial Number
  - **2A26** - Firmware Version

### Custom Services (Possible)
- Custom UUIDs for extended battery data
  - Voltage
  - Current/Charging State
  - Temperature
  - Other metrics

---

## Data Capture

Once discovery is complete, you can capture battery data:

```bash
node client.js
```

This will:
1. Connect to your device
2. Subscribe to battery notifications
3. Log all data to battery_data.log
4. Show real-time updates in console

Keep it running while your device charges for best results.

---

## Analysis

After capturing data, analyze it:

```bash
node test-decoder.js
```

This will show:
- Raw hex data
- Possible interpretations
- Confidence scores for each interpretation
- Decoded battery metrics (level, voltage, current)

---

## Troubleshooting

### Device Not Found After Powering On

1. **Check device is advertising**:
   ```bash
   bluetoothctl
   > scan on
   # Wait 10-15 seconds and look for your device
   ```

2. **Check range**: Device must be within 10 meters

3. **Check conflicts**: Make sure it's not connected to another device

4. **Restart Bluetooth**:
   ```bash
   sudo systemctl restart bluetooth
   ```

### Connection Failed

Device might require pairing first:
```bash
bluetoothctl
> scan on
# Find your device in the list
> pair 88:25:83:F3:5D:30
> connect 88:25:83:F3:5D:30
```

### No Data Received

Device might use polling instead of notifications. The client.js script handles this automatically with fallback reads.

---

## Next Steps Checklist

- [ ] Power on your Leaperkim device
- [ ] Verify it's in range and not connected to other devices
- [ ] Run `node discover-bluetoothctl.js`
- [ ] Record all service/characteristic UUIDs
- [ ] Update REVERSE_ENGINEERING.md with your findings
- [ ] Run `node client.js` while device charges
- [ ] Analyze results with `node test-decoder.js`
- [ ] Document the protocol in config.js

---

## System Status Summary

✅ **Bluetooth Hardware**: Detected (Intel AX211)
✅ **Bluetooth Daemon**: Running (bluetoothctl working)
✅ **Node.js**: v20.19.0
✅ **noble Library**: @abandonware/noble installed
✅ **Discovery Scripts**: Ready (both options available)
✅ **Client Script**: Ready
✅ **Decoder**: Ready and tested
✅ **Documentation**: Complete

**Status**: READY FOR DEVICE TESTING

---

## When Device is Ready

```bash
cd /home/philg/working/euc-dump

# 1. Discover services
node discover-bluetoothctl.js

# 2. Capture battery data (keep running while charging)
node client.js

# 3. Analyze captured data
node test-decoder.js
```

Your system is fully configured and ready to reverse-engineer the Leaperkim charging protocol! 🚀

---

For more information, see:
- **HARDWARE_SETUP.md** - Hardware configuration
- **START_HERE.md** - Quick start guide
- **REVERSE_ENGINEERING.md** - Protocol documentation

