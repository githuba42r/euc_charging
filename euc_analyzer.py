#!/usr/bin/env python3
"""EUC Log Analyzer

A tool for analyzing captured EUC BLE data to help reverse engineer
protocols and add support for new models.

This tool provides:
- Packet pattern analysis
- Header detection
- Field extraction and correlation
- Statistical analysis of data fields
- Visualization of changing values

Usage:
    # Analyze a capture file
    python euc_analyzer.py analyze euc_captures/20260201_120345_veteran_sherman_s.json
    
    # Compare two capture files (e.g., before/after charging)
    python euc_analyzer.py compare capture1.json capture2.json
    
    # Extract patterns from a capture
    python euc_analyzer.py patterns euc_captures/capture.json
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class PacketAnalyzer:
    """Analyzes BLE packet data to identify patterns and structures."""
    
    def __init__(self, capture_data: Dict[str, Any]):
        self.metadata = capture_data.get("metadata", {})
        self.raw_packets = capture_data.get("raw_packets", [])
        self.decoded_packets = capture_data.get("decoded_packets", [])
    
    def analyze(self) -> None:
        """Perform comprehensive analysis of the capture."""
        print("=" * 80)
        print("CAPTURE ANALYSIS")
        print("=" * 80)
        print()
        
        self._print_metadata()
        print()
        
        self._analyze_packet_patterns()
        print()
        
        self._analyze_headers()
        print()
        
        self._analyze_packet_lengths()
        print()
        
        self._analyze_byte_positions()
        print()
        
        if self.decoded_packets:
            self._analyze_decoded_fields()
            print()
    
    def _print_metadata(self) -> None:
        """Print capture metadata."""
        print("METADATA:")
        print("-" * 80)
        for key, value in self.metadata.items():
            print(f"  {key}: {value}")
    
    def _analyze_packet_patterns(self) -> None:
        """Analyze overall packet patterns."""
        print("PACKET PATTERNS:")
        print("-" * 80)
        
        if not self.raw_packets:
            print("  No packets to analyze")
            return
        
        # Analyze packet lengths
        lengths = [p["length"] for p in self.raw_packets]
        length_counts = Counter(lengths)
        
        print(f"  Total packets: {len(self.raw_packets)}")
        print(f"  Unique packet lengths: {len(length_counts)}")
        print(f"  Most common lengths:")
        for length, count in length_counts.most_common(5):
            percentage = (count / len(self.raw_packets)) * 100
            print(f"    {length} bytes: {count} packets ({percentage:.1f}%)")
    
    def _analyze_headers(self) -> None:
        """Analyze packet headers to identify protocol."""
        print("HEADER ANALYSIS:")
        print("-" * 80)
        
        if not self.raw_packets:
            print("  No packets to analyze")
            return
        
        # Look at first 4 bytes of each packet
        header_2byte = Counter()
        header_3byte = Counter()
        header_4byte = Counter()
        
        for packet in self.raw_packets:
            data_hex = packet["data_hex"]
            if len(data_hex) >= 4:
                header_2byte[data_hex[:4]] += 1  # First 2 bytes (4 hex chars)
            if len(data_hex) >= 6:
                header_3byte[data_hex[:6]] += 1  # First 3 bytes
            if len(data_hex) >= 8:
                header_4byte[data_hex[:8]] += 1  # First 4 bytes
        
        print("  Most common 2-byte headers:")
        for header, count in header_2byte.most_common(5):
            percentage = (count / len(self.raw_packets)) * 100
            print(f"    0x{header}: {count} packets ({percentage:.1f}%)")
        
        print()
        print("  Most common 3-byte headers:")
        for header, count in header_3byte.most_common(5):
            percentage = (count / len(self.raw_packets)) * 100
            print(f"    0x{header}: {count} packets ({percentage:.1f}%)")
        
        # Detect known protocols
        print()
        print("  Protocol detection:")
        if any(h.startswith("dc5a5c") for h in header_3byte.keys()):
            print("    ✓ Veteran/Leaperkim protocol detected (DC 5A 5C)")
        if any(h.startswith("aa55") for h in header_2byte.keys()):
            print("    ✓ KingSong protocol detected (AA 55)")
        if any(h.startswith("55aa") for h in header_2byte.keys()):
            print("    ✓ Gotway/Begode protocol detected (55 AA)")
        if any(h.startswith("dc5a") for h in header_2byte.keys()):
            print("    ✓ InMotion V2 protocol detected (DC 5A)")
        if any(h.startswith("aaaa") for h in header_2byte.keys()):
            print("    ✓ InMotion V1 protocol detected (AA AA)")
        if any(h.startswith("5aa5") for h in header_2byte.keys()):
            print("    ✓ Ninebot Z protocol detected (5A A5)")
    
    def _analyze_packet_lengths(self) -> None:
        """Analyze distribution of packet lengths."""
        print("PACKET LENGTH DISTRIBUTION:")
        print("-" * 80)
        
        if not self.raw_packets:
            print("  No packets to analyze")
            return
        
        lengths = [p["length"] for p in self.raw_packets]
        min_len = min(lengths)
        max_len = max(lengths)
        avg_len = sum(lengths) / len(lengths)
        
        print(f"  Min length: {min_len} bytes")
        print(f"  Max length: {max_len} bytes")
        print(f"  Average length: {avg_len:.1f} bytes")
        
        # Check if lengths are fixed or variable
        unique_lengths = len(set(lengths))
        if unique_lengths == 1:
            print(f"  ✓ Fixed-length protocol ({min_len} bytes)")
        else:
            print(f"  ℹ Variable-length protocol ({unique_lengths} different lengths)")
    
    def _analyze_byte_positions(self) -> None:
        """Analyze individual byte positions for patterns."""
        print("BYTE POSITION ANALYSIS:")
        print("-" * 80)
        
        if not self.raw_packets:
            print("  No packets to analyze")
            return
        
        # Only analyze if packets have consistent length
        lengths = [p["length"] for p in self.raw_packets]
        if len(set(lengths)) > 3:
            print("  Skipping (too many different packet lengths)")
            return
        
        # Get the most common length
        common_length = Counter(lengths).most_common(1)[0][0]
        
        # Filter packets with common length
        filtered_packets = [p for p in self.raw_packets if p["length"] == common_length]
        
        print(f"  Analyzing {len(filtered_packets)} packets of length {common_length}")
        print()
        
        # Analyze each byte position
        byte_stats = []
        for pos in range(common_length):
            values = [p["data_bytes"][pos] for p in filtered_packets if pos < len(p["data_bytes"])]
            
            unique_values = len(set(values))
            min_val = min(values)
            max_val = max(values)
            
            # Calculate variance (rough measure of how much the byte changes)
            avg_val = sum(values) / len(values)
            variance = sum((v - avg_val) ** 2 for v in values) / len(values)
            
            byte_stats.append({
                "position": pos,
                "unique_values": unique_values,
                "min": min_val,
                "max": max_val,
                "variance": variance
            })
        
        # Find static bytes (likely header/footer/type indicators)
        static_bytes = [b for b in byte_stats if b["unique_values"] == 1]
        if static_bytes:
            print("  Static bytes (constant across all packets):")
            for byte_info in static_bytes:
                print(f"    Byte {byte_info['position']:3d}: 0x{byte_info['min']:02X}")
        
        print()
        
        # Find highly variable bytes (likely data fields)
        variable_bytes = [b for b in byte_stats if b["variance"] > 100 and b["unique_values"] > 10]
        if variable_bytes:
            print("  Highly variable bytes (likely data fields):")
            for byte_info in variable_bytes[:10]:  # Show top 10
                print(f"    Byte {byte_info['position']:3d}: {byte_info['unique_values']} unique values, "
                      f"range 0x{byte_info['min']:02X}-0x{byte_info['max']:02X}, "
                      f"variance {byte_info['variance']:.1f}")
    
    def _analyze_decoded_fields(self) -> None:
        """Analyze decoded packet fields if available."""
        print("DECODED FIELD ANALYSIS:")
        print("-" * 80)
        
        if not self.decoded_packets:
            print("  No decoded packets available")
            return
        
        # Collect all field values
        fields = defaultdict(list)
        for packet in self.decoded_packets:
            for key, value in packet.items():
                if key != "timestamp" and isinstance(value, (int, float)):
                    fields[key].append(value)
        
        # Analyze each field
        for field_name, values in sorted(fields.items()):
            if not values:
                continue
            
            min_val = min(values)
            max_val = max(values)
            avg_val = sum(values) / len(values)
            
            # Check if field changes
            unique_values = len(set(values))
            
            if unique_values == 1:
                print(f"  {field_name}: constant = {values[0]}")
            else:
                print(f"  {field_name}:")
                print(f"    Min: {min_val:.3f}")
                print(f"    Max: {max_val:.3f}")
                print(f"    Avg: {avg_val:.3f}")
                print(f"    Unique values: {unique_values}")


def compare_captures(file1: str, file2: str) -> None:
    """Compare two capture files to identify differences."""
    print("=" * 80)
    print("CAPTURE COMPARISON")
    print("=" * 80)
    print()
    
    with open(file1) as f:
        data1 = json.load(f)
    
    with open(file2) as f:
        data2 = json.load(f)
    
    print(f"File 1: {file1}")
    print(f"  Brand: {data1['metadata'].get('brand')}")
    print(f"  Model: {data1['metadata'].get('model')}")
    print(f"  Packets: {len(data1['raw_packets'])}")
    print()
    
    print(f"File 2: {file2}")
    print(f"  Brand: {data2['metadata'].get('brand')}")
    print(f"  Model: {data2['metadata'].get('model')}")
    print(f"  Packets: {len(data2['raw_packets'])}")
    print()
    
    # Compare decoded fields if available
    if data1['decoded_packets'] and data2['decoded_packets']:
        print("DECODED FIELD COMPARISON:")
        print("-" * 80)
        
        # Get first and last packets from each capture
        first1 = data1['decoded_packets'][0]
        last1 = data1['decoded_packets'][-1]
        first2 = data2['decoded_packets'][0]
        last2 = data2['decoded_packets'][-1]
        
        # Compare common fields
        all_keys = set(first1.keys()) | set(first2.keys())
        all_keys.discard("timestamp")
        
        for key in sorted(all_keys):
            if key in first1 and key in first2:
                val1_first = first1[key]
                val1_last = last1.get(key, val1_first)
                val2_first = first2[key]
                val2_last = last2.get(key, val2_first)
                
                if isinstance(val1_first, (int, float)):
                    change1 = val1_last - val1_first
                    change2 = val2_last - val2_first
                    
                    print(f"  {key}:")
                    print(f"    Capture 1: {val1_first:.3f} -> {val1_last:.3f} (Δ {change1:.3f})")
                    print(f"    Capture 2: {val2_first:.3f} -> {val2_last:.3f} (Δ {change2:.3f})")
                    print()


def extract_patterns(filepath: str) -> None:
    """Extract repeating patterns from a capture file."""
    print("=" * 80)
    print("PATTERN EXTRACTION")
    print("=" * 80)
    print()
    
    with open(filepath) as f:
        data = json.load(f)
    
    raw_packets = data.get("raw_packets", [])
    
    if not raw_packets:
        print("No packets to analyze")
        return
    
    # Look for repeating byte sequences
    print("Looking for repeating sequences...")
    print()
    
    # Get most common packet length
    lengths = [p["length"] for p in raw_packets]
    common_length = Counter(lengths).most_common(1)[0][0]
    
    # Filter to common length
    packets = [p["data_bytes"] for p in raw_packets if p["length"] == common_length]
    
    # Find sequences that appear in multiple positions
    sequence_length = 2
    sequences = defaultdict(list)
    
    for i, packet in enumerate(packets):
        for pos in range(len(packet) - sequence_length + 1):
            seq = tuple(packet[pos:pos + sequence_length])
            sequences[seq].append((i, pos))
    
    # Filter to sequences that appear in same position across multiple packets
    common_sequences = {}
    for seq, positions in sequences.items():
        # Group by position
        by_position = defaultdict(int)
        for _, pos in positions:
            by_position[pos] += 1
        
        # Find positions where this sequence appears frequently
        for pos, count in by_position.items():
            if count > len(packets) * 0.8:  # Appears in 80%+ of packets
                if pos not in common_sequences:
                    common_sequences[pos] = seq
    
    if common_sequences:
        print("Common sequences (appear in 80%+ of packets):")
        for pos, seq in sorted(common_sequences.items()):
            hex_seq = " ".join(f"{b:02X}" for b in seq)
            print(f"  Position {pos}: {hex_seq}")
    else:
        print("No common sequences found")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="EUC Log Analyzer - Analyze captured BLE data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze a capture file
  python euc_analyzer.py analyze euc_captures/capture.json
  
  # Compare two captures
  python euc_analyzer.py compare capture1.json capture2.json
  
  # Extract patterns
  python euc_analyzer.py patterns euc_captures/capture.json
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a capture file")
    analyze_parser.add_argument("filepath", help="Path to the capture file")
    
    # Compare command
    compare_parser = subparsers.add_parser("compare", help="Compare two capture files")
    compare_parser.add_argument("file1", help="First capture file")
    compare_parser.add_argument("file2", help="Second capture file")
    
    # Patterns command
    patterns_parser = subparsers.add_parser("patterns", help="Extract patterns from a capture")
    patterns_parser.add_argument("filepath", help="Path to the capture file")
    
    args = parser.parse_args()
    
    if args.command == "analyze":
        try:
            with open(args.filepath) as f:
                data = json.load(f)
            
            analyzer = PacketAnalyzer(data)
            analyzer.analyze()
        except Exception as e:
            print(f"Error analyzing file: {e}")
            sys.exit(1)
    
    elif args.command == "compare":
        try:
            compare_captures(args.file1, args.file2)
        except Exception as e:
            print(f"Error comparing files: {e}")
            sys.exit(1)
    
    elif args.command == "patterns":
        try:
            extract_patterns(args.filepath)
        except Exception as e:
            print(f"Error extracting patterns: {e}")
            sys.exit(1)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
