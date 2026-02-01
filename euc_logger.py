#!/usr/bin/env python3
"""EUC BLE Data Logger

A command-line tool for capturing and logging BLE data from Electric Unicycles.
This tool is designed to help contributors capture data from their EUC for
reverse engineering and adding support for new models.

Usage:
    # Scan for nearby EUC devices
    python euc_logger.py scan
    
    # Capture data from a specific MAC address
    python euc_logger.py capture AA:BB:CC:DD:EE:FF --brand veteran --model "Sherman S" --duration 60
    
    # Capture data with auto-detection
    python euc_logger.py capture AA:BB:CC:DD:EE:FF --auto-detect --duration 300
    
    # List previous captures
    python euc_logger.py list
    
    # View a capture file
    python euc_logger.py view captures/20260201_120345_veteran_sherman_s.json
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from bleak import BleakClient, BleakScanner
    from bleak.backends.device import BLEDevice
except ImportError:
    print("Error: bleak library not found. Install with: pip install bleak")
    sys.exit(1)

# Import our decoders
sys.path.insert(0, str(Path(__file__).parent / "custom_components" / "euc_charging"))
from const import (
    ALL_SERVICE_UUIDS,
    BRAND_DEVICE_NAMES,
    CELL_CONFIG,
    WheelBrand,
    KINGSONG_SERVICE_UUID,
    KINGSONG_READ_UUID,
    VETERAN_SERVICE_UUID,
    VETERAN_READ_UUID,
)
from decoders import get_decoder_by_data, get_decoder_by_brand

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
_LOGGER = logging.getLogger(__name__)

# Default directory for captured logs
CAPTURE_DIR = Path("euc_captures")


class EucDataCapture:
    """Captures BLE data from an EUC device."""
    
    def __init__(
        self,
        mac_address: str,
        brand: Optional[WheelBrand] = None,
        model: Optional[str] = None,
        auto_detect: bool = False
    ):
        self.mac_address = mac_address
        self.brand = brand
        self.model = model
        self.auto_detect = auto_detect
        self.decoder = None
        
        # Data storage
        self.raw_packets = []
        self.decoded_packets = []
        self.start_time = None
        self.end_time = None
        
        # Connection
        self.client: Optional[BleakClient] = None
        self.device: Optional[BLEDevice] = None
        
    async def scan_and_find(self) -> bool:
        """Scan for the device and determine service UUIDs."""
        _LOGGER.info(f"Scanning for device {self.mac_address}...")
        
        devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
        
        for device, adv_data in devices.values():
            if device.address.lower() == self.mac_address.lower():
                self.device = device
                _LOGGER.info(f"Found device: {device.name} ({device.address})")
                _LOGGER.info(f"RSSI: {adv_data.rssi} dBm")
                _LOGGER.info(f"Service UUIDs: {adv_data.service_uuids}")
                return True
        
        _LOGGER.error(f"Device {self.mac_address} not found")
        return False
    
    async def connect(self) -> bool:
        """Connect to the EUC device."""
        try:
            _LOGGER.info(f"Connecting to {self.mac_address}...")
            self.client = BleakClient(self.mac_address)
            await self.client.connect()
            
            if not self.client.is_connected:
                _LOGGER.error("Failed to connect")
                return False
            
            _LOGGER.info("Connected successfully")
            
            # Log available services and characteristics
            services = self.client.services
            _LOGGER.info("Available services:")
            for service in services:
                _LOGGER.info(f"  Service: {service.uuid}")
                for char in service.characteristics:
                    _LOGGER.info(f"    Characteristic: {char.uuid} - {char.properties}")
            
            return True
            
        except Exception as e:
            _LOGGER.error(f"Connection failed: {e}")
            return False
    
    def _notification_handler(self, sender: int, data: bytes) -> None:
        """Handle incoming BLE notifications."""
        timestamp = datetime.now().isoformat()
        
        # Store raw packet
        packet_info = {
            "timestamp": timestamp,
            "sender": sender,
            "data_hex": data.hex(),
            "data_bytes": list(data),
            "length": len(data),
        }
        self.raw_packets.append(packet_info)
        
        # Try to decode if we have a decoder
        if self.decoder is None and self.auto_detect:
            self.decoder = get_decoder_by_data(data)
            if self.decoder:
                _LOGGER.info(f"Auto-detected protocol: {self.decoder.brand.value}")
        
        if self.decoder:
            try:
                decoded = self.decoder.decode(data)
                if decoded:
                    decoded["timestamp"] = timestamp
                    self.decoded_packets.append(decoded)
                    _LOGGER.debug(f"Decoded: {json.dumps(decoded, indent=2)}")
            except Exception as e:
                _LOGGER.debug(f"Decode error: {e}")
    
    async def capture(self, duration: int = 60) -> bool:
        """Capture data for the specified duration (seconds)."""
        try:
            # Determine which characteristic to subscribe to
            # Try common service/characteristic UUIDs
            notify_uuid = None
            
            # Check which service UUID is available
            for service in self.client.services:
                if service.uuid in ALL_SERVICE_UUIDS or service.uuid.startswith("0000ffe0"):
                    for char in service.characteristics:
                        if "notify" in char.properties:
                            notify_uuid = char.uuid
                            _LOGGER.info(f"Using notification characteristic: {notify_uuid}")
                            break
                if notify_uuid:
                    break
            
            if not notify_uuid:
                _LOGGER.error("Could not find notification characteristic")
                return False
            
            # Create decoder if brand is specified
            if self.brand and not self.decoder:
                self.decoder = get_decoder_by_brand(self.brand)
            
            # Start notifications
            _LOGGER.info(f"Starting data capture for {duration} seconds...")
            _LOGGER.info("Press Ctrl+C to stop early")
            
            self.start_time = datetime.now()
            await self.client.start_notify(notify_uuid, self._notification_handler)
            
            # Wait for duration or until interrupted
            try:
                await asyncio.sleep(duration)
            except KeyboardInterrupt:
                _LOGGER.info("Capture interrupted by user")
            
            # Stop notifications
            await self.client.stop_notify(notify_uuid)
            self.end_time = datetime.now()
            
            _LOGGER.info(f"Capture complete. Received {len(self.raw_packets)} packets")
            if self.decoded_packets:
                _LOGGER.info(f"Successfully decoded {len(self.decoded_packets)} packets")
            
            return True
            
        except Exception as e:
            _LOGGER.error(f"Capture error: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            _LOGGER.info("Disconnected")
    
    def save_to_file(self, output_path: Optional[Path] = None) -> Path:
        """Save captured data to a JSON file."""
        if output_path is None:
            # Generate filename
            CAPTURE_DIR.mkdir(exist_ok=True)
            timestamp = self.start_time.strftime("%Y%m%d_%H%M%S") if self.start_time else "unknown"
            brand = self.brand.value if self.brand else "unknown"
            model = self.model.replace(" ", "_").lower() if self.model else "unknown"
            filename = f"{timestamp}_{brand}_{model}.json"
            output_path = CAPTURE_DIR / filename
        
        # Prepare data structure
        capture_data = {
            "metadata": {
                "mac_address": self.mac_address,
                "brand": self.brand.value if self.brand else "unknown",
                "model": self.model or "unknown",
                "start_time": self.start_time.isoformat() if self.start_time else None,
                "end_time": self.end_time.isoformat() if self.end_time else None,
                "duration_seconds": (self.end_time - self.start_time).total_seconds() if (self.start_time and self.end_time) else 0,
                "total_packets": len(self.raw_packets),
                "decoded_packets": len(self.decoded_packets),
                "decoder_used": self.decoder.name if self.decoder else None,
            },
            "raw_packets": self.raw_packets,
            "decoded_packets": self.decoded_packets,
        }
        
        # Write to file
        with open(output_path, 'w') as f:
            json.dump(capture_data, f, indent=2)
        
        _LOGGER.info(f"Saved capture to {output_path}")
        return output_path


async def scan_for_eucs() -> None:
    """Scan for nearby EUC devices."""
    print("Scanning for EUC devices (10 seconds)...")
    print()
    
    devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
    
    euc_devices = []
    for device, adv_data in devices.values():
        # Check if device name matches any known EUC patterns
        is_euc = False
        detected_brand = None
        
        if device.name:
            for brand, patterns in BRAND_DEVICE_NAMES.items():
                for pattern in patterns:
                    if pattern.lower() in device.name.lower():
                        is_euc = True
                        detected_brand = brand
                        break
                if is_euc:
                    break
        
        # Check service UUIDs
        for service_uuid in adv_data.service_uuids:
            if service_uuid in ALL_SERVICE_UUIDS:
                is_euc = True
                break
        
        if is_euc:
            euc_devices.append((device, adv_data, detected_brand))
    
    if not euc_devices:
        print("No EUC devices found nearby.")
        print("Make sure your EUC is powered on and in range.")
        return
    
    print(f"Found {len(euc_devices)} EUC device(s):\n")
    
    for device, adv_data, brand in euc_devices:
        print(f"Device: {device.name or 'Unknown'}")
        print(f"  MAC Address: {device.address}")
        print(f"  RSSI: {adv_data.rssi} dBm")
        if brand:
            print(f"  Detected Brand: {brand.value}")
        print(f"  Service UUIDs: {', '.join(adv_data.service_uuids)}")
        print()


async def capture_data(
    mac_address: str,
    brand: Optional[str],
    model: Optional[str],
    duration: int,
    auto_detect: bool,
    output: Optional[str]
) -> None:
    """Capture data from an EUC device."""
    # Parse brand
    wheel_brand = None
    if brand:
        try:
            wheel_brand = WheelBrand(brand.lower())
        except ValueError:
            _LOGGER.error(f"Unknown brand: {brand}")
            _LOGGER.info(f"Available brands: {', '.join([b.value for b in WheelBrand])}")
            return
    
    # Create capture instance
    capture = EucDataCapture(
        mac_address=mac_address,
        brand=wheel_brand,
        model=model,
        auto_detect=auto_detect or (wheel_brand is None)
    )
    
    # Find device
    if not await capture.scan_and_find():
        return
    
    # Connect
    if not await capture.connect():
        return
    
    try:
        # Capture data
        if await capture.capture(duration):
            # Save to file
            output_path = Path(output) if output else None
            capture.save_to_file(output_path)
    finally:
        # Always disconnect
        await capture.disconnect()


def list_captures() -> None:
    """List all captured log files."""
    if not CAPTURE_DIR.exists():
        print("No captures found.")
        return
    
    captures = list(CAPTURE_DIR.glob("*.json"))
    
    if not captures:
        print("No captures found.")
        return
    
    print(f"Found {len(captures)} capture(s):\n")
    
    for capture_file in sorted(captures, reverse=True):
        try:
            with open(capture_file) as f:
                data = json.load(f)
            
            metadata = data.get("metadata", {})
            print(f"File: {capture_file.name}")
            print(f"  Brand: {metadata.get('brand', 'unknown')}")
            print(f"  Model: {metadata.get('model', 'unknown')}")
            print(f"  MAC: {metadata.get('mac_address', 'unknown')}")
            print(f"  Captured: {metadata.get('start_time', 'unknown')}")
            print(f"  Duration: {metadata.get('duration_seconds', 0):.1f}s")
            print(f"  Packets: {metadata.get('total_packets', 0)} (decoded: {metadata.get('decoded_packets', 0)})")
            print()
        except Exception as e:
            print(f"Error reading {capture_file.name}: {e}")
            print()


def view_capture(filepath: str) -> None:
    """View a capture file."""
    try:
        with open(filepath) as f:
            data = json.load(f)
        
        metadata = data.get("metadata", {})
        raw_packets = data.get("raw_packets", [])
        decoded_packets = data.get("decoded_packets", [])
        
        print("=" * 80)
        print("CAPTURE METADATA")
        print("=" * 80)
        for key, value in metadata.items():
            print(f"{key}: {value}")
        
        print()
        print("=" * 80)
        print(f"RAW PACKETS ({len(raw_packets)} total)")
        print("=" * 80)
        
        # Show first 10 raw packets
        for i, packet in enumerate(raw_packets[:10]):
            print(f"\nPacket {i + 1}:")
            print(f"  Time: {packet.get('timestamp')}")
            print(f"  Length: {packet.get('length')} bytes")
            print(f"  Hex: {packet.get('data_hex')}")
        
        if len(raw_packets) > 10:
            print(f"\n... and {len(raw_packets) - 10} more packets")
        
        if decoded_packets:
            print()
            print("=" * 80)
            print(f"DECODED PACKETS ({len(decoded_packets)} total)")
            print("=" * 80)
            
            # Show first 5 decoded packets
            for i, packet in enumerate(decoded_packets[:5]):
                print(f"\nDecoded Packet {i + 1}:")
                print(json.dumps(packet, indent=2))
            
            if len(decoded_packets) > 5:
                print(f"\n... and {len(decoded_packets) - 5} more decoded packets")
        
    except Exception as e:
        print(f"Error reading capture file: {e}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="EUC BLE Data Logger - Capture and analyze EUC Bluetooth data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan for nearby EUC devices
  python euc_logger.py scan
  
  # Capture data with auto-detection
  python euc_logger.py capture AA:BB:CC:DD:EE:FF --auto-detect --duration 60
  
  # Capture data from a known Veteran wheel
  python euc_logger.py capture AA:BB:CC:DD:EE:FF --brand veteran --model "Sherman S" --duration 300
  
  # List previous captures
  python euc_logger.py list
  
  # View a capture file
  python euc_logger.py view euc_captures/20260201_120345_veteran_sherman_s.json
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Scan command
    subparsers.add_parser("scan", help="Scan for nearby EUC devices")
    
    # Capture command
    capture_parser = subparsers.add_parser("capture", help="Capture data from an EUC device")
    capture_parser.add_argument("mac_address", help="MAC address of the EUC (XX:XX:XX:XX:XX:XX)")
    capture_parser.add_argument("--brand", help="Brand of the EUC (veteran, kingsong, gotway, etc.)")
    capture_parser.add_argument("--model", help="Model name of the EUC")
    capture_parser.add_argument("--duration", type=int, default=60, help="Capture duration in seconds (default: 60)")
    capture_parser.add_argument("--auto-detect", action="store_true", help="Auto-detect protocol from data")
    capture_parser.add_argument("--output", help="Output file path (default: auto-generated)")
    
    # List command
    subparsers.add_parser("list", help="List all captured log files")
    
    # View command
    view_parser = subparsers.add_parser("view", help="View a capture file")
    view_parser.add_argument("filepath", help="Path to the capture file")
    
    args = parser.parse_args()
    
    if args.command == "scan":
        asyncio.run(scan_for_eucs())
    
    elif args.command == "capture":
        asyncio.run(capture_data(
            mac_address=args.mac_address,
            brand=args.brand,
            model=args.model,
            duration=args.duration,
            auto_detect=args.auto_detect,
            output=args.output
        ))
    
    elif args.command == "list":
        list_captures()
    
    elif args.command == "view":
        view_capture(args.filepath)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
