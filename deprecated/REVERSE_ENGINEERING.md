# Reverse Engineering Guide - Leaperkim Sherman S Bluetooth Protocol

## Overview
This guide will help you discover the exact Bluetooth LE protocol used by your Leaperkim Sherman S unicycle.

## Step 1: Device Discovery & Service Enumeration

### Run the discovery script
```bash
sudo node discover.js
```

This will:
1. Scan for your device (MAC: 88:25:83:F3:5D:30)
2. Connect to it
3. Enumerate all services and characteristics
4. Display the complete service tree

### What to look for
- **Service UUIDs**: Look for custom UUIDs (not standard 128-bit Bluetooth UUIDs)
- **Characteristic UUIDs**: Note which ones have 'notify' or 'indicate' properties
- **Standard Services**: May include:
  - `180F` - Battery Service
  - `180A` - Device Information
  - Custom services (8+ characters)

## Step 2: Packet Capture & Analysis

If the client doesn't receive data automatically, you may need to capture the raw BLE packets.

### Using hcidump (Linux)
```bash
# Start hcidump to capture packets
sudo hcidump -i hci0 -X

# In another terminal, run the client
sudo node client.js
```

Look for:
- ATT (Attribute Transport) packets
- Handle values and their payloads
- Notification/indication packets

### Using Wireshark (Recommended for detailed analysis)
```bash
# Install if needed:
sudo apt install wireshark

# Start capture (GUI):
sudo wireshark

# Filter for BLE:
- Set interface to bluetooth device
- In Wireshark: add filter `btle`
- Look for ATT packets with your device's MAC address
```

## Step 3: Data Pattern Recognition

Once you capture data, look for patterns:

### Battery Level (0-100%)
- Usually a single byte value
- Characteristic UUID: `2a19` (standard)
- Range: 0x00-0x64 (0-100)

### Voltage
- Usually 2-4 bytes
- Common encodings:
  - Millivolts: 3000-5000 mV range
  - 0.1V units: multiply by 0.1
  - Raw ADC value: device-specific

### Current
- Usually 2-4 bytes, can be signed (for discharge direction)
- Common encodings:
  - Milliamps: 0-1000 mA for charging
  - Negative values for discharge

### Example Data Structures

#### Single Battery Characteristic (3 bytes)
```
Byte 0:     Battery Level (%)
Bytes 1-2:  Voltage (little-endian uint16, mV)
```

#### Extended Data (5 bytes)
```
Byte 0:     Battery Level (%)
Bytes 1-2:  Voltage (little-endian uint16, mV)
Bytes 3-4:  Current (little-endian int16, mA)
```

## Step 4: Manual Testing

### Connect with bluetoothctl
```bash
bluetoothctl

# Scan for devices
scan on

# Connect to your device
connect 88:25:83:F3:5D:30

# View services
gatt.list-attributes

# Enable notifications on a characteristic
select-attribute /org/bluez/hci0/dev_88_25_83_F3_5D_30/service0001/char0002
notify on

# Monitor incoming data
```

## Step 5: Documenting the Protocol

Once you identify the data structure, document it:

### Create a format specification
Update `decoder.js` with the discovered format:

```javascript
static LEAPERKIM_BATTERY_FORMAT = [
  { name: 'batteryLevel', type: 'uint8', unit: '%' },
  { name: 'voltage', type: 'uint16le', unit: 'mV', scale: 0.001, unit_final: 'V' },
  { name: 'current', type: 'int16le', unit: 'mA', scale: 0.001, unit_final: 'A' },
];
```

### Test the decoder
```bash
# Run with test data to verify parsing
node test-decoder.js
```

## Step 6: Integration & Verification

### Verify your decoded values
- Battery level should be 0-100%
- Voltage should match device's display
- Current should be positive when charging, zero when idle

### Log & Monitor
The client logs all data to `battery_data.log`. Analyze it:

```bash
# Watch in real-time
tail -f battery_data.log

# Extract just battery values
grep "Battery Level" battery_data.log
```

## Common Issues & Solutions

### "Device not found"
- Device may not be advertising
- May require active pairing first
- Try: `bluetoothctl connect 88:25:83:F3:5D:30`

### "No notifications received"
- Device may use polling (read characteristic periodically)
- Try the client's read-based fallback
- Check if notifications are enabled

### "Data seems wrong"
- Check byte order (little-endian vs big-endian)
- Verify scale factors (mV vs V, mA vs A)
- Compare against device's built-in display

### Permission Errors
- Add user to bluetooth group: `sudo usermod -a -G bluetooth $USER`
- Logout and login again
- Or use `sudo node client.js`

## Resources

### Bluetooth LE Documentation
- [Bluetooth SIG GATT Specs](https://www.bluetooth.com/specifications/specs/)
- [Common Service UUIDs](https://www.bluetooth.com/specifications/gatt/services/)
- [Common Characteristic UUIDs](https://www.bluetooth.com/specifications/gatt/characteristics/)

### Similar Projects (for reference)
- King Song wheel BLE protocol reverse engineering
- Inmotion (IPS) wheel communication analysis
- Gotway wheel BLE protocol documentation

## Next Steps

Once protocol is reverse-engineered:

1. Create ESPHome component for Bluetooth proxy
2. Integrate with Home Assistant
3. Add Home Assistant automations based on battery level
4. Monitor charging cycles and battery health

---

**Record your findings here:**

### Discovered Services
```
[Paste output from discovery.js here]
```

### Battery Characteristic Details
- UUID: 
- Service UUID:
- Properties: (notify, read, indicate, etc.)
- Data format: (bytes, structure)

### Test Data Examples
```
[Paste hex dump samples here]
Decoded as: [Battery%, Voltage, Current]
```
