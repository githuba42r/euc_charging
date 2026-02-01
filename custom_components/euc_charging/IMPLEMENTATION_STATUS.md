# Implementation Status: All EUC Models

## ✅ Fully Implemented (Ready to Use)

### Veteran / Leaperkim
- **Status**: ✅ Complete
- **Models**: Sherman, Sherman S, Abrams, Patton, Patton S, Lynx, Sherman L, Oryx, Nosfet Apex, Nosfet Aero
- **Features**: Full telemetry, automatic model detection, all battery configurations
- **Protocol**: Passive read-only (notifications)

### KingSong  
- **Status**: ✅ Complete
- **Models**: All KingSong models (KS-14, KS-16, KS-18, KS-S series, etc.)
- **Features**: Voltage, speed, current, temperature, distance, auto voltage detection (16S-42S)
- **Protocol**: Passive read-only (notifications)

### Gotway / Begode
- **Status**: ✅ Complete
- **Models**: All Gotway/Begode models (MCM, Monster, MSX, Nikola, RS, Master, EX, etc.)
- **Features**: Voltage, speed, current, temperature, distance, PWM, auto voltage detection
- **Protocol**: Passive read-only (notifications)

## 🔄 Requires Active Communication (Additional Work Needed)

The following brands require **bidirectional** BLE communication (write commands + read responses), which requires integration changes to the coordinator layer.

### InMotion V1 Protocol
- **Status**: 🚧 Protocol structure documented, needs coordinator integration
- **Models**: V3, V5/V5F, V8/V8F/V8S, V10/V10F/V10S/V10T, Solowheel Glide 3, R-series
- **Requirements**:
  - Write characteristic for sending commands
  - Keep-alive timer (25ms interval)
  - Password authentication
  - CAN-style message framing with data escaping
  - Checksum validation

**What's Needed:**
1. Update `coordinator.py` to support write operations
2. Implement keep-alive timer
3. Handle CAN message requests/responses  
4. Implement data escaping/unescaping (0xAA, 0x55, 0xA5)

### InMotion V2 Protocol
- **Status**: 🚧 Protocol structure documented, needs coordinator integration
- **Models**: V11, V11Y, V12 HS/HT/PRO/S, V13/V13 PRO, V14, V9
- **Requirements**:
  - Write characteristic for sending commands
  - Keep-alive timer
  - Request/response command pattern
  - Model-specific settings parsing

**What's Needed:**
1. Update `coordinator.py` to support write operations
2. Implement keep-alive timer
3. Handle command requests/responses
4. Model-specific decoders for each V-series

### Ninebot (Standard)
- **Status**: 🚧 Protocol structure documented, needs encryption + coordinator integration  
- **Models**: Ninebot One (C, E, E+, P, A1, S2), Ninebot Mini
- **Requirements**:
  - Write characteristic for sending commands
  - Encryption key exchange (GetKey command)
  - XOR encryption with 16-byte gamma key
  - Keep-alive timer (25ms interval)
  - Checksum validation (XOR 0xFFFF)

**What's Needed:**
1. Update `coordinator.py` to support write operations
2. Implement encryption key exchange
3. Implement XOR encryption/decryption
4. Implement keep-alive timer
5. Handle encrypted command requests/responses

### Ninebot Z
- **Status**: 🚧 Protocol structure documented, needs encryption + coordinator integration
- **Models**: Ninebot Z6, Z8, Z10
- **Requirements**:
  - Write characteristic for sending commands
  - Encryption key exchange (GetKey command)
  - XOR encryption with 16-byte gamma key
  - Keep-alive timer (25ms interval)
  - Checksum validation (XOR 0xFFFF)
  - BMS data parsing

**What's Needed:**
1. Update `coordinator.py` to support write operations  
2. Implement encryption key exchange
3. Implement XOR encryption/decryption
4. Implement keep-alive timer
5. Handle encrypted command requests/responses
6. Parse BMS cell data

## Why These Aren't Implemented Yet

The current integration architecture uses **passive monitoring** - it only listens to BLE notifications from the EUC. This works perfectly for:
- ✅ Veteran/Leaperkim (broadcasts data continuously)
- ✅ KingSong (broadcasts data continuously)
- ✅ Gotway/Begode (broadcasts data continuously)

However, InMotion and Ninebot wheels require **active communication**:
- ❌ They don't broadcast data automatically
- ❌ You must send requests to get data
- ❌ You must maintain a keep-alive connection
- ❌ Some require password authentication
- ❌ Some require encryption key exchange

## Implementation Roadmap

### Phase 1: Coordinator Enhancement (Required for all remaining brands)

**File**: `custom_components/euc_charging/coordinator.py`

**Changes Needed:**
1. Add support for write characteristics
2. Add timer for periodic command sending
3. Add state management for request/response
4. Add encryption support

**Code Pattern:**
```python
class EucDataCoordinator:
    def __init__(self, ...):
        self.write_characteristic = None
        self.keep_alive_timer = None
        self.encryption_key = None
        
    async def _setup_active_protocol(self):
        """Setup write characteristic and keep-alive for active protocols."""
        # Find write characteristic
        # Start keep-alive timer
        # Exchange encryption keys if needed
```

### Phase 2: InMotion V1 Implementation

