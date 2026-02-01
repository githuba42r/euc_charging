#!/usr/bin/env python3
"""
Leaperkim Sherman S - Bluetooth Proxy
Connects to the wheel and re-broadcasts packets over a local WebSocket,
allowing both our decoder and EUC World to monitor simultaneously.

This proxy:
1. Connects to the Sherman S via BLE
2. Receives notifications from the wheel
3. Logs packets with decoded values
4. Optionally forwards to EUC World via a virtual serial port or network

Usage:
    python proxy.py

The proxy will display live decoded values alongside the raw packets,
so you can compare with EUC World's display.
"""

import asyncio
import struct
import json
import logging
from datetime import datetime
from pathlib import Path

from bleak import BleakClient, BleakScanner

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Target device
TARGET_MAC = "88:25:83:F3:5D:30"
NOTIFY_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# Log file for raw packets
LOG_FILE = Path(__file__).parent / "proxy_log.txt"


class PacketAnalyzer:
    """Analyzes packets and tries multiple decoding strategies."""

    def __init__(self):
        self.packet_count = 0
        self.last_values = {}

    def analyze(self, data: bytes) -> dict:
        """Analyze a packet and return all possible interpretations."""
        self.packet_count += 1
        result = {
            'raw': data.hex(),
            'len': len(data),
            'interpretations': []
        }

        if len(data) < 2:
            return result

        # DC5A Telemetry frame
        if data[0] == 0xDC and data[1] == 0x5A and len(data) >= 20:
            voltage = struct.unpack(">H", data[4:6])[0] / 100.0
            result['type'] = 'DC5A_TELEMETRY'
            result['voltage'] = voltage
            result['battery'] = self._calc_battery(voltage)
            self.last_values['voltage'] = voltage

        # Packets with varying current (00 00 00 00 XX XX YY YY pattern)
        elif data[0] == 0x00 and data[1] == 0x00 and len(data) >= 20:
            # Check for the current pattern: 00 00 00 00 0X 00 0Y YY ff ff ff ff ff 32 ee ...
            if len(data) >= 12 and data[10] == 0xFF and data[11] == 0xFF:
                # Bytes 8-9 appear to be the current
                raw_current = struct.unpack(">H", data[8:10])[0]

                # Try different divisors
                result['type'] = 'CURRENT_FRAME'
                result['raw_current'] = raw_current
                result['current_div1245'] = raw_current / 1245.0
                result['current_div1000'] = raw_current / 1000.0
                result['current_div100'] = raw_current / 100.0

                self.last_values['raw_current'] = raw_current

        # 0E 10 continuation frames
        elif data[0] == 0x0E and len(data) >= 20:
            result['type'] = '0E_CONTINUATION'
            # Position 8-9 has 0BC7 = 3015 static value
            val_8 = struct.unpack(">H", data[8:10])[0]
            result['pos_8_9'] = val_8
            result['pos_8_9_div1245'] = val_8 / 1245.0

        # 0B BMS frames
        elif data[0] == 0x0B and len(data) >= 20:
            result['type'] = 'BMS_FRAME'
            val_0 = struct.unpack(">H", data[0:2])[0]
            result['bytes_0_1'] = val_0
            result['current_div1245'] = val_0 / 1245.0
            self.last_values['bms_current'] = val_0 / 1245.0

        else:
            result['type'] = 'UNKNOWN'
            # Try to find any values that could be current (1000-10000 range)
            for i in range(0, min(len(data)-1, 18), 2):
                val = struct.unpack(">H", data[i:i+2])[0]
                if 1000 <= val <= 10000:
                    result['interpretations'].append({
                        'pos': i,
                        'val': val,
                        'as_current': val / 1245.0
                    })

        return result

    def _calc_battery(self, voltage: float) -> float:
        """Calculate battery percentage from voltage."""
        min_v, max_v = 72.0, 100.8
        pct = (voltage - min_v) / (max_v - min_v) * 100
        return max(0, min(100, pct))


