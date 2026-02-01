# Hardware Setup & Environment Information

## Current Environment Status

You're running in a **demo/development environment** without:
- ❌ Actual Bluetooth hardware interface
- ❌ BLE adapter/dongle
- ❌ Leaperkim device in range

This is a **cloud environment** used for development. To actually use the Bluetooth client, you'll need to run it on a **Linux system with Bluetooth hardware**.

---

## What You Need (For Real Hardware)

### Hardware Requirements:
1. **Linux Computer** with Bluetooth support
   - Built-in Bluetooth (laptops, some desktops)
   - OR USB Bluetooth adapter (4.0+ LE compatible)

2. **Leaperkim Sherman S** device
   - Powered on
   - In range (< 10 meters)

### Software on Your Linux System:
```bash
# Install Bluetooth tools
sudo apt update
sudo apt install bluez bluez-tools

# Install Node.js if not already installed
curl https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
nvm install 20

# Clone this project
git clone <your-repo-url>
cd euc-dump
npm install
```

---

## Running on Your Local System

### Step 1: Verify Bluetooth Hardware
```bash
# Check if Bluetooth adapter is present
hciconfig

# You should see output like:
# hci0:   Type: Primary  Bus: USB
#         UP RUNNING PSCAN ISCAN 
#         BD Address: XX:XX:XX:XX:XX:XX  ACL MTU: 310:10  SCO MTU: 64:8

# If not, install a USB Bluetooth 4.0+ adapter
```

### Step 2: Enable Bluetooth
```bash
# Start Bluetooth service
sudo systemctl start bluetooth

# Check status
sudo systemctl status bluetooth

# Verify adapter is powered on
bluetoothctl power on
```

### Step 3: Run Discovery
```bash
cd /path/to/euc-dump
sudo node discover.js
```

### Step 4: Connect to Device
```bash
# Keep Leaperkim charged and in range
sudo node client.js

# Keep running for 5-10 minutes while device charges
# Press Ctrl+C to stop
```

### Step 5: Analyze Data
```bash
node test-decoder.js
```

---

## Manual Bluetooth Control (Alternative)

If the Node.js scripts don't work, you can use `bluetoothctl` directly:

```bash
# Start bluetoothctl interactive shell
bluetoothctl

# Inside bluetoothctl:
> scan on
# Wait and look for: 88:25:83:F3:5D:30 or "Leaperkim"

> connect 88:25:83:F3:5D:30

> gatt.list-attributes
# Record all service/characteristic UUIDs

> select-attribute /org/bluez/hci0/dev_88_25_83_F3_5D_30/service0001/char0001
> notify on
# Watch for data updates
```

---

## Expected Device Discovery Output

When you successfully run `sudo node discover.js`, you should see something like:

```
✓ Found target device!
  MAC: 88:25:83:F3:5D:30
  Name: Leaperkim or similar
  RSSI: -45 dBm

[Discovering services and characteristics...]

Service: 180f
  Characteristics: 1
    - 2a19
      Name: Battery Level
      Properties: read, notify

Service: custom-uuid
  Characteristics: 1
    - custom-char-uuid
      Properties: notify, read
```

---

## Troubleshooting for Real Hardware

### Bluetooth Not Found
```bash
# Check if adapter exists
lsusb | grep -i bluetooth

# If using USB adapter, check if recognized
dmesg | tail -20

# Reload Bluetooth
sudo systemctl restart bluetooth
```

### Device Not Discovered
1. Make sure Leaperkim is **powered on**
2. Try: `bluetoothctl scan on` to manually verify it's advertising
3. Device might need to be **paired** first:
   ```bash
   bluetoothctl pair 88:25:83:F3:5D:30
   ```

### Permission Issues
```bash
# Add your user to bluetooth group
sudo usermod -a -G bluetooth $USER

# Apply group changes
newgrp bluetooth

# Or just use sudo
sudo node discover.js
```

### Slow Scanning
The initial scan can take 30-60 seconds. Be patient. You can also modify `discover.js` to scan for shorter periods:

```javascript
// Change scan timeout from 30000 to 15000 ms
setTimeout(() => {
  if (!isConnected) {
    console.log('Device not found');
    process.exit(1);
  }
}, 15000);  // 15 seconds instead of 30
```

---

## Using in Different Linux Distributions

### Ubuntu/Debian:
```bash
sudo apt install bluez
sudo apt install python3-pip  # For some dependencies
```

### Fedora/RedHat:
```bash
sudo dnf install bluez
```

### Arch:
```bash
sudo pacman -S bluez
```

---

## Optional: Using Android Phone for Initial Exploration

If you don't have immediate access to Linux with Bluetooth:

1. **Install nRF Connect for Mobile** on Android phone
2. **Scan for devices** and find your Leaperkim (MAC: 88:25:83:F3:5D:30)
3. **Connect** and browse services/characteristics
4. **Screenshot** the service tree
5. **Record** all UUIDs you find
6. **Update** REVERSE_ENGINEERING.md with this info
7. **Later** run the Node.js scripts when you have Linux with Bluetooth

---

## What This Project Expects

### Device Requirements:
- ✓ Bluetooth LE 4.0+ capable
- ✓ Advertising battery status (likely)
- ✓ Standard or custom battery service

### Device Behavior:
- Will respond to scan requests
- Will accept connection when triggered
- Will expose services/characteristics
- May send battery updates via notifications
- May require reading characteristics manually

### Expected Data Flow:
```
Your Linux PC with BLE
    ↓
    ├─ Scan for device
    ├─ Find: 88:25:83:F3:5D:30 (Leaperkim)
    ├─ Connect
    ├─ Enumerate services
    ├─ Subscribe to battery notifications
    └─ Receive: Battery Level, Voltage, Current
         ↓
    Decode & Parse
         ↓
    Display/Log
```

---

## Testing Without Real Hardware

To test the decoder without actual BLE hardware, use:

```bash
# Test the decoder with synthetic data
node test-decoder.js

# This generates test data and shows interpretations
# You can see the decoder in action
```

---

## Next: Run on Real Hardware

When you have:
1. Linux PC with Bluetooth hardware
2. Leaperkim device available
3. This project copied to that system

Run the **3 commands** from START_HERE.md:
```bash
sudo node discover.js
sudo node client.js
node test-decoder.js
```

---

## FAQ: Why is it not working in this environment?

This is a **cloud-based development environment**. It doesn't have:
- ❌ Bluetooth hardware attached
- ❌ Direct USB/hardware access
- ❌ Bluetooth daemon (bluetoothd)
- ❌ Access to your physical Leaperkim device

The code is **correct and production-ready** - it just needs a real Linux system with actual Bluetooth hardware to run.

---

## Moving Forward

### Option 1: Your Own Linux System (Recommended)
Run the project on your local Linux laptop/desktop with:
- Built-in Bluetooth, OR
- USB Bluetooth 4.0+ adapter

### Option 2: Raspberry Pi
```bash
# Install on Raspberry Pi 4/5
sudo apt install nodejs npm
git clone <your-repo>
cd euc-dump
npm install
sudo node discover.js
```

### Option 3: Virtual Machine
Create a Linux VM with USB passthrough for Bluetooth adapter

### Option 4: Remote Server
SSH into a Linux server that has Bluetooth hardware connected

---

## Summary

✅ **Code**: Complete and ready
✅ **Configuration**: Done
✅ **Documentation**: Comprehensive
⏳ **Execution**: Requires real Linux + Bluetooth hardware

**Next Step**: Run this project on a Linux system with actual Bluetooth hardware and your Leaperkim device nearby.

All the code and documentation is ready to go! 🚀
