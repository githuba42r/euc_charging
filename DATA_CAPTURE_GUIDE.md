# EUC Data Capture Guide

This guide will help you capture BLE data from your EUC and prepare it for analysis. Whether you're adding support for a new model or helping improve existing support, following these steps will make the process smooth and efficient.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Step 1: Prepare Your Environment](#step-1-prepare-your-environment)
- [Step 2: Capture Data](#step-2-capture-data)
- [Step 3: Review Your Captures](#step-3-review-your-captures)
- [Step 4: Share Your Data](#step-4-share-your-data)
- [Tips for High-Quality Captures](#tips-for-high-quality-captures)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Hardware
- Your EUC (fully charged or at least 50% battery)
- A computer with Bluetooth (built-in or USB adapter)
- Access to your EUC's Bluetooth while it's powered on

### Software
- Python 3.9 or newer
- `bleak` Python library for BLE communication
- The capture tools from this repository

### Information You'll Need
- Your EUC's brand (e.g., KingSong, Gotway, InMotion, Veteran)
- Your EUC's model (e.g., "KS-S18", "RS HT", "V12 HT", "Sherman Max")
- Your EUC's battery configuration:
  - Voltage (e.g., 100.8V for 24S, 126V for 30S)
  - Capacity in Wh (e.g., 2700Wh)
  - Number of cells in series (e.g., 24S, 30S, 36S)

## Step 1: Prepare Your Environment

### Install Python Dependencies

```bash
# Navigate to the project directory
cd /path/to/euc-dump

# Install required packages
pip install bleak

# Or use requirements.txt if available
pip install -r requirements.txt
```

### Test Your Bluetooth

```bash
# Quick test to see if Bluetooth is working
python euc_logger.py scan
```

You should see a list of nearby Bluetooth devices. If you get an error, make sure:
- Bluetooth is enabled on your computer
- You have permissions to access Bluetooth (on Linux, you may need to add your user to the `bluetooth` group)

## Step 2: Capture Data

### Capture Scenario 1: Idle State (REQUIRED)

This captures your EUC when it's powered on but not moving or charging. This is the baseline data.

```bash
python euc_logger.py capture AA:BB:CC:DD:EE:FF \
  --brand <your_brand> \
  --model "Your Model Name" \
  --duration 60 \
  --auto-detect \
  --output euc_captures/idle.json
```

**Replace:**
- `AA:BB:CC:DD:EE:FF` with your EUC's MAC address (from the scan)
- `<your_brand>` with: `kingsong`, `gotway`, `veteran`, `inmotion`, `ninebot`, or `begode`
- `"Your Model Name"` with your specific model (e.g., "RS HT", "V12 HT")

**What to do:**
1. Power on your EUC
2. Let it sit idle (don't ride, don't charge)
3. Run the command above
4. Wait 60 seconds
5. The capture will automatically save

### Capture Scenario 2: Charging State (REQUIRED)

This captures your EUC while it's charging. This helps identify charging status and battery percentage changes.

```bash
python euc_logger.py capture AA:BB:CC:DD:EE:FF \
  --brand <your_brand> \
  --model "Your Model Name" \
  --duration 300 \
  --auto-detect \
  --output euc_captures/charging.json
```

**What to do:**
1. Plug in your EUC to its charger
2. Wait about 30 seconds for charging to stabilize
3. Run the command above
4. Let it capture for 5 minutes (300 seconds)
5. You can stop early with Ctrl+C if needed

**Why 5 minutes?** This gives enough time to see:
- Battery percentage increasing
- Voltage changes
- Charging current patterns

### Capture Scenario 3: Different Battery Levels (RECOMMENDED)

If possible, capture at different battery levels to help calibrate the battery percentage calculation.

```bash
# At ~25% battery
python euc_logger.py capture AA:BB:CC:DD:EE:FF \
  --brand <your_brand> \
  --model "Your Model Name" \
  --duration 60 \
  --auto-detect \
  --output euc_captures/idle_25pct.json

# At ~50% battery
python euc_logger.py capture AA:BB:CC:DD:EE:FF \
  --brand <your_brand> \
  --model "Your Model Name" \
  --duration 60 \
  --auto-detect \
  --output euc_captures/idle_50pct.json

# At ~75% battery
python euc_logger.py capture AA:BB:CC:DD:EE:FF \
  --brand <your_brand> \
  --model "Your Model Name" \
  --duration 60 \
  --auto-detect \
  --output euc_captures/idle_75pct.json
```

### Capture Scenario 4: Moving (OPTIONAL, Advanced)

**⚠️ SAFETY WARNING**: Only attempt this if you can safely capture data while riding. Have someone else handle the computer/phone, or mount your device securely on the EUC.

```bash
python euc_logger.py capture AA:BB:CC:DD:EE:FF \
  --brand <your_brand> \
  --model "Your Model Name" \
  --duration 120 \
  --auto-detect \
  --output euc_captures/riding.json
```

**What to capture:**
- Slow riding (5-10 km/h) in a parking lot or empty area
- Acceleration and braking
- Turning left and right (if your EUC has gyroscope data)

This helps identify:
- Speed encoding
- Acceleration/tilt angle data
- Current draw during riding

## Step 3: Review Your Captures

### List All Captures

```bash
python euc_logger.py list
```

This shows all your captured files with basic info:
- Brand and model
- MAC address
- Timestamp
- Duration
- Number of packets (raw and decoded)

### View a Capture

```bash
python euc_logger.py view euc_captures/idle.json
```

This displays:
- Metadata about the capture
- First 10 raw packets (hex format)
- First 5 decoded packets (if protocol was detected)

**What to check:**
- ✅ Packets were captured (look for "total_packets" > 0)
- ✅ Protocol was detected (look for "decoder_used")
- ✅ Some packets were decoded (look for "decoded_packets" > 0)

If packets aren't being decoded, that's okay! That just means your EUC needs protocol analysis (see the Analysis Guide).

## Step 4: Share Your Data

### Create a Data Package

Organize your captures into a folder structure:

```
my_euc_data/
├── README.txt
├── captures/
│   ├── idle.json
│   ├── charging.json
│   ├── idle_25pct.json (optional)
│   ├── idle_50pct.json (optional)
│   ├── idle_75pct.json (optional)
│   └── riding.json (optional)
└── specs.txt
```

### Create README.txt

Include this information in `README.txt`:

```
EUC Data Capture Package

Brand: [Your EUC Brand]
Model: [Your EUC Model]
Firmware Version: [If known]

Battery Specifications:
- Configuration: [e.g., 30S or "30 cells in series"]
- Nominal Voltage: [e.g., 111V]
- Maximum Voltage: [e.g., 126V]
- Capacity: [e.g., 2700Wh]

Capture Details:
- idle.json: Captured at [XX]% battery, idle
- charging.json: Captured while charging from [XX]% to [YY]%
- [other captures and their conditions]

Additional Notes:
- [Any special circumstances]
- [Issues encountered]
- [Questions or concerns]

Contact: [Your name/username]
Date: [Capture date]
```

### Create specs.txt

List detailed specifications:

```
Brand: [Brand]
Model: [Model]
Year: [Year, if known]
Motor: [e.g., "2500W"]
Battery: [e.g., "30S6P, 2700Wh, 126V nominal"]
Tire: [e.g., "20 inches"]
Weight: [e.g., "35kg"]
Top Speed: [e.g., "80 km/h"]
Range: [e.g., "150km"]

Official App: [Name of manufacturer's app]
Other Compatible Apps: [e.g., "WheelLog", "EUC World"]

Bluetooth Name: [What the EUC shows up as in Bluetooth scan]
MAC Address: [Your EUC's MAC - optional if you want privacy]

Purchase Date: [When you got it]
Purchase Location: [Country/Region]
```

### Share Your Data

**Option 1: GitHub Issue (Recommended)**

1. Go to the project's GitHub issues page
2. Create a new issue with title: "Data Capture: [Brand] [Model]"
3. Attach your data package as a ZIP file
4. Or upload to a file sharing service and paste the link

**Option 2: GitHub Pull Request (Advanced)**

If you're comfortable with Git:

1. Fork the repository
2. Create a branch: `data-capture-[brand]-[model]`
3. Add your captures to a new folder: `test_data/captures/[brand]_[model]/`
4. Commit and create a pull request

**Option 3: Email**

If you prefer privacy:
- Email your data package to the project maintainer
- Check the project README for contact information

### What Happens Next

1. **Initial Review** - A maintainer will review your captures to ensure quality
2. **Protocol Analysis** - Your data will be analyzed (see Data Analysis Guide)
3. **Decoder Implementation** - Code will be written to support your model
4. **Testing** - You may be asked to test the implementation
5. **Release** - Your EUC model will be added to the supported list!

## Tips for High-Quality Captures

### 1. Stable Connection
- Keep your computer within 5 meters of the EUC
- Avoid interference from other Bluetooth devices
- Close other apps that might connect to the EUC (WheelLog, manufacturer app, etc.)

### 2. Multiple Battery Levels
- Captures at different battery levels help calibrate percentage calculations
- Try to capture at: 25%, 50%, 75%, and 100%

### 3. Document Everything
- Note the exact battery percentage during each capture (from the EUC's app)
- Note if the EUC was recently charged or used
- Note any unusual behavior or warnings

### 4. Charging Captures
- Let the charger stabilize for 30 seconds before starting capture
- Longer charging captures (10-15 minutes) are better
- Note the battery percentage at start and end of capture

### 5. Clean Data
- Don't move the EUC during "idle" captures
- Don't disconnect/reconnect during a capture
- Let captures complete naturally (avoid stopping early unless necessary)

### 6. Safety First
- Never capture while riding unless you have a safe setup
- Don't modify your EUC's firmware just for captures
- Follow manufacturer safety guidelines

## Troubleshooting

### Problem: "Device not found during scan"

**Solutions:**
- Make sure EUC is powered on
- Move closer to the EUC
- Disable other Bluetooth devices temporarily
- Restart Bluetooth on your computer
- On Linux: `sudo systemctl restart bluetooth`

### Problem: "Failed to connect"

**Solutions:**
- Close the manufacturer's app if it's running
- Close WheelLog or other EUC apps
- Make sure no other computer/phone is connected
- Power cycle the EUC (turn off and on)
- Try again after 10-20 seconds

### Problem: "No packets captured" or "total_packets: 0"

**Solutions:**
- Make sure you can connect to the EUC manually first
- Try a longer capture duration (5 minutes)
- Check if your EUC requires a special pairing code
- Some EUCs might auto-disconnect when idle - try capturing while charging

### Problem: "Protocol not detected" or "decoded_packets: 0"

**This is actually okay!** It just means your EUC uses a protocol that isn't implemented yet. This is exactly why we need your data. The analysis guide will show how to decode it.

### Problem: Capture keeps getting interrupted

**Solutions:**
- Make sure your computer doesn't go to sleep during capture
- Disable Bluetooth power saving on your computer
- Use a USB Bluetooth adapter instead of built-in Bluetooth
- Try a shorter initial capture (30 seconds) to test

### Problem: "Permission denied" on Linux

**Solutions:**
```bash
# Add your user to bluetooth group
sudo usermod -a -G bluetooth $USER

# Or run with sudo (not recommended)
sudo python euc_logger.py capture ...
```

### Problem: Can't install bleak

**Solutions:**
```bash
# Update pip first
pip install --upgrade pip

# Install bleak with verbose output
pip install bleak --verbose

# On Linux, you might need system packages:
sudo apt-get install python3-dev libbluetooth-dev

# On macOS with M1/M2:
arch -x86_64 pip install bleak
```

## Example Session

Here's a complete example of capturing data from a KingSong S18:

```bash
# 1. Scan for the EUC
$ python euc_logger.py scan
Scanning for EUC devices (10 seconds)...

Found 1 EUC device(s):

Device: KS-S18
  MAC Address: AA:BB:CC:DD:EE:FF
  RSSI: -45 dBm
  Detected Brand: kingsong
  Service UUIDs: 0000ffe0-0000-1000-8000-00805f9b34fb

# 2. Capture idle state at 85% battery
$ python euc_logger.py capture AA:BB:CC:DD:EE:FF \
    --brand kingsong \
    --model "KS-S18" \
    --duration 60 \
    --auto-detect \
    --output euc_captures/ks_s18_idle_85pct.json

2026-02-01 13:00:00 - INFO - Scanning for device AA:BB:CC:DD:EE:FF...
2026-02-01 13:00:05 - INFO - Found device: KS-S18 (AA:BB:CC:DD:EE:FF)
2026-02-01 13:00:05 - INFO - Connecting to AA:BB:CC:DD:EE:FF...
2026-02-01 13:00:06 - INFO - Connected successfully
2026-02-01 13:00:06 - INFO - Using notification characteristic: 0000ffe1-...
2026-02-01 13:00:06 - INFO - Auto-detected protocol: kingsong
2026-02-01 13:00:06 - INFO - Starting data capture for 60 seconds...
2026-02-01 13:01:06 - INFO - Capture complete. Received 120 packets
2026-02-01 13:01:06 - INFO - Successfully decoded 120 packets
2026-02-01 13:01:06 - INFO - Saved capture to euc_captures/ks_s18_idle_85pct.json
2026-02-01 13:01:06 - INFO - Disconnected

# 3. Start charging and capture
$ python euc_logger.py capture AA:BB:CC:DD:EE:FF \
    --brand kingsong \
    --model "KS-S18" \
    --duration 300 \
    --auto-detect \
    --output euc_captures/ks_s18_charging.json

[Similar output, 300 seconds of capture]

# 4. List all captures
$ python euc_logger.py list

Found 2 capture(s):

File: ks_s18_charging.json
  Brand: kingsong
  Model: KS-S18
  MAC: AA:BB:CC:DD:EE:FF
  Captured: 2026-02-01T13:02:00
  Duration: 300.0s
  Packets: 600 (decoded: 600)

File: ks_s18_idle_85pct.json
  Brand: kingsong
  Model: KS-S18
  MAC: AA:BB:CC:DD:EE:FF
  Captured: 2026-02-01T13:00:06
  Duration: 60.0s
  Packets: 120 (decoded: 120)

# 5. View a capture
$ python euc_logger.py view euc_captures/ks_s18_idle_85pct.json

[Shows metadata and packet details]
```

## Next Steps

Once you have good captures:

1. Review them with `python euc_logger.py view`
2. Package them according to the guidelines above
3. Share them via GitHub issue or PR
4. Read the **Data Analysis Guide** if you want to help decode the protocol
5. Wait for feedback from maintainers

Thank you for contributing to the EUC community! Your data helps everyone.

---

**Questions?** Open an issue on GitHub or check the Discussions section.