**File**: `custom_components/euc_charging/decoders.py`

**Key Components:**
- `InMotionCANMessage` class (CAN message framing)
- `InMotionV1Unpacker` class (with data escaping)
- `InMotionDecoder` implementation
- Password authentication
- Keep-alive requests (GetFastInfo, GetSlowInfo)

**Estimated Effort**: 2-3 days

### Phase 3: InMotion V2 Implementation

**File**: `custom_components/euc_charging/decoders.py`

**Key Components:**
- `InMotionV2Protocol` class (command/response)
- `InMotionV2Decoder` implementation
- Model-specific parsing (V11, V12, V13, V14)
- Keep-alive requests

**Estimated Effort**: 2-3 days

### Phase 4: Ninebot Encryption

**File**: `custom_components/euc_charging/encryption.py` (new)

**Key Components:**
- `NinebotEncryption` class
- Key exchange protocol
- XOR encryption/decryption
- Checksum calculation

**Estimated Effort**: 1-2 days

### Phase 5: Ninebot Standard Implementation

**File**: `custom_components/euc_charging/decoders.py`

**Key Components:**
- `NinebotProtocol` class
- `NinebotDecoder` implementation
- Encrypted command/response handling
- Keep-alive requests

**Estimated Effort**: 2-3 days

### Phase 6: Ninebot Z Implementation

**File**: `custom_components/euc_charging/decoders.py`

**Key Components:**
- `NinebotZProtocol` class
- `NinebotZDecoder` implementation
- BMS data parsing
- Encrypted command/response handling

**Estimated Effort**: 2-3 days

## Total Estimated Effort

- **Coordinator Enhancement**: 1-2 days
- **All InMotion + Ninebot**: 9-14 days
- **Testing & Bug Fixes**: 3-5 days
- **Documentation**: 1-2 days

**Total**: ~2-3 weeks of focused development

## Current Recommendation

### Option 1: Community-Driven (Recommended)

Wait for community contributions:
1. Users with InMotion/Ninebot wheels can capture data using the tools
2. Community members can implement their specific brand
3. Maintainers review and merge implementations

**Pros:**
- Actual hardware for testing
- Motivated users with specific needs
- Distributed development effort

**Cons:**
- Slower overall progress
- May not happen without user initiative

### Option 2: Phased Implementation

Implement one brand at a time based on demand:
1. Add coordinator write support (foundational)
2. Start with most requested brand (InMotion V2 for V12/V13?)
3. Validate with community testing
4. Move to next brand

**Pros:**
- Incremental progress
- Can validate architecture early
- Easier to test and debug

**Cons:**
- Requires hardware or captures for testing
- More time investment

### Option 3: Reference Implementation

Create one complete reference implementation (e.g., InMotion V2):
1. Implement coordinator write support
2. Fully implement InMotion V2
3. Document the pattern
4. Let community follow pattern for other brands

**Pros:**
- Establishes pattern for others
- Proves architecture works
- Good documentation

**Cons:**
- Still requires hardware/captures
- One brand may not cover all edge cases

## What Works Right Now

**The integration is production-ready for:**
- ✅ All Veteran/Leaperkim wheels
- ✅ All KingSong wheels
- ✅ All Gotway/Begode wheels

This covers a **significant portion** of the EUC market, especially in the high-performance category.

## How Users Can Help

If you have an InMotion or Ninebot wheel:

### 1. Capture Data
```bash
python euc_logger.py capture MAC_ADDRESS --brand inmotion --model "V12 HT" --duration 300
```

### 2. Use Official App Simultaneously

While capturing, also connect with:
- InMotion app
- Ninebot app
- WheelLog app

This helps understand the request/response pattern.

### 3. Share Captures

Submit captures to the project with:
- Brand and model
- What data the official app shows
- Any issues or observations

### 4. Test Implementations

Once a decoder is implemented, volunteer to test with your physical wheel.

## References

### WheelLog Source Code
The complete protocol implementations are in WheelLog Android:
- [InMotion V1](https://github.com/Wheellog/Wheellog.Android/blob/master/app/src/main/java/com/cooper/wheellog/utils/InMotionAdapter.java)
- [InMotion V2](https://github.com/Wheellog/Wheellog.Android/blob/master/app/src/main/java/com/cooper/wheellog/utils/InmotionAdapterV2.java)
- [Ninebot](https://github.com/Wheellog/Wheellog.Android/blob/master/app/src/main/java/com/cooper/wheellog/utils/NinebotAdapter.java)
- [Ninebot Z](https://github.com/Wheellog/Wheellog.Android/blob/master/app/src/main/java/com/cooper/wheellog/utils/NinebotZAdapter.java)

### Protocol Documentation
See `DATA_ANALYSIS_GUIDE.md` for how to reverse engineer protocols from captured data.

## Questions?

Open an issue on GitHub with:
- What brand/model you have
- Whether you can test implementations
- Whether you can contribute code
- What features are most important to you

---

**Bottom Line**: The integration currently supports the most popular passive-monitoring wheels (Veteran, KingSong, Gotway). Adding InMotion and Ninebot support requires architectural changes to support active bidirectional communication. This is feasible but requires dedicated development time and ideally access to physical hardware for testing.
