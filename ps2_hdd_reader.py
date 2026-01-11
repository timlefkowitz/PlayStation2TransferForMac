#!/usr/bin/env python3
"""
PS2 HDD Reader for macOS
A tool to read and extract files from PlayStation 2 hard drives on macOS.
"""

import os
import sys
import struct
import argparse
from pathlib import Path
from typing import List, Optional, Tuple

# Constants for PS2 file system
SECTOR_SIZE = 512
APA_MAGIC = b'APA'
PFS_MAGIC = b'\x50\x46\x53\x20'  # "PFS "


class PS2HDDReader:
    """Main class for reading PS2 HDDs"""
    
    def __init__(self, device_path: str):
        self.device_path = device_path
        self.device = None
        
    def __enter__(self):
        """Open the device file"""
        try:
            self.device = open(self.device_path, 'rb')
            return self
        except PermissionError:
            print(f"Error: Permission denied. Please run with sudo.")
            sys.exit(1)
        except FileNotFoundError:
            print(f"Error: Device {self.device_path} not found.")
            sys.exit(1)
            
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close the device file"""
        if self.device:
            self.device.close()
    
    def read_sector(self, sector: int) -> bytes:
        """Read a single sector from the device"""
        self.device.seek(sector * SECTOR_SIZE)
        return self.device.read(SECTOR_SIZE)
    
    def read_sectors(self, sector: int, count: int) -> bytes:
        """Read multiple sectors from the device"""
        self.device.seek(sector * SECTOR_SIZE)
        return self.device.read(count * SECTOR_SIZE)


class APAPartition:
    """Represents an APA partition"""
    
    def __init__(self, sector: int, size: int, name: str, pfs_type: int):
        self.sector = sector
        self.size = size
        self.name = name
        self.pfs_type = pfs_type
    
    def __repr__(self):
        return f"APAPartition(name='{self.name}', sector={self.sector}, size={self.size})"


class APAParser:
    """Parser for APA (Aligned Partition Allocation) system"""
    
    def __init__(self, reader: PS2HDDReader):
        self.reader = reader
        
    def parse_mbr(self, verbose=False) -> List[APAPartition]:
        """Parse the Master Boot Record to find APA partitions"""
        partitions = []
        
        # Read MBR (sector 0)
        mbr = self.reader.read_sector(0)
        
        # Check for APA magic at offset 0x1B0
        if mbr[0x1B0:0x1B3] != APA_MAGIC:
            if verbose:
                print("Checking for PS2 formats...")
                # Check for APA in other common locations
                for offset in [0x1B0, 0x00, 0x200, 0x400]:
                    if offset < len(mbr):
                        sig = mbr[offset:offset+3]
                        if sig == APA_MAGIC:
                            print(f"Found APA magic at offset 0x{offset:X}")
                            break
                
                # Check for standard MBR partition table
                print("\nChecking standard MBR partition table...")
                for i in range(4):
                    entry_offset = 0x1BE + (i * 16)
                    if entry_offset + 16 <= len(mbr):
                        entry = mbr[entry_offset:entry_offset+16]
                        if entry[4] != 0:  # Non-empty partition
                            start = struct.unpack('<I', entry[8:12])[0]
                            size = struct.unpack('<I', entry[12:16])[0]
                            print(f"  Partition {i}: Start sector {start}, Size {size} sectors")
                            
                            # Try to read partition header
                            if start > 0 and start < 1000000:  # Sanity check
                                try:
                                    part_header = self.reader.read_sector(start)
                                    # Check for various PS2 signatures
                                    if part_header[0:3] == APA_MAGIC:
                                        print(f"    -> Found APA partition header!")
                                    elif part_header[0:4] == PFS_MAGIC:
                                        print(f"    -> Found PFS signature!")
                                    else:
                                        # Show first 64 bytes as hex
                                        hex_preview = ' '.join(f'{b:02X}' for b in part_header[:64])
                                        print(f"    -> Header preview: {hex_preview}")
                                except Exception as e:
                                    print(f"    -> Could not read partition header: {e}")
                
                # Show MBR hex dump around APA location
                print("\nMBR around APA signature location (offset 0x1B0):")
                start_hex = max(0, 0x1B0 - 32)
                end_hex = min(len(mbr), 0x1B0 + 32)
                for i in range(start_hex, end_hex, 16):
                    hex_str = ' '.join(f'{b:02X}' for b in mbr[i:i+16])
                    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in mbr[i:i+16])
                    print(f"  {i:04X}: {hex_str:<48} {ascii_str}")
            
            if not verbose:
                print("Warning: APA magic not found in MBR. This might not be a PS2 HDD.")
                print("Try running with 'diagnose' command to see more details:")
                print(f"  sudo python3 ps2_hdd_reader.py --device {self.reader.device_path} diagnose")
            return partitions
        
        # Read partition table entries (4 entries starting at 0x1BE)
        for i in range(4):
            offset = 0x1BE + (i * 16)
            entry = mbr[offset:offset+16]
            
            if entry[4] == 0:  # Empty partition
                continue
                
            # Parse partition entry
            start_sector = struct.unpack('<I', entry[8:12])[0]
            num_sectors = struct.unpack('<I', entry[12:16])[0]
            
            if start_sector == 0 or num_sectors == 0:
                continue
            
            # Read partition header to get name
            try:
                part_header = self.reader.read_sector(start_sector)
                # APA partition header structure
                if part_header[0:3] == APA_MAGIC:
                    # Name is at offset 0x10, 32 bytes
                    name = part_header[0x10:0x30].rstrip(b'\x00').decode('ascii', errors='ignore')
                    pfs_type = struct.unpack('<I', part_header[0x4:0x8])[0]
                    
                    partition = APAPartition(start_sector, num_sectors, name, pfs_type)
                    partitions.append(partition)
            except Exception as e:
                print(f"Warning: Could not read partition header at sector {start_sector}: {e}")
                continue
        
        return partitions


class PFSParser:
    """Parser for PFS (PlayStation File System)"""
    
    def __init__(self, reader: PS2HDDReader, partition: APAPartition):
        self.reader = reader
        self.partition = partition
        self.root_inode = None
        
    def parse_superblock(self) -> bool:
        """Parse the PFS superblock"""
        # PFS superblock is typically at sector 1 of the partition
        superblock = self.reader.read_sector(self.partition.sector + 1)
        
        # Check for PFS magic
        if superblock[0:4] != PFS_MAGIC:
            print(f"Warning: PFS magic not found in partition '{self.partition.name}'")
            return False
        
        # Read root inode number (offset varies, typically around 0x10-0x14)
        try:
            self.root_inode = struct.unpack('<I', superblock[0x10:0x14])[0]
            return True
        except:
            return False
    
    def read_inode(self, inode_num: int) -> Optional[dict]:
        """Read an inode from the file system"""
        # PFS inodes are typically 128 bytes
        # Inode location calculation varies by PFS version
        # This is a simplified version
        try:
            # Inodes are usually in a specific area, often starting around sector 2-3
            inode_sector = self.partition.sector + 2 + (inode_num // 4)
            inode_offset = (inode_num % 4) * 128
            
            sector_data = self.reader.read_sector(inode_sector)
            inode_data = sector_data[inode_offset:inode_offset+128]
            
            if len(inode_data) < 128:
                return None
            
            # Parse inode structure
            mode = struct.unpack('<I', inode_data[0:4])[0]
            size = struct.unpack('<I', inode_data[4:8])[0]
            
            # Read file name (typically at offset 0x20, 32 bytes)
            name = inode_data[0x20:0x40].rstrip(b'\x00').decode('ascii', errors='ignore')
            
            # Read data block pointers (simplified)
            blocks = []
            for i in range(8, 40, 4):  # First 8 direct blocks
                block = struct.unpack('<I', inode_data[i:i+4])[0]
                if block != 0:
                    blocks.append(block)
            
            return {
                'inode': inode_num,
                'mode': mode,
                'size': size,
                'name': name,
                'blocks': blocks,
                'is_dir': (mode & 0x4000) != 0
            }
        except Exception as e:
            print(f"Error reading inode {inode_num}: {e}")
            return None
    
    def list_directory(self, inode_num: int = None) -> List[dict]:
        """List files in a directory"""
        if inode_num is None:
            if self.root_inode is None:
                if not self.parse_superblock():
                    return []
                inode_num = self.root_inode
            else:
                inode_num = self.root_inode
        
        dir_inode = self.read_inode(inode_num)
        if not dir_inode or not dir_inode['is_dir']:
            return []
        
        files = []
        # Read directory entries from data blocks
        for block in dir_inode['blocks']:
            if block == 0:
                continue
            
            # Read directory block
            block_data = self.reader.read_sector(self.partition.sector + block)
            
            # Parse directory entries (simplified - actual structure is more complex)
            offset = 0
            while offset < SECTOR_SIZE - 64:
                entry_inode = struct.unpack('<I', block_data[offset:offset+4])[0]
                if entry_inode == 0:
                    break
                
                entry_name = block_data[offset+4:offset+36].rstrip(b'\x00').decode('ascii', errors='ignore')
                if entry_name:
                    entry_info = self.read_inode(entry_inode)
                    if entry_info:
                        files.append(entry_info)
                
                offset += 64  # Directory entry size (simplified)
        
        return files
    
    def extract_file(self, inode: dict, output_path: Path):
        """Extract a file from the PFS"""
        if inode['is_dir']:
            print(f"Error: {inode['name']} is a directory, not a file")
            return False
        
        try:
            with open(output_path, 'wb') as f:
                remaining = inode['size']
                for block in inode['blocks']:
                    if block == 0 or remaining <= 0:
                        break
                    
                    block_data = self.reader.read_sector(self.partition.sector + block)
                    write_size = min(SECTOR_SIZE, remaining)
                    f.write(block_data[:write_size])
                    remaining -= write_size
            
            print(f"Extracted {inode['name']} to {output_path}")
            return True
        except Exception as e:
            print(f"Error extracting file: {e}")
            return False


def list_ps2_devices() -> List[str]:
    """List potential PS2 HDD devices on macOS"""
    devices = []
    
    # Check common disk device paths
    for i in range(10):
        device_path = f"/dev/disk{i}"
        if os.path.exists(device_path):
            devices.append(device_path)
    
    return devices


def main():
    parser = argparse.ArgumentParser(
        description='Read and extract files from PS2 HDD on macOS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all partitions
  sudo python3 ps2_hdd_reader.py --device /dev/disk2 list-partitions
  
  # List files in a partition
  sudo python3 ps2_hdd_reader.py --device /dev/disk2 list-files --partition 0
  
  # Extract all files from a partition
  sudo python3 ps2_hdd_reader.py --device /dev/disk2 extract --partition 0 --output ./extracted/
  
  # Diagnose device to see what's on it
  sudo python3 ps2_hdd_reader.py --device /dev/disk2 diagnose
        """
    )
    
    parser.add_argument('--device', '-d', 
                       help='PS2 HDD device path (e.g., /dev/disk2)',
                       required=True)
    parser.add_argument('command',
                       choices=['list-partitions', 'list-files', 'extract', 'diagnose'],
                       help='Command to execute')
    parser.add_argument('--partition', '-p',
                       type=int,
                       help='Partition index (0-based)')
    parser.add_argument('--output', '-o',
                       type=str,
                       help='Output directory for extraction')
    parser.add_argument('--verbose', '-v',
                       action='store_true',
                       help='Show verbose diagnostic information')
    
    args = parser.parse_args()
    
    # Check if running as root (required for raw disk access)
    if os.geteuid() != 0:
        print("Error: This tool requires root privileges (sudo) to access raw disk devices.")
        print("Please run with: sudo python3 ps2_hdd_reader.py ...")
        sys.exit(1)
    
    with PS2HDDReader(args.device) as reader:
        # Handle diagnose command first
        if args.command == 'diagnose':
            print(f"Diagnosing device: {args.device}")
            print("=" * 60)
            print()
            
            # Get device size (macOS method)
            try:
                import subprocess
                result = subprocess.run(['diskutil', 'info', args.device],
                                      capture_output=True, text=True, check=True)
                for line in result.stdout.split('\n'):
                    if 'Total Size' in line or 'Disk Size' in line:
                        print(f"Device: {line.strip()}")
                        break
            except:
                # Try to get size by seeking to end
                try:
                    reader.device.seek(0, 2)  # Seek to end
                    size = reader.device.tell()
                    size_gb = size / (1024**3)
                    print(f"Device size: {size_gb:.2f} GB ({size} bytes)")
                    reader.device.seek(0)  # Reset to beginning
                except:
                    print("Could not determine device size")
            
            print()
            apa_parser = APAParser(reader)
            partitions = apa_parser.parse_mbr(verbose=True)
            
            if partitions:
                print(f"\nFound {len(partitions)} PS2 partition(s):")
                for i, part in enumerate(partitions):
                    print(f"  [{i}] {part.name} - Sector: {part.sector}, Size: {part.size} sectors")
            else:
                print("\nNo PS2 partitions found.")
                print("\nPossible reasons:")
                print("  1. Drive is not formatted for PS2")
                print("  2. Drive uses a different PS2 format (HDLoader, etc.)")
                print("  3. Drive is unformatted or corrupted")
                print("  4. Drive needs to be initialized on a PS2 first")
            
            return
        
        # For other commands, parse partitions normally
        apa_parser = APAParser(reader)
        partitions = apa_parser.parse_mbr(verbose=args.verbose)
        
        if not partitions:
            print("No PS2 partitions found on this device.")
            sys.exit(1)
        
        print(f"Found {len(partitions)} partition(s):")
        for i, part in enumerate(partitions):
            print(f"  [{i}] {part.name} - Sector: {part.sector}, Size: {part.size} sectors")
        
        if args.command == 'list-partitions':
            return
        
        if args.partition is None:
            print("Error: --partition is required for this command")
            sys.exit(1)
        
        if args.partition >= len(partitions):
            print(f"Error: Partition index {args.partition} out of range")
            sys.exit(1)
        
        selected_partition = partitions[args.partition]
        pfs_parser = PFSParser(reader, selected_partition)
        
        if not pfs_parser.parse_superblock():
            print(f"\nError: Could not parse PFS superblock for partition '{selected_partition.name}'")
            print("This is normal for a newly formatted drive.")
            print("The partition may need to be initialized on a PS2 console first,")
            print("or files may have been written but the directory structure isn't readable.")
            print("\nTo verify files are on the drive, try using wLaunchELF on your PS2.")
            sys.exit(1)
        
        if args.command == 'list-files':
            files = pfs_parser.list_directory()
            print(f"\nFiles in partition '{selected_partition.name}':")
            for file_info in files:
                file_type = "DIR" if file_info['is_dir'] else "FILE"
                print(f"  [{file_type}] {file_info['name']} - Size: {file_info['size']} bytes")
        
        elif args.command == 'extract':
            if args.output is None:
                print("Error: --output is required for extract command")
                sys.exit(1)
            
            output_dir = Path(args.output)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            files = pfs_parser.list_directory()
            print(f"\nExtracting files from partition '{selected_partition.name}'...")
            
            for file_info in files:
                if not file_info['is_dir']:
                    output_path = output_dir / file_info['name']
                    pfs_parser.extract_file(file_info, output_path)


if __name__ == '__main__':
    main()

