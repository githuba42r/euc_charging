# EUC Protocol Diagrams

This document provides visual representations of the BLE packet structures for all supported EUC brands.

## Table of Contents

- [Veteran/Leaperkim Protocol](#veteranleaperkim-protocol)
- [KingSong Protocol](#kingsong-protocol)
- [Gotway/Begode Protocol](#gotwaybenode-protocol)
- [InMotion V1 Protocol](#inmotion-v1-protocol)
- [InMotion V2 Protocol](#inmotion-v2-protocol)
- [Ninebot Protocol](#ninebot-protocol)
- [Ninebot Z Protocol](#ninebot-z-protocol)

---

## Veteran/Leaperkim Protocol

### Frame Structure

```
┌────────┬────────┬────────┬────────┬─────────────┬──────────────┐
│ Header │ Header │ Header │ Length │  Payload    │   Checksum   │
│  0xDC  │  0x5A  │  0x5C  │  (N)   │  N bytes    │   2 bytes    │
└────────┴────────┴────────┴────────┴─────────────┴──────────────┘
  1 byte   1 byte   1 byte   1 byte    Variable      2 bytes
```

### Live Data Payload (20 bytes)

```
┌──────────┬────────┬─────────────┬──────────────┬─────────┬────────────┬────────┐
│ Voltage  │ Speed  │   Trip      │    Total     │ Current │Temperature │  PWM   │
│  2 bytes │2 bytes │   2 bytes   │   4 bytes    │ 2 bytes │  2 bytes   │2 bytes │
└──────────┴────────┴─────────────┴──────────────┴─────────┴────────────┴────────┘
  *100 V     *100    *1000 km        *1000 km       *100 A     *100 C      *100
```

### Example Packet (Sherman S)

```
DC 5A 5C 14 | B9 01 | 00 00 | 1A 62 | 00 00 FF C6 | 00 00 | 2E 3D | 00 00 | 12 34
Header+Len  | 441   |   0   | 6754  |   65478     |   0   | 11837 |   0   | CS
            | =441% |  0kph | 6.7km |   65.4km    |  0A   | 118°C |   0%  |
            |105.8V |       |       |             |       |       |       |
```

### Model Detection

Model is detected from firmware version field in extended packets:
- `34359750` → Sherman S
- `34360040` → Abrams
- `34360070` → Patton
- Others → Generic Veteran

---

## KingSong Protocol

### Frame Structure

```
┌────────┬────────┬────────┬────────┬────────┬─────────────┬──────────────┐
│ Header │ Header │ Length │  Seq   │  Cmd   │  Payload    │   Checksum   │
│  0xAA  │  0x55  │  (N)   │  Seq#  │  0xA9  │  N-2 bytes  │   2 bytes    │
└────────┴────────┴────────┴────────┴────────┴─────────────┴──────────────┘
  1 byte   1 byte   1 byte   1 byte   1 byte    Variable      2 bytes
```

### Live Data Payload (0xA9 command)

```
┌──────────┬────────┬─────────┬──────────────┬─────────┬────────────┬────────┐
│ Voltage  │ Speed  │  Trip   │    Total     │ Current │Temperature │  Mode  │
│  2 bytes │2 bytes │ 2 bytes │   4 bytes    │ 1 byte  │  1 byte    │1 byte  │
└──────────┴────────┴─────────┴──────────────┴─────────┴────────────┴────────┘
  *100 V     *100    *1000km     *1000 km      *100 A      *100 C     flags
```

### Example Packet (KS-S18)

```
AA 55 14 | 5A | A9 | 14 A0 | 00 00 | 00 C8 | 01 F4 00 00 | 1E | 5A | 00 | 12 34
Header   | Seq| Cmd| 5280  |   0   |  200  |    500      | 30 | 90 | 00 | CS
         |    |    | =52.8V|  0kph | 0.2km |   500km     |0.3A|0.9°|    |
```

### Voltage Detection

Cell configuration is auto-detected from voltage range:
- < 70V → 16S (67.2V)
- 70-90V → 20S (84V)
- 90-110V → 24S (100.8V)
- 110-135V → 30S (126V)

---

## Gotway/Begode Protocol

### Frame Structure

```
┌────────┬────────┬────────┬────────┬─────────────┬──────────────┐
│ Header │ Header │ Header │ Header │  Payload    │   Checksum   │
│  0x55  │  0xAA  │  0xDC  │  0x5A  │  Variable   │   2 bytes    │
└────────┴────────┴────────┴────────┴─────────────┴──────────────┘
  1 byte   1 byte   1 byte   1 byte    Variable      2 bytes
```

### Live Data Payload

```
┌──────────┬────────┬─────────────┬──────────────┬─────────┬────────────┬────────┐
│ Voltage  │ Speed  │   Trip      │    Total     │ Current │Temperature │  PWM   │
│  2 bytes │2 bytes │   4 bytes   │   4 bytes    │ 2 bytes │  2 bytes   │2 bytes │
└──────────┴────────┴─────────────┴──────────────┴─────────┴────────────┴────────┘
  *100 V    *1.14   *1000 km        *1000 km       *100 A     *100 C      *100
          (0.875)
```

### Example Packet (Monster Pro)

```
55 AA DC 5A | 2F 6C | 00 08 | 00 00 00 32 | 00 00 12 34 | 00 00 | 1E 28 | 00 00 | 12 34
Header      | 12140 | 8*0.8 |    50       |   4660      |   0   | 7720  |   0   | CS
            |=121.4V| =22.8 |   0.05km    |   4.66km    |  0A   | 77.2°C|   0%  |
            |       |  kph  |             |             |       |       |       |
```

Note: Speed has a multiplier of 0.875 (7/8) for Gotway wheels.

---

## InMotion V1 Protocol

### Frame Structure (CAN-style)

```
┌────────┬────────┬────────┬─────────────┬──────────────┐
│ Header │ Header │ Length │  Payload    │   Checksum   │
│  0xAA  │  0xAA  │  (N)   │  N bytes    │   2 bytes    │
└────────┴────────┴────────┴─────────────┴──────────────┘
  1 byte   1 byte   1 byte    Variable      2 bytes (sum)

Note: Uses data escaping with 0xA5 byte
```

### Request Packet (Keepalive)

```
┌────────┬────────┬────────┬────────┬─────────────────┬──────────────┐
│  0xAA  │  0xAA  │  0x09  │  0x01  │  [Request Data] │   Checksum   │
└────────┴────────┴────────┴────────┴─────────────────┴──────────────┘
```

### Live Data Response

```
┌──────────┬────────┬─────────────┬──────────────┬─────────┬────────────┐
│ Msg Type │Voltage │   Distance  │    Total     │ Current │Temperature │
│  0x01    │2 bytes │   4 bytes   │   4 bytes    │ 2 bytes │  2 bytes   │
└──────────┴────────┴─────────────┴──────────────┴─────────┴────────────┘
  1 byte    *100 V     *1000 km       *1000 km      *100 A     *100 C
```

### Characteristics

- **Bidirectional**: Requires active request/response
- **Authentication**: May require password on some models
- **Keep-alive**: ~25ms interval
- **Checksum**: Sum of all bytes & 0xFFFF

---

## InMotion V2 Protocol

### Frame Structure

```
┌────────┬────────┬────────┬─────────┬─────────────┬──────────────┐
│ Header │ Header │ Length │ Command │  Payload    │   Checksum   │
│  0xDC  │  0x5A  │  (N)   │  Type   │  N-1 bytes  │   2 bytes    │
└────────┴────────┴────────┴─────────┴─────────────┴──────────────┘
  1 byte   1 byte   1 byte   1 byte     Variable      2 bytes (XOR)
```

### Request Packet (Keepalive)

```
┌────────┬────────┬────────┬────────┬──────────────┐
│  0xDC  │  0x5A  │  0x05  │  0x01  │   Checksum   │
└────────┴────────┴────────┴────────┴──────────────┘
```

### Live Data Response (Command 0x01)

```
┌──────────┬────────┬─────────────┬──────────────┬─────────┬────────────┬──────────┐
│ Voltage  │ Speed  │   Trip      │    Total     │ Current │Temperature │  Model   │
│  2 bytes │2 bytes │   4 bytes   │   4 bytes    │ 2 bytes │  2 bytes   │ 10 bytes │
└──────────┴────────┴─────────────┴──────────────┴─────────┴────────────┴──────────┘
  *100 V    *100     *1000 km        *1000 km      *100 A     *100 C     ASCII
```

### Characteristics

- **Bidirectional**: Requires active request/response
- **Keep-alive**: ~1 second interval
- **Checksum**: XOR of length + command + data
- **Models**: V11, V12, V13, V14

---

## Ninebot Protocol

### Frame Structure

```
┌────────┬────────┬────────┬─────────┬─────────┬─────────────┬──────────────┐
│ Header │ Header │ Length │ Address │ Command │  Payload    │   Checksum   │
│  0x55  │  0xAA  │  (N)   │  Addr   │  Cmd    │  N-2 bytes  │   2 bytes    │
└────────┴────────┴────────┴─────────┴─────────┴─────────────┴──────────────┘
  1 byte   1 byte   1 byte   1 byte    1 byte     Variable      2 bytes

Note: Payload + Checksum are XOR encrypted with gamma key
```

### Request Packet (to BMS 0x22)

```
┌────────┬────────┬────────┬────────┬────────┬──────────────┐
│  0x55  │  0xAA  │  0x03  │  0x22  │  0x01  │   Checksum   │
│        │        │        │  BMS   │  Read  │  (encrypted) │
└────────┴────────┴────────┴────────┴────────┴──────────────┘
```

### Live Data Response

```
┌──────────┬─────────┬────────┬─────────────┬──────────────┬────────────┐
│ Voltage  │ Current │ Speed  │   Trip      │    Total     │Temperature │
│  2 bytes │ 2 bytes │2 bytes │   4 bytes   │   4 bytes    │  2 bytes   │
└──────────┴─────────┴────────┴─────────────┴──────────────┴────────────┘
  *100 V     *100 A    *100     *1000 km        *1000 km      *10 C
```

### Encryption Algorithm

```
Gamma Key = Generate from serial number
For each byte in payload:
    encrypted_byte = plain_byte XOR gamma_key[i % len(gamma_key)]
    i++

Checksum = (XOR of all payload bytes) XOR 0xFFFF
```

### Characteristics

- **Bidirectional**: Requires active request/response
- **Encryption**: XOR with gamma key derived from serial
- **Addresses**: 0x22 (BMS), 0x20 (ESC), others
- **Checksum**: XOR inverted (XOR result XOR 0xFFFF)

---

## Ninebot Z Protocol

### Frame Structure

```
┌────────┬────────┬────────┬─────────┬─────────┬─────────────┬──────────────┐
│ Header │ Header │ Length │ Address │ Command │  Payload    │   Checksum   │
│  0x5A  │  0xA5  │  (N)   │  Addr   │  Cmd    │  N-2 bytes  │   2 bytes    │
└────────┴────────┴────────┴─────────┴─────────┴─────────────┴──────────────┘
  1 byte   1 byte   1 byte   1 byte    1 byte     Variable      2 bytes

Note: Same as Ninebot but with different header (5A A5 vs 55 AA)
```

### Request Packet (to BMS 0x22)

```
┌────────┬────────┬────────┬────────┬────────┬──────────────┐
│  0x5A  │  0xA5  │  0x03  │  0x22  │  0x01  │   Checksum   │
│        │        │        │  BMS   │  Read  │  (encrypted) │
└────────┴────────┴────────┴────────┴────────┴──────────────┘
```

### Live Data Response

Same structure as standard Ninebot protocol, but may include extended fields for model name and additional sensors on Z-series (Z6, Z8, Z10).

### Characteristics

- **Bidirectional**: Requires active request/response
- **Encryption**: Same as standard Ninebot (XOR with gamma key)
- **Models**: Z6, Z8, Z10 (high-performance series)
- **Typical Config**: 20S (Z6/Z8) or 30S (Z10)

---

## Protocol Detection Logic

The integration auto-detects protocols based on packet headers:

```
┌─────────────────────────┬──────────────────────────────────────┐
│      Header Pattern     │          Detected Protocol           │
├─────────────────────────┼──────────────────────────────────────┤
│    DC 5A 5C             │  Veteran/Leaperkim                   │
│    AA 55                │  KingSong                            │
│    55 AA DC 5A          │  Gotway/Begode                       │
│    AA AA                │  InMotion V1                         │
│    DC 5A (no 5C)        │  InMotion V2                         │
│    55 AA (not Gotway)   │  Ninebot                             │
│    5A A5                │  Ninebot Z                           │
└─────────────────────────┴──────────────────────────────────────┘
```

Note: Some protocols share header bytes and require additional checks or minimum packet length for disambiguation.

---

## Communication Types

### Passive (Notification-Only)

These protocols broadcast data automatically via BLE notifications:

- ✅ **Veteran/Leaperkim** - Continuous broadcast
- ✅ **KingSong** - Continuous broadcast  
- ✅ **Gotway/Begode** - Continuous broadcast

### Active (Bidirectional)

These protocols require periodic requests to receive data:

- ⚠️ **InMotion V1** - Request/response with 25ms keep-alive
- ⚠️ **InMotion V2** - Request/response with 1s keep-alive
- ⚠️ **Ninebot** - Request/response with encryption
- ⚠️ **Ninebot Z** - Request/response with encryption

---

## References

- Protocol details researched from [WheelLog Android app](https://github.com/Wheellog/Wheellog.Android)
- BLE characteristic UUIDs documented in `const.py`
- Decoder implementations in `decoders.py`

---

*Last Updated: 2024-01-15*
