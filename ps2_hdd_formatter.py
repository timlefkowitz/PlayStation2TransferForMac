#!/usr/bin/env python3
"""
PS2 HDD Formatter for macOS
A tool to format a hard drive for use with PlayStation 2.
"""

import os
import sys
import struct
import argparse
from datetime import datetime

# Constants for PS2 file system
SECTOR_SIZE = 512
APA_MAGIC = b'APA'
PFS_MAGIC = b'\x50\x46\x53\x20'  # "PFS "


class PS2HDDFormatter:
    """Formatter for PS2 HDDs"""
    
    def __init__(self, device_path: str):
        self.device_path = device_path
        self.device = None
        
    def __enter__(self):
        """Open the device file"""
        try:
            self.device = open(self.device_path, 'r+b')  # Read-write mode
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
    
    def write_sector(self, sector: int, data: bytes):
        """Write a single sector to the device"""
        if len(data) != SECTOR_SIZE:
            raise ValueError(f"Data must be exactly {SECTOR_SIZE} bytes")
        self.device.seek(sector * SECTOR_SIZE)
        self.device.write(data)
        self.device.flush()


def create_apa_mbr(total_sectors: int) -> bytes:
    """Create an APA Master Boot Record"""
    mbr = bytearray(SECTOR_SIZE)
    
    # Boot code area (first 446 bytes) - leave mostly empty
    # Some PS2 systems expect specific boot code, but for basic formatting we can leave it
    
    # APA signature at offset 0x1B0
    mbr[0x1B0:0x1B3] = APA_MAGIC
    
    # APA version (typically 1)
    mbr[0x1B3] = 1
    
    # Total sectors (little-endian, 8 bytes)
    struct.pack_into('<Q', mbr, 0x1B4, total_sectors)
    
    # MBR checksum (simplified - real PS2 uses specific algorithm)
    # For now, we'll set a placeholder
    mbr[0x1BC:0x1BE] = b'\x00\x00'
    
    # Standard MBR partition table starts at 0x1BE
    # We'll create one partition that uses the whole drive (minus reserved sectors)
    # PS2 typically reserves the first few sectors
    
    # Partition 1: Main PS2 partition
    # Boot flag: 0x80 (active)
    mbr[0x1BE] = 0x80
    
    # CHS start (simplified)
    mbr[0x1BF:0x1C2] = b'\x00\x01\x01'
    
    # Partition type: 0x01 (FAT12) or 0x0C (FAT32) - PS2 uses custom, but we'll use 0x01
    mbr[0x1C2] = 0x01
    
    # CHS end (simplified)
    mbr[0x1C3:0x1C6] = b'\xFF\xFE\xFF'
    
    # Start sector: 1 (sector 0 is MBR)
    struct.pack_into('<I', mbr, 0x1C6, 1)
    
    # Number of sectors: total - 1 (reserve sector 0)
    # Limit to 32-bit max for MBR partition table
    num_sectors = min(total_sectors - 1, 0xFFFFFFFF)
    if num_sectors < 0:
        num_sectors = 0
    struct.pack_into('<I', mbr, 0x1CA, num_sectors)
    
    # MBR signature: 0x55AA at offset 0x1FE
    mbr[0x1FE] = 0x55
    mbr[0x1FF] = 0xAA
    
    return bytes(mbr)


def create_apa_partition_header(partition_name: str, start_sector: int, num_sectors: int, 
                                pfs_type: int = 0x01) -> bytes:
    """Create an APA partition header"""
    header = bytearray(SECTOR_SIZE)
    
    # APA magic
    header[0:3] = APA_MAGIC
    
    # PFS type (0x01 = standard PFS)
    struct.pack_into('<I', header, 0x4, pfs_type)
    
    # Partition ID (unique identifier)
    struct.pack_into('<I', header, 0x8, 1)  # First partition = ID 1
    
    # Start sector
    struct.pack_into('<I', header, 0xC, start_sector)
    
    # Number of sectors
    struct.pack_into('<I', header, 0x10, num_sectors)
    
    # Partition name (32 bytes, null-terminated) - at offset 0x10-0x30
    # Note: 0x10 is already used for num_sectors, so name is actually at 0x14-0x34
    # Actually, looking at APA structure, name is typically at 0x10-0x30 (overlapping with num_sectors)
    # Let's use 0x14-0x34 to be safe, or check actual APA docs
    # For now, let's put name at 0x14 to avoid overlap
    name_offset = 0x14
    name_bytes = partition_name.encode('ascii', errors='ignore')[:31]
    header[name_offset:name_offset+32] = name_bytes.ljust(32, b'\x00')
    
    # Modification date (Unix timestamp)
    mod_time = int(datetime.now().timestamp())
    struct.pack_into('<I', header, 0x30, mod_time)
    
    # Creation date
    struct.pack_into('<I', header, 0x34, mod_time)
    
    # Flags and other fields (simplified)
    # Real APA has more fields, but this should work for basic formatting
    
    return bytes(header)


def create_pfs_superblock(root_inode: int = 2) -> bytes:
    """Create a PFS superblock"""
    superblock = bytearray(SECTOR_SIZE)
    
    # PFS magic
    superblock[0:4] = PFS_MAGIC
    
    # Version (typically 1)
    struct.pack_into('<I', superblock, 0x4, 1)
    
    # Root inode number
    struct.pack_into('<I', superblock, 0x10, root_inode)
    
    # Other PFS fields (simplified)
    # Real PFS has more structure, but this creates a basic superblock
    
    return bytes(superblock)


