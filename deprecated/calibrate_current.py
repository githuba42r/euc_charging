#!/usr/bin/env python3
"""
Calibration capture script for Sherman S charging current.
Captures BLE data at multiple charging rates for analysis.
"""

import asyncio
import sys
from datetime import datetime
from bleak import BleakClient, BleakScanner

MAC = '88:25:83:F3:5D:30'
CHAR_UUID = '0000ffe1-0000-1000-8000-00805f9b34fb'

# Calibration points - adjust as needed
# Format: (target_amps, description)
CALIBRATION_POINTS = [
    (2.0, "Minimum ~2A"),
    (3.0, "Low ~3A"),
    (4.0, "Medium-Low ~4A"),
    (5.0, "Medium ~5A"),
    (6.0, "Medium-High ~6A"),
    (7.0, "High ~7A"),
    (8.0, "Higher ~8A"),
    (9.0, "Very High ~9A"),
    (10.0, "Maximum ~10A"),
]

CAPTURE_DURATION = 10  # seconds per calibration point


class CalibrationCapture:
    def __init__(self):
        self.packets = []
        self.current_target = 0.0

    def callback(self, sender, data):
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        self.packets.append({
            'time': timestamp,
            'target': self.current_target,
            'data': data
        })

    async def capture_at_current(self, client, target_amps: float, description: str):
        """Capture data at a specific charging current setting."""
        self.current_target = target_amps
        start_count = len(self.packets)

        print(f"\n{'='*60}")
        print(f"  CALIBRATION POINT: {description}")
        print(f"  Target: {target_amps:.1f}A on your meter")
        print(f"{'='*60}")

        # Wait for user to set the charger
        input(f"\n  Set charger to ~{target_amps:.1f}A, then press ENTER to capture...")

        # Read actual value from meter
        actual = input(f"  Enter ACTUAL meter reading (A): ").strip()
        try:
            actual_amps = float(actual)
        except:
            actual_amps = target_amps
            print(f"  Using target value: {target_amps:.1f}A")

        self.current_target = actual_amps

        print(f"\n  Capturing for {CAPTURE_DURATION} seconds...")

        # Capture data
        await asyncio.sleep(CAPTURE_DURATION)

        captured = len(self.packets) - start_count
        print(f"  Captured {captured} packets at {actual_amps:.2f}A")

        return actual_amps, captured

    async def run(self):
        print("\n" + "="*60)
        print("  SHERMAN S CHARGING CURRENT CALIBRATION")
        print("="*60)
        print("\nThis script will capture BLE data at multiple charging rates.")
        print("You'll be prompted to adjust your charger at each step.")
        print(f"\nPlanned calibration points: {len(CALIBRATION_POINTS)}")
        for target, desc in CALIBRATION_POINTS:
            print(f"  - {desc}")

        # Ask which points to capture
        print("\nOptions:")
        print("  1. Run all calibration points")
        print("  2. Select specific points")
        print("  3. Custom single point")

        choice = input("\nChoice [1]: ").strip() or "1"

        if choice == "2":
            print("\nEnter point numbers to capture (comma-separated):")
            for i, (target, desc) in enumerate(CALIBRATION_POINTS, 1):
                print(f"  {i}. {desc}")
            selected = input("Points: ").strip()
            try:
                indices = [int(x.strip()) - 1 for x in selected.split(",")]
                points = [CALIBRATION_POINTS[i] for i in indices if 0 <= i < len(CALIBRATION_POINTS)]
            except:
                points = CALIBRATION_POINTS
        elif choice == "3":
            custom = input("Enter target amps: ").strip()
            try:
                target = float(custom)
                points = [(target, f"Custom {target:.1f}A")]
            except:
                points = CALIBRATION_POINTS
        else:
            points = CALIBRATION_POINTS

        print(f"\nWill capture {len(points)} calibration points.")
        input("Press ENTER to connect to the wheel...")

        # Connect and capture
        print(f"\nConnecting to {MAC}...")

        async with BleakClient(MAC) as client:
            print("Connected! Starting notifications...")
            await client.start_notify(CHAR_UUID, self.callback)

            results = []
            for target, desc in points:
                actual, count = await self.capture_at_current(client, target, desc)
                results.append((actual, count))

            await client.stop_notify(CHAR_UUID)

        # Save captured data
        filename = f"calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        with open(filename, 'w') as f:
            f.write("# Calibration capture\n")
            f.write(f"# Date: {datetime.now().isoformat()}\n")
            f.write(f"# Points: {len(points)}\n")
            f.write("#\n")
            for pkt in self.packets:
                f.write(f"{pkt['time']} | {pkt['target']:.2f}A | {pkt['data'].hex()}\n")

        print(f"\n{'='*60}")
        print(f"  CALIBRATION COMPLETE")
        print(f"{'='*60}")
        print(f"\nCaptured {len(self.packets)} total packets")
        print(f"Saved to: {filename}")

        print("\nSummary:")
        for (actual, count), (target, desc) in zip(results, points):
            print(f"  {actual:.2f}A: {count} packets")

        # Analyze the data
        print("\n" + "="*60)
        print("  ANALYSIS")
        print("="*60)

        self.analyze_packets()

        return filename

    def analyze_packets(self):
        """Analyze captured packets to find current correlation."""

        # Group packets by target current
        by_current = {}
        for pkt in self.packets:
            target = pkt['target']
            if target not in by_current:
                by_current[target] = []
            by_current[target].append(pkt['data'])

        print("\nLooking for bytes that correlate with charging current...\n")

        # For each current level, analyze packet patterns
        for target in sorted(by_current.keys()):
            packets = by_current[target]
            print(f"\n--- {target:.2f}A ({len(packets)} packets) ---")

            # Separate packet types
            dc5a_packets = [p for p in packets if len(p) >= 2 and p[0] == 0xDC and p[1] == 0x5A]
            zero_packets = [p for p in packets if len(p) >= 2 and p[0] == 0x00 and p[1] == 0x00]
            other_packets = [p for p in packets if p not in dc5a_packets and p not in zero_packets]

            print(f"  DC5A telemetry: {len(dc5a_packets)}")
            print(f"  00 00 packets:  {len(zero_packets)}")
            print(f"  Other packets:  {len(other_packets)}")

            # Analyze DC5A packets - bytes 16-17 (phase current)
            if dc5a_packets:
                phase_values = []
                for p in dc5a_packets:
                    if len(p) >= 18:
                        val = (p[16] << 8) | p[17]
                        phase_values.append(val)
                if phase_values:
                    avg = sum(phase_values) / len(phase_values)
                    print(f"  DC5A bytes 16-17 (phase): avg={avg:.0f} -> {avg/100:.2f}A")

            # Analyze 00 00 packets - check various byte positions
            if zero_packets:
                # Check bytes 8-9 (our current guess)
                for pos in [6, 8, 10, 12]:
                    values = []
                    for p in zero_packets:
                        if len(p) >= pos + 2:
                            val = (p[pos] << 8) | p[pos + 1]
                            values.append(val)
                    if values:
                        avg = sum(values) / len(values)
                        # Try different divisors
                        print(f"  00 00 bytes {pos}-{pos+1}: avg={avg:.0f}")
                        print(f"    /100={avg/100:.2f}A  /1000={avg/1000:.2f}A  /1245={avg/1245:.2f}A")

            # Show sample packets
            if zero_packets:
                print(f"  Sample 00 00 packet: {zero_packets[0].hex()}")
            if other_packets:
                print(f"  Sample other packet: {other_packets[0][:20].hex()}...")


async def main():
    capture = CalibrationCapture()
    await capture.run()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nCalibration cancelled.")
        sys.exit(0)
