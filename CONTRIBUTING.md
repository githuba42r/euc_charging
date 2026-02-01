# Contributing to EUC Charging Integration

Thank you for your interest in contributing to the EUC Charging integration! This guide will help you add support for new EUC models and brands.

## Table of Contents

- [Quick Start](#quick-start)
- [Capturing Data from Your EUC](#capturing-data-from-your-euc)
- [Analyzing Captured Data](#analyzing-captured-data)
- [Adding Support for a New Model](#adding-support-for-a-new-model)
- [Testing Your Changes](#testing-your-changes)
- [Submitting a Pull Request](#submitting-a-pull-request)

## Quick Start

To contribute support for a new EUC model, you'll need:

1. **Your EUC** - Make sure it's charged and powered on
2. **A computer with Bluetooth** - For capturing BLE data
3. **Python 3.9+** - For running the capture and analysis tools
4. **Basic Python knowledge** - For implementing the decoder (we'll help!)

## Capturing Data from Your EUC

### Step 1: Install Dependencies

```bash
# Install required Python packages
pip install bleak

# Or use the requirements.txt
pip install -r requirements.txt
```

### Step 2: Scan for Your EUC

First, find your EUC's Bluetooth MAC address:

```bash
python euc_logger.py scan
```

This will show all nearby EUC devices. Note your EUC's MAC address (format: `AA:BB:CC:DD:EE:FF`).

### Step 3: Capture BLE Data

Capture data from your EUC while it's in different states:

#### Capture 1: Idle (Not Charging)

```bash
python euc_logger.py capture AA:BB:CC:DD:EE:FF \
  --brand <your_brand> \
  --model "Your Model Name" \
  --duration 60 \
  --auto-detect
```

Replace:
- `AA:BB:CC:DD:EE:FF` with your EUC's MAC address
- `<your_brand>` with one of: `kingsong`, `gotway`, `veteran`, `inmotion`, `ninebot`
- `"Your Model Name"` with your specific model (e.g., "V12 HT", "RS HT", "Sherman Max")

#### Capture 2: Charging

Plug in your EUC charger and capture data while it's charging:

```bash
python euc_logger.py capture AA:BB:CC:DD:EE:FF \
  --brand <your_brand> \
  --model "Your Model Name" \
  --duration 300 \
  --auto-detect
```

We recommend capturing for at least 5 minutes (300 seconds) while charging to see how the battery percentage and voltage change.

#### Capture 3: Moving (Optional)

If you want to capture data while riding (safely!):

```bash
python euc_logger.py capture AA:BB:CC:DD:EE:FF \
  --brand <your_brand> \
  --model "Your Model Name" \
  --duration 60 \
  --auto-detect
```

**Safety note:** Have someone else run this command while you ride in a safe, controlled environment, or mount your phone/laptop on the EUC.

### Step 4: List Your Captures

View all captured data:

```bash
python euc_logger.py list
```

Captured files are saved in the `euc_captures/` directory with timestamps.

## Analyzing Captured Data

### View Captured Data

To view the contents of a capture file:

```bash
python euc_logger.py view euc_captures/20260201_120345_veteran_sherman_s.json
```

### Analyze Packet Patterns

Use the analyzer tool to understand the protocol:

```bash
python euc_analyzer.py analyze euc_captures/your_capture.json
```

This will show:
- Packet header patterns
- Packet lengths and structures
- Byte positions that change (likely data fields)
- Byte positions that are constant (likely headers/footers)

### Compare Captures

Compare data from different states (e.g., idle vs charging):

```bash
python euc_analyzer.py compare euc_captures/idle.json euc_captures/charging.json
```

This helps identify which bytes represent battery percentage, voltage, charging status, etc.

### Extract Patterns

Find repeating sequences in the data:

```bash
python euc_analyzer.py patterns euc_captures/your_capture.json
```

## Adding Support for a New Model

### If Your Brand is Already Supported

If your brand (KingSong, Gotway, Veteran) is already in the codebase but your specific model isn't detected:

1. **Check the captured data** - Does the protocol auto-detect correctly?
2. **Update model detection** - Add your model to the appropriate decoder in `custom_components/euc_charging/decoders.py`
3. **Update voltage configuration** - If your model has a different battery configuration (e.g., 30S instead of 24S)

### If Your Brand is NOT Supported

If your EUC brand isn't supported yet, you'll need to implement a decoder. Here's the process:

#### 1. Analyze the Protocol

Use the analyzer tool to understand:
- **Header bytes**: What bytes start each packet?
- **Packet structure**: Fixed length or variable?
- **Data fields**: Which byte positions contain voltage, speed, etc.?

#### 2. Create a Decoder Class

Add a new decoder class in `custom_components/euc_charging/decoders.py`:

```python
class YourBrandDecoder(EucDecoder):
    """Decoder for YourBrand wheels."""

    def __init__(self) -> None:
        super().__init__()
        self.unpacker = YourBrandUnpacker()  # If needed
        self.system_voltage = 84.0  # Default voltage

    @property
    def brand(self) -> WheelBrand:
        return WheelBrand.YOURBRAND

    def decode(self, data: bytes) -> Optional[dict[str, Any]]:
        """Decode BLE notification data."""
        # Implement packet decoding here
        pass
```

#### 3. Implement Packet Unpacking

If packets can be fragmented across multiple BLE notifications, implement an unpacker:

```python
class YourBrandUnpacker:
    """Unpacker for YourBrand protocol."""

    def __init__(self) -> None:
        self.buffer = bytearray()

    def add_data(self, data: bytes) -> list[bytes]:
        """Add data and return complete frames."""
        # Implement frame assembly
        pass
```

#### 4. Parse Data Fields

In your decoder's `decode()` method, extract the data fields:

```python
def _decode_frame(self, buff: bytes) -> Optional[dict[str, Any]]:
    """Decode a complete frame."""
    try:
        # Example: Parse voltage from bytes 2-3 (big-endian)
        voltage = struct.unpack(">H", buff[2:4])[0] / 100.0
        
        # Example: Parse speed from bytes 4-5 (signed)
        speed = struct.unpack(">h", buff[4:6])[0] * 3.6
        
        # ... parse other fields
        
        battery_percent = self.calculate_battery_percent(voltage, self.system_voltage)
        
        return {
            "voltage": voltage,
            "speed": speed,
            "battery_percent": battery_percent,
            # ... other fields
        }
    except (struct.error, IndexError) as e:
        _LOGGER.debug(f"Decode error: {e}")
        return None
```

#### 5. Update Protocol Detection

Add protocol detection in `get_decoder_by_data()`:

```python
def get_decoder_by_data(data: bytes) -> Optional[EucDecoder]:
    # ... existing code ...
    
    # Check for YourBrand (XX YY header)
    if data[0] == 0xXX and data[1] == 0xYY:
        _LOGGER.debug("Detected YourBrand protocol")
        return YourBrandDecoder()
```

#### 6. Update Constants

Add your brand to `custom_components/euc_charging/const.py`:

```python
# Add UUIDs
YOURBRAND_SERVICE_UUID = "your-service-uuid"
YOURBRAND_READ_UUID = "your-read-uuid"

# Add to WheelBrand enum
class WheelBrand(Enum):
    # ... existing brands ...
    YOURBRAND = "yourbrand"

# Add device name patterns
BRAND_DEVICE_NAMES = {
    # ... existing brands ...
    WheelBrand.YOURBRAND: ["YourBrand", "Model1", "Model2"],
}
```

## Testing Your Changes

### 1. Test with Captured Data

Create a simple test script:

```python
from custom_components.euc_charging.decoders import get_decoder_by_data
import json

# Load your capture
with open("euc_captures/your_capture.json") as f:
    data = json.load(f)

# Test decoder
decoder = None
for packet in data["raw_packets"]:
    data_bytes = bytes(packet["data_bytes"])
    
    if decoder is None:
        decoder = get_decoder_by_data(data_bytes)
        if decoder:
            print(f"Detected: {decoder.name}")
    
    if decoder:
        result = decoder.decode(data_bytes)
        if result:
            print(f"Decoded: {result}")
            break
```

### 2. Test with Home Assistant

1. Copy your updated integration to Home Assistant's custom_components directory
2. Restart Home Assistant
3. Try to add your EUC through the integration UI
4. Check the logs for any errors

## Submitting a Pull Request

When you're ready to contribute your changes:

### 1. Prepare Your Submission

- Include sample capture files (at least one idle and one charging)
- Add a comment in your decoder explaining the protocol structure
- Update this CONTRIBUTING.md if you learned something that would help others

### 2. Create a Pull Request

1. Fork the repository
2. Create a branch with a descriptive name: `add-support-yourbrand-model`
3. Commit your changes with clear commit messages
4. Push to your fork
5. Create a Pull Request with:
   - Description of what brand/model you're adding
   - Link to manufacturer's website or documentation (if available)
   - Battery configuration (cell count, voltage)
   - Any special notes about the protocol

### Example PR Description

```markdown
## Add support for YourBrand Model X

This PR adds support for YourBrand Model X electric unicycles.

### Specifications
- **Brand**: YourBrand
- **Model**: Model X
- **Battery**: 30S (126V nominal)
- **Capacity**: 2700Wh
- **BLE Service UUID**: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

### Protocol Details
- Fixed 20-byte packets
- Header: `0xAA 0xBB`
- Voltage at bytes 2-3 (big-endian, divide by 100)
- Speed at bytes 4-5 (signed, multiply by 3.6)
- Charging status at byte 18

### Testing
Tested with:
- Idle state (battery 85%)
- Charging state (5 minute capture)
- Riding (short test in parking lot)

All sensors reporting correctly in Home Assistant.
```

## Getting Help

If you need help:

1. **Open an issue** - Describe your EUC model and what you've tried
2. **Share capture files** - Upload your JSON captures (they don't contain personal info)
3. **Ask questions** - We're here to help!

## Code Style

- Follow PEP 8 Python style guidelines
- Add type hints to function signatures
- Include docstrings for classes and public methods
- Use meaningful variable names
- Add comments for complex protocol logic

## Additional Resources

- [WheelLog Android App](https://github.com/Wheellog/Wheellog.Android) - Reference implementation for many protocols
- [Bleak Documentation](https://bleak.readthedocs.io/) - Python BLE library
- [Home Assistant Developer Docs](https://developers.home-assistant.io/) - For integration development

## Thank You!

Your contributions help the entire EUC community. Every new model you add makes this integration more useful for everyone!
