# EUC Data Analysis Guide

This guide explains how to analyze captured EUC BLE data to reverse engineer the protocol and extract meaningful attributes like voltage, speed, battery percentage, etc.

## Table of Contents

- [Overview](#overview)
- [Understanding BLE Packet Structure](#understanding-ble-packet-structure)
- [Analysis Workflow](#analysis-workflow)
- [Step 1: Initial Analysis](#step-1-initial-analysis)
- [Step 2: Identify the Protocol Header](#step-2-identify-the-protocol-header)
- [Step 3: Understand Packet Structure](#step-3-understand-packet-structure)
- [Step 4: Find Data Fields](#step-4-find-data-fields)
- [Step 5: Decode Data Types](#step-5-decode-data-types)
- [Step 6: Validate Your Findings](#step-6-validate-your-findings)
- [Common Patterns](#common-patterns)
- [Example Analysis](#example-analysis)

## Overview

### What You'll Learn

By the end of this guide, you'll be able to:
- Identify protocol headers and packet structure
- Locate specific data fields (voltage, speed, temperature, etc.)
- Determine data types and scaling factors
- Calculate battery percentage from voltage
- Detect charging status
- Validate your findings

### Tools We'll Use

- `euc_analyzer.py` - Automated analysis tool
- `euc_logger.py` - For viewing captures
- Calculator or Python interactive mode
- Spreadsheet software (optional, for tracking findings)

## Understanding BLE Packet Structure

### What is a BLE Packet?

A BLE notification packet is a sequence of bytes sent from your EUC to your device. Each byte is a value from 0-255 (0x00-0xFF in hexadecimal).

Example packet in hex:
```
DC 5A 5C 24 18 E4 00 00 00 00 00 00 ...
```

### Common Packet Components

Most EUC protocols have these components:

1. **Header** - Fixed bytes that identify the start of a packet (e.g., `DC 5A 5C`)
2. **Length** - Byte(s) indicating total packet size
3. **Data Fields** - The actual information (voltage, speed, etc.)
4. **Checksum/CRC** - Validation bytes (optional)
5. **Footer** - Fixed bytes marking the end (e.g., `5A 5A 5A 5A`)

### Data Types

Common ways data is encoded:

| Type | Description | Example |
|------|-------------|---------|
| **uint8** | Unsigned 8-bit (0-255) | Temperature offset |
| **uint16** | Unsigned 16-bit (0-65535) | Voltage * 100 |
| **int16** | Signed 16-bit (-32768-32767) | Speed (can be negative) |
| **uint32** | Unsigned 32-bit | Distance in meters |
| **Flags** | Individual bits represent on/off states | Charging status |

### Endianness

**Big Endian** (most common): Higher byte first
- Example: `18 E4` = 0x18E4 = 6372

**Little Endian**: Lower byte first
- Example: `E4 18` = 0x18E4 = 6372

Most EUCs use **Big Endian**.

## Analysis Workflow

```
1. Initial Analysis
   ↓
2. Identify Header
   ↓
3. Determine Packet Structure
   ↓
4. Find Static vs Variable Bytes
   ↓
5. Correlate with Known Values
   ↓
6. Decode Each Field
   ↓
7. Validate Findings
   ↓
8. Implement Decoder
```

## Step 1: Initial Analysis

### Run the Analyzer

Start with the automated analysis tool:

```bash
python euc_analyzer.py analyze euc_captures/idle.json
```

This will show:
- Total packets captured
- Packet length distribution
- Most common headers
- Protocol detection results
- Byte position analysis

### What to Look For

**✅ Good Signs:**
- Fixed packet length (all packets are the same size)
- Clear header pattern detected
- Protocol is recognized
- Many packets decoded

**⚠️ Needs Work:**
- Variable packet lengths (requires more complex framing)
- No clear header pattern
- Protocol not recognized
- No packets decoded

### Example Output

```
PACKET PATTERNS:
  Total packets: 120
  Unique packet lengths: 1
  Most common lengths:
    36 bytes: 120 packets (100.0%)

HEADER ANALYSIS:
  Most common 2-byte headers:
    0xdc5a: 120 packets (100.0%)
  
  Most common 3-byte headers:
    0xdc5a5c: 120 packets (100.0%)
  
  Protocol detection:
    ✓ Veteran/Leaperkim protocol detected (DC 5A 5C)
```

**Analysis:** This shows a fixed 36-byte protocol with consistent `DC 5A 5C` header. Clean data!

## Step 2: Identify the Protocol Header

### Find the Header Bytes

Look at the "HEADER ANALYSIS" section. The header is the fixed bytes at the start of every packet.

**Common EUC Headers:**

| Brand | Header | Bytes |
|-------|--------|-------|
| Veteran/Leaperkim | `DC 5A 5C` | 3 bytes |
| KingSong | `AA 55` | 2 bytes |
| Gotway/Begode | `55 AA` | 2 bytes |
| InMotion V1 | `AA AA` | 2 bytes |
| InMotion V2 | `DC 5A` | 2 bytes |
| Ninebot | `55 AA` | 2 bytes |
| Ninebot Z | `5A A5` | 2 bytes |

### Manual Verification

View a few raw packets:

```bash
python euc_logger.py view euc_captures/idle.json
```

Look at the first few bytes of each packet. They should be identical.

Example:
```
Packet 1: DC 5A 5C 24 18 E4 00 00 ...
Packet 2: DC 5A 5C 24 18 E5 00 00 ...
Packet 3: DC 5A 5C 24 18 E6 00 00 ...
          ^^^^^^^^^ - Same header!
```

## Step 3: Understand Packet Structure

### Fixed vs Variable Length

**Fixed Length** (easier):
- All packets are the same size
- Structure is predictable
- Example: KingSong (20 bytes), Gotway (20 bytes), Veteran (36+ bytes)

**Variable Length** (harder):
- Packets can be different sizes
- Usually has a length byte early in the packet
- Example: InMotion V2 (length byte at position 3)

### Find the Length Byte

For variable-length protocols, find the byte that indicates packet length:

```bash
python euc_analyzer.py analyze euc_captures/idle.json
```

Look for a byte position that changes in correlation with packet size.

### Map the Structure

Create a basic map of your protocol:

```
Byte 0-2:    Header (DC 5A 5C)
Byte 3:      Length (0x24 = 36 bytes)
Byte 4-5:    [Unknown - analyze]
Byte 6-7:    [Unknown - analyze]
...
```

## Step 4: Find Data Fields

### Use Byte Position Analysis

The analyzer shows which bytes are static (constant) vs dynamic (changing):

```
BYTE POSITION ANALYSIS:
  Static bytes (constant across all packets):
    Byte   0: 0xDC
    Byte   1: 0x5A
    Byte   2: 0x5C
    Byte  22: 0x00
    Byte  30: 0x00
  
  Highly variable bytes (likely data fields):
    Byte   4: 255 unique values, range 0x00-0xFF, variance 156.3
    Byte   5: 248 unique values, range 0x00-0xFF, variance 142.7
    Byte   6: 189 unique values, range 0x00-0xFF, variance 98.2
```

**Analysis:**
- Bytes 0-2: Header (expected)
- Bytes 4-7: High variance = probably voltage, speed, or other continuously changing values
- Bytes 22, 30: Static = probably type indicators or checksums

### Compare Idle vs Charging

Compare two captures to identify specific fields:

```bash
python euc_analyzer.py compare euc_captures/idle.json euc_captures/charging.json
```

**What changes during charging:**
- ✅ Voltage increases
- ✅ Battery percentage increases
- ✅ Charging flag changes from 0 to 1
- ✅ Current becomes negative
- ❌ Speed stays 0 (not moving)
- ❌ Distance stays constant

Use this to narrow down which bytes represent which fields.

## Step 5: Decode Data Fields

### Strategy: Start with Voltage

Voltage is usually the easiest to find because:
1. It's a large number (e.g., 6372 for 63.72V)
2. Changes slowly and predictably
3. Usually encoded as uint16 (2 bytes)

### Find the Voltage Bytes

Look for a 2-byte field that:
- Has a value around your known voltage * 100
- Changes slowly between packets
- Increases during charging

**Example:**

Your EUC is at 85% battery on a 100.8V (24S) system.
- Expected voltage: ~94V
- Expected encoded value: 9400

Look for bytes that could be `0x24 0xB8` (9400 in hex, big endian):

```
Packet: DC 5A 5C 24 24 B8 00 00 ...
                   ^^^^^ - Possibly voltage!
```

### Decode the Value

To decode a uint16 big-endian value from hex bytes:

```python
# Bytes at position 4-5: 24 B8
byte1 = 0x24
byte2 = 0xB8

# Big endian: (byte1 << 8) | byte2
value = (byte1 << 8) | byte2  # = 9400

# Apply scaling
voltage = value / 100.0  # = 94.0V
```

### Find Other Fields

Use similar logic for other fields:

#### Speed
- Usually int16 (can be negative for reverse)
- Often needs scaling (* 3.6 or * 10 / 1000)
- Should be 0 in idle captures

#### Current
- Usually int16 (negative = charging, positive = discharging)
- Scaling factor varies (common: / 100 or * 10 / 1000)

#### Temperature
- Can be uint16 or use MPU6050 formula
- MPU6050: `temp_celsius = raw / 340.0 + 36.53`

#### Distance
- Usually uint32 (4 bytes)
- Often in meters, divide by 1000 for km
- Watch for "reversed big-endian" format (high word at offset+2)

#### Battery Percentage
- Might be directly encoded as uint8 (0-100)
- Or calculated from voltage

#### Charging Status
- Often a single bit or byte
- Compare idle vs charging captures

### Common Scaling Factors

| Field | Common Encodings |
|-------|------------------|
| Voltage | `raw / 100` |
| Speed | `raw * 3.6` or `(raw * 10) / 1000` |
| Current | `raw / 100` or `(raw * 10) / 1000` |
| Temperature | `raw / 100` or `raw / 340 + 36.53` |
| Distance | `raw / 1000` (meters to km) |
| PWM | `raw / 10` |
| Angle | `raw / 100` |

## Step 6: Validate Your Findings

### Cross-Reference with Official App

Install your EUC's official app (or WheelLog) and compare values:

1. Open the official app
2. View real-time data
3. Capture BLE data simultaneously
4. Compare decoded values with app values

### Test Edge Cases

Test your decoding with:
- ✅ Low battery (20-30%)
- ✅ High battery (90-100%)
- ✅ Charging
- ✅ Not charging
- ✅ Moving (if safe)
- ✅ Cold temperature
- ✅ Hot temperature

### Calculate Battery Percentage

Most EUCs don't directly encode battery percentage. You need to calculate it from voltage:

```python
def calculate_battery_percent(voltage, max_voltage):
    """
    Calculate battery percentage from voltage.
    
    Args:
        voltage: Current voltage (e.g., 94.0)
        max_voltage: Maximum voltage (e.g., 100.8 for 24S)
    """
    # Simple linear (not very accurate):
    min_voltage = max_voltage * 0.75  # ~3.1V per cell
    percent = ((voltage - min_voltage) / (max_voltage - min_voltage)) * 100
    return max(0, min(100, percent))

# Better approach: Use non-linear Li-ion curve
# (See custom_components/euc_charging/decoders.py for full implementation)
```

## Common Patterns

### Pattern 1: Fixed 20-byte packets with footer

**Structure:**
```
Bytes 0-1:   Header (AA 55 or 55 AA)
Bytes 2-3:   Voltage (uint16 BE)
Bytes 4-5:   Speed (int16 BE)
Bytes 6-9:   Distance (uint32 BE)
Bytes 10-11: Current (int16 BE)
Bytes 12-13: Temperature (uint16 BE)
Bytes 14-15: PWM (int16 BE)
Bytes 16-17: Reserved
Byte 18:     Frame type
Byte 19:     Reserved
Bytes 20-23: Footer (5A 5A 5A 5A)
```

**Brands:** KingSong, Gotway/Begode

### Pattern 2: Variable-length with 3-byte header

**Structure:**
```
Bytes 0-2:   Header (DC 5A 5C)
Byte 3:      Length
Bytes 4-N:   Data (varies)
```

**Brands:** Veteran/Leaperkim, InMotion V2

### Pattern 3: CAN-style frames

**Structure:**
```
Bytes 0-1:   Header (AA AA)
Bytes 0-3:   CAN ID (32-bit)
Bytes 4-11:  Data (8 bytes)
Byte 12:     Length
Byte 13:     Channel
Bytes 14-15: Checksum
Bytes 16-17: Footer (55 55)
```

**Brands:** InMotion V1

## Example Analysis

Let's walk through a complete analysis of a fictional "NewBrand X1" EUC.

### Capture Info
- Brand: NewBrand
- Model: X1
- Battery: 20S (84V max)
- Current battery: 75% (approximately 78V)

### Step 1: Run Analysis

```bash
$ python euc_analyzer.py analyze captures/newbrand_idle.json

PACKET PATTERNS:
  Total packets: 150
  Unique packet lengths: 1
  Most common lengths:
    24 bytes: 150 packets (100.0%)

HEADER ANALYSIS:
  Most common 2-byte headers:
    0xab55: 150 packets (100.0%)
  
  Protocol detection:
    ✗ No known protocol detected
```

**Finding:** 24-byte fixed-length protocol, header is `AB 55`, unknown protocol.

### Step 2: View Raw Packets

```bash
$ python euc_logger.py view captures/newbrand_idle.json

Packet 1:
  Hex: ab551e8200000000000000009a03e81027006400000000
  
Packet 2:
  Hex: ab551e8300000000000000009a03e81027006400000000
```

Let's break down packet 1:
```
AB 55 - Header
1E 82 - ? (7810 decimal)
00 00 - ? (0)
00 00 - ? (0)
00 00 - ? (0)
00 00 - ? (0)
9A 03 - ? (39427 decimal)
E8 10 - ? (59408 decimal)
27 00 - ? (10240 decimal - or 0x0027 = 39 in LE)
64 00 - ? (25600 decimal - or 0x0064 = 100 in LE)
00 00 - ? (0)
00 00 - ? (0)
```

### Step 3: Hypothesis - Find Voltage

Battery is at ~78V, so we expect a value around 7800.

Look for: `0x1E 0x82` = 7810 decimal

**Hypothesis:** Bytes 2-3 are voltage * 100

```python
voltage = 7810 / 100  # = 78.10V ✓
```

### Step 4: Compare Charging Capture

```bash
$ python euc_analyzer.py compare captures/newbrand_idle.json captures/newbrand_charging.json

DECODED FIELD COMPARISON:
  [No decoded fields available - analyzing raw packets]
```

Manually compare first and last packets of charging capture:

**First packet (78.10V):**
```
AB 55 1E 82 00 00 00 00 00 00 00 00 9A 03 E8 10 27 00 64 00 00 00 00 00
```

**Last packet (78.65V, after 5 min charging):**
```
AB 55 1E B7 00 00 00 00 00 00 00 00 9A 03 E8 10 27 00 65 00 01 00 00 00
```

**Changes:**
- Bytes 2-3: `1E 82` → `1E B7` (7810 → 7863, voltage increased ✓)
- Byte 19: `64` → `65` (100 → 101, possibly battery%?)
- Byte 21: `00` → `01` (possibly charging flag?)

### Step 5: Decode Fields

Based on analysis:

```python
def decode_newbrand_x1(data):
    # Header check
    if data[0] != 0xAB or data[1] != 0x55:
        return None
    
    # Voltage (bytes 2-3, big endian)
    voltage_raw = (data[2] << 8) | data[3]
    voltage = voltage_raw / 100.0
    
    # Unknown fields at 4-11 (all zeros in captures)
    
    # Bytes 12-13: Maybe speed? (0x9A03 = 39427)
    # Try different interpretations:
    # - 39427 / 1000 = 39.4 (too high for stationary)
    # - As signed int16: still positive
    # - Maybe odometer? Need more data
    
    # Bytes 14-15: 0xE810 = 59408
    # Also unclear, might be settings
    
    # Byte 19: Looks like battery percentage (64 = 100d = 100%)
    # Wait, that doesn't match 75%...
    # Maybe it's something else?
    
    # Byte 21: Charging flag (0 = not charging, 1 = charging)
    is_charging = data[21] == 0x01
    
    return {
        'voltage': voltage,
        'is_charging': is_charging,
        # More fields TBD
    }
```

### Step 6: Test More Captures

Need additional captures to figure out:
- What are bytes 12-13? (captured at different speeds)
- What are bytes 14-15? (captured at different temperatures)
- What is byte 19? (captured at different battery levels)

### Step 7: Implement Decoder

Once all fields are understood, implement in `decoders.py`:

```python
class NewBrandDecoder(EucDecoder):
    """Decoder for NewBrand X1 wheels."""
    
    # ... implementation ...
```

## Next Steps

After completing your analysis:

1. **Document Your Findings** - Create a document with:
   - Packet structure diagram
   - Field offsets and data types
   - Scaling factors
   - Known vs unknown bytes
   
2. **Share Your Analysis** - Post in GitHub issue or discussion:
   - Attach your analysis document
   - Include capture files
   - Ask for help with unknown fields
   
3. **Implement Decoder** - Follow CONTRIBUTING.md to:
   - Add decoder class
   - Add protocol detection
   - Test with your captures
   
4. **Submit PR** - Share your work with the community

## Tools and Resources

### Python Interactive Mode

Test decoding quickly:

```python
# Open Python
>>> data = bytes.fromhex("ab551e8200000000")
>>> voltage = ((data[2] << 8) | data[3]) / 100
>>> print(voltage)
78.1
```

### Hex to Decimal Converter

Online tools:
- https://www.rapidtables.com/convert/number/hex-to-decimal.html

Or in Python:
```python
>>> 0x1E82
7810
```

### Spreadsheet Analysis

Create a spreadsheet to track packets:

| Packet # | Byte 2-3 (Voltage) | Byte 4-5 (Speed?) | Byte 19 (Battery?) | Notes |
|----------|-------------------|-------------------|-------------------|-------|
| 1 | 0x1E82 (78.10V) | 0x0000 | 0x64 (100) | Idle |
| 2 | 0x1E83 (78.11V) | 0x0000 | 0x64 (100) | Idle |
| ... | ... | ... | ... | ... |

### WheelLog Source Code

Great reference for protocol details:
- https://github.com/Wheellog/Wheellog.Android
- Look in `app/src/main/java/com/cooper/wheellog/utils/`

## Getting Help

If you're stuck:

1. **Post in GitHub Discussions** - Share your analysis and captures
2. **Open an Issue** - Request help with specific model
3. **Join Community** - Connect with other EUC developers

Remember: Protocol reverse engineering takes patience. Even partial progress is valuable!

---

**Good luck with your analysis!**