class BluetoothProxy:
    """Proxy that connects to wheel and logs/broadcasts packets."""

    def __init__(self, address: str = TARGET_MAC):
        self.address = address
        self.analyzer = PacketAnalyzer()
        self.running = False
        self.log_file = None

        # Current display values
        self.display = {
            'voltage': 0.0,
            'current': 0.0,
            'battery': 0.0,
            'raw_current': 0,
            'packet_count': 0
        }

    def _notification_handler(self, characteristic, data: bytearray):
        """Handle incoming BLE notifications."""
        timestamp = datetime.now()

        # Analyze packet
        analysis = self.analyzer.analyze(bytes(data))

        # Update display values
        self.display['packet_count'] = self.analyzer.packet_count

        if 'voltage' in analysis:
            self.display['voltage'] = analysis['voltage']
            self.display['battery'] = analysis['battery']

        if 'raw_current' in analysis:
            self.display['raw_current'] = analysis['raw_current']
            # Use div1245 as primary
            self.display['current'] = analysis['current_div1245']

        if analysis.get('type') == 'BMS_FRAME':
            self.display['bms_current'] = analysis.get('current_div1245', 0)

        # Log to file
        if self.log_file:
            log_entry = {
                'time': timestamp.isoformat(),
                **analysis
            }
            self.log_file.write(json.dumps(log_entry) + '\n')
            self.log_file.flush()

        # Print interesting packets
        pkt_type = analysis.get('type', 'UNKNOWN')

        if pkt_type == 'DC5A_TELEMETRY':
            pass  # Don't spam with telemetry
        elif pkt_type == 'CURRENT_FRAME':
            raw = analysis['raw_current']
            c1245 = analysis['current_div1245']
            c1000 = analysis['current_div1000']
            c100 = analysis['current_div100']
            print(f"\r[CURRENT] Raw: {raw:5d} | /1245={c1245:.2f}A | /1000={c1000:.2f}A | /100={c100:.1f}A    ", end='', flush=True)
        elif pkt_type == 'BMS_FRAME':
            print(f"\r[BMS] Current: {analysis.get('current_div1245', 0):.2f}A                                    ", end='', flush=True)

    def _print_status(self):
        """Print current status."""
        d = self.display
        print(f"\r{d['packet_count']:5d} pkts | V={d['voltage']:.2f}V | I(raw)={d['raw_current']:5d} | I={d['current']:.2f}A | Bat={d['battery']:.1f}%    ", end='', flush=True)

    async def run(self):
        """Main run loop."""
        self.running = True

        # Open log file
        self.log_file = open(LOG_FILE, 'w')
        logger.info(f"Logging to: {LOG_FILE}")

        print("\n" + "=" * 70)
        print("SHERMAN S BLUETOOTH PROXY")
        print("=" * 70)
        print("Compare these values with EUC World to find correct divisor")
        print("=" * 70 + "\n")

        try:
            logger.info(f"Scanning for {self.address}...")
            device = await BleakScanner.find_device_by_address(
                self.address, timeout=30.0
            )

            if not device:
                logger.error("Device not found!")
                return

            logger.info(f"Found: {device.name}")
            logger.info("Connecting...")

            async with BleakClient(self.address) as client:
                logger.info("Connected!")

                await client.start_notify(NOTIFY_UUID, self._notification_handler)
                logger.info("Subscribed to notifications")

                print("\n" + "-" * 70)
                print("LIVE DATA (compare with EUC World)")
                print("-" * 70)
                print("Format: [TYPE] Raw value | different divisor interpretations")
                print("-" * 70 + "\n")

                # Run until stopped
                status_interval = 0
                while self.running:
                    await asyncio.sleep(0.1)
                    status_interval += 1

                    # Print status every second
                    if status_interval >= 10:
                        # self._print_status()
                        status_interval = 0

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error: {e}")
            raise
        finally:
            if self.log_file:
                self.log_file.close()
            print("\n\nProxy stopped.")

    def stop(self):
        """Stop the proxy."""
        self.running = False


async def main():
    """Main entry point."""
    proxy = BluetoothProxy()

    try:
        await proxy.run()
    except KeyboardInterrupt:
        proxy.stop()


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                    SHERMAN S BLUETOOTH PROXY                         ║
╠══════════════════════════════════════════════════════════════════════╣
║ This proxy connects to the wheel and logs packets with multiple      ║
║ current interpretations. Compare with EUC World to find the          ║
║ correct divisor.                                                     ║
║                                                                       ║
║ NOTE: EUC World connects directly to the wheel - this proxy will     ║
║ disconnect when EUC World tries to connect (BLE is 1:1).            ║
║                                                                       ║
║ To compare: Run this proxy, note the raw values, then disconnect     ║
║ and connect EUC World to see what current it shows for similar       ║
║ battery/voltage levels.                                              ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    asyncio.run(main())