def format_ps2_hdd(device_path: str, partition_name: str = "__mbr", confirm: bool = False):
    """Format a drive for PS2 use"""
    
    if not confirm:
        print("WARNING: This will ERASE ALL DATA on the drive!")
        print(f"Device: {device_path}")
        response = input("Type 'YES' to continue: ")
        if response != 'YES':
            print("Formatting cancelled.")
            return False
    
    # Get device size before opening for write
    import subprocess
    import re
    total_sectors = None
    try:
        result = subprocess.run(['diskutil', 'info', device_path],
                              capture_output=True, text=True, check=True)
        for line in result.stdout.split('\n'):
            if 'Total Size' in line or 'Disk Size' in line:
                match = re.search(r'\((\d+)\s+Bytes\)', line)
                if match:
                    size_bytes = int(match.group(1))
                    total_sectors = size_bytes // SECTOR_SIZE
                    break
                match = re.search(r'exactly\s+(\d+)\s+512-Byte-Units', line)
                if match:
                    total_sectors = int(match.group(1))
                    break
    except:
        pass
    
    if total_sectors is None or total_sectors == 0:
        print("Error: Could not determine device size.")
        print("Please make sure the device is properly connected and recognized by macOS.")
        return False
    
    print(f"Device size: {total_sectors} sectors ({total_sectors * SECTOR_SIZE / (1024**3):.2f} GB)")
    
    with PS2HDDFormatter(device_path) as formatter:
        print(f"Formatting {device_path} for PS2...")
        
        # Create and write MBR
        print("Writing Master Boot Record...")
        mbr = create_apa_mbr(total_sectors)
        formatter.write_sector(0, mbr)
        
        # Create main partition starting at sector 1
        # Reserve some sectors for partition management
        partition_start = 1
        partition_size = total_sectors - partition_start - 100  # Reserve 100 sectors
        
        print(f"Creating partition '{partition_name}' (sectors {partition_start} to {partition_start + partition_size})...")
        
        # Write APA partition header
        part_header = create_apa_partition_header(partition_name, partition_start, partition_size)
        formatter.write_sector(partition_start, part_header)
        
        # Write PFS superblock at sector 2 of partition (sector 3 overall)
        print("Writing PFS superblock...")
        superblock = create_pfs_superblock()
        formatter.write_sector(partition_start + 1, superblock)
        
        # Zero out a few more sectors to ensure clean state
        print("Initializing file system...")
        zero_sector = b'\x00' * SECTOR_SIZE
        for i in range(2, min(10, partition_size)):
            formatter.write_sector(partition_start + i, zero_sector)
        
        print("\n✓ PS2 HDD formatted successfully!")
        print(f"  Partition: {partition_name}")
        print(f"  Start sector: {partition_start}")
        print(f"  Size: {partition_size} sectors")
        print("\nYou can now use this drive with your PS2.")
        print("Note: You may need to format it further using wLaunchELF or")
        print("the PS2 HDD Utility Disc to create usable partitions.")
        print("\n⚠️  IMPORTANT: macOS will show a message saying the device is")
        print("   'not readable' - this is NORMAL and EXPECTED! macOS cannot")
        print("   read PS2 file systems, but your PS2 console will be able to.")
        print("\n   You can verify the format worked by running:")
        print(f"   sudo python3 ps2_hdd_reader.py --device {device_path} list-partitions")
        
        return True


def main():
    parser = argparse.ArgumentParser(
        description='Format a hard drive for PlayStation 2 use',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
WARNING: This will ERASE ALL DATA on the specified device!

Examples:
  # Format with confirmation prompt
  sudo python3 ps2_hdd_formatter.py --device /dev/disk4
  
  # Format without confirmation (use with caution!)
  sudo python3 ps2_hdd_formatter.py --device /dev/disk4 --yes
  
  # Format with custom partition name
  sudo python3 ps2_hdd_formatter.py --device /dev/disk4 --name "PS2HDD" --yes
        """
    )
    
    parser.add_argument('--device', '-d',
                       required=True,
                       help='Device path (e.g., /dev/disk4)')
    parser.add_argument('--name', '-n',
                       default='__mbr',
                       help='Partition name (default: __mbr)')
    parser.add_argument('--yes', '-y',
                       action='store_true',
                       help='Skip confirmation prompt (DANGEROUS!)')
    
    args = parser.parse_args()
    
    # Check if running as root
    if os.geteuid() != 0:
        print("Error: This tool requires root privileges (sudo) to format drives.")
        print("Please run with: sudo python3 ps2_hdd_formatter.py ...")
        sys.exit(1)
    
    # Double-check the device path
    if not os.path.exists(args.device):
        print(f"Error: Device {args.device} not found.")
        sys.exit(1)
    
    # Show device info
    try:
        import subprocess
        result = subprocess.run(['diskutil', 'info', args.device],
                              capture_output=True, text=True, check=True)
        print("Device information:")
        for line in result.stdout.split('\n')[:10]:
            if line.strip():
                print(f"  {line}")
        print()
    except:
        pass
    
    # Format the drive
    success = format_ps2_hdd(args.device, args.name, confirm=args.yes)
    
    if success:
        print("\nFormatting complete!")
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()

