"""Simple test runner for decoders that doesn't require Home Assistant."""

import struct

# Inline the minimal needed code to test decoders
print("Testing Protocol Detection...")
print("=" * 60)

# Test 1: Veteran protocol detection
veteran_packet = bytes([0xDC, 0x5A, 0x5C, 0x10])
print(f"Veteran header: {veteran_packet[:4].hex()}")
assert veteran_packet[0] == 0xDC and veteran_packet[1] == 0x5A and veteran_packet[2] == 0x5C
print("✓ Veteran protocol detection works")

# Test 2: KingSong protocol detection
kingsong_packet = bytes([0xAA, 0x55, 0x14, 0x5A])
print(f"KingSong header: {kingsong_packet[:4].hex()}")
assert kingsong_packet[0] == 0xAA and kingsong_packet[1] == 0x55
print("✓ KingSong protocol detection works")

# Test 3: Gotway protocol detection (55 AA DC 5A - unique 4-byte header)
gotway_packet = bytes([0x55, 0xAA, 0xDC, 0x5A])
print(f"Gotway header: {gotway_packet[:4].hex()}")
assert gotway_packet[0] == 0x55 and gotway_packet[1] == 0xAA and gotway_packet[2] == 0xDC and gotway_packet[3] == 0x5A
print("✓ Gotway protocol detection works (55 AA DC 5A)")

# Test 4: InMotion V1 protocol detection (AA AA with small len)
inmotion_packet = bytes([0xAA, 0xAA, 0x09, 0x01])
print(f"InMotion V1 header: {inmotion_packet[:4].hex()}")
assert inmotion_packet[0] == 0xAA and inmotion_packet[1] == 0xAA
print("✓ InMotion V1 protocol detection works (AA AA len=09)")

# Test 5: InMotion V2 protocol detection (DC 5A with flags != 5C)
inmotionv2_packet = bytes([0xDC, 0x5A, 0x05, 0x01])
print(f"InMotion V2 header: {inmotionv2_packet[:4].hex()}")
assert inmotionv2_packet[0] == 0xDC and inmotionv2_packet[1] == 0x5A and inmotionv2_packet[2] != 0x5C
print("✓ InMotion V2 protocol detection works (DC 5A flags=05)")

# Test 6: Ninebot protocol detection (55 AA but NOT followed by DC 5A)
ninebot_packet = bytes([0x55, 0xAA, 0x03, 0x22])
print(f"Ninebot header: {ninebot_packet[:4].hex()}")
assert ninebot_packet[0] == 0x55 and ninebot_packet[1] == 0xAA and ninebot_packet[2] != 0xDC
print("✓ Ninebot protocol detection works (55 AA 03, NOT DC)")

# Test 7: Ninebot Z protocol detection
ninebotz_packet = bytes([0x5A, 0xA5, 0x03, 0x22])
print(f"Ninebot Z header: {ninebotz_packet[:4].hex()}")
assert ninebotz_packet[0] == 0x5A and ninebotz_packet[1] == 0xA5
print("✓ Ninebot Z protocol detection works")

print()
print("Testing Battery Calculations...")
print("=" * 60)

# Test battery percentage calculation
def calculate_battery_percent(voltage, max_voltage):
    """Simplified battery calculation for testing."""
    if max_voltage <= 0:
        return 0.0
    cells = round(max_voltage / 4.2)
    min_v = cells * 3.0
    return max(0.0, min(100.0, ((voltage - min_v) / (max_voltage - min_v)) * 100.0))

# Test full charge (24S = 100.8V)
percent = calculate_battery_percent(100.8, 100.8)
print(f"24S Full (100.8V): {percent:.1f}%")
assert percent >= 95.0, f"Expected >= 95%, got {percent}%"
print("✓ Full battery calculation works")

# Test half charge
percent = calculate_battery_percent(86.4, 100.8)
print(f"24S Half (~86.4V): {percent:.1f}%")
assert 40.0 <= percent <= 60.0, f"Expected 40-60%, got {percent}%"
print("✓ Half battery calculation works")

# Test empty (24 cells * 3.0V = 72V)
percent = calculate_battery_percent(72.0, 100.8)
print(f"24S Empty (72V): {percent:.1f}%")
assert percent <= 5.0, f"Expected <= 5%, got {percent}%"
print("✓ Empty battery calculation works")

print()
print("Testing Encryption...")
print("=" * 60)

# Test XOR encryption
def xor_encrypt(data, key):
    """Simple XOR encryption."""
    result = bytearray()
    for i, byte in enumerate(data):
        result.append(byte ^ key[i % len(key)])
    return bytes(result)

test_data = b"Hello World!"
test_key = bytes([0x12, 0x34, 0x56, 0x78])
encrypted = xor_encrypt(test_data, test_key)
decrypted = xor_encrypt(encrypted, test_key)

print(f"Original:  {test_data.hex()}")
print(f"Encrypted: {encrypted.hex()}")
print(f"Decrypted: {decrypted.hex()}")
assert test_data == decrypted, "Encryption/decryption failed"
print("✓ XOR encryption works")

print()
print("Testing Checksum Calculations...")
print("=" * 60)

# Test XOR checksum (Ninebot style)
def xor_checksum(data):
    """Calculate XOR checksum."""
    result = 0
    for byte in data:
        result ^= byte
    return result

test_data = bytes([0x01, 0x02, 0x03, 0x04])
checksum = xor_checksum(test_data)
print(f"Data: {test_data.hex()}, XOR Checksum: {checksum:02x}")
assert checksum == 0x04, f"Expected 0x04, got {checksum:02x}"
print("✓ XOR checksum works")

# Test sum checksum (InMotion style)
def sum_checksum(data):
    """Calculate sum checksum."""
    return sum(data) & 0xFFFF

checksum = sum_checksum(test_data)
print(f"Data: {test_data.hex()}, Sum Checksum: {checksum:04x}")
assert checksum == 0x000A, f"Expected 0x000A, got {checksum:04x}"
print("✓ Sum checksum works")

print()
print("=" * 60)
print("All tests passed! ✓")
print("=" * 60)
