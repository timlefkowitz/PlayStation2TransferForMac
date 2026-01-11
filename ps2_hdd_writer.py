#!/usr/bin/env python3
"""
PS2 HDD Writer for macOS
A tool to write/copy files to PlayStation 2 hard drives.
"""

import os
import sys
import struct
import argparse
import zipfile
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# Import from reader
SECTOR_SIZE = 512
APA_MAGIC = b'APA'
PFS_MAGIC = b'\x50\x46\x53\x20'  # "PFS "


class PS2HDDWriter:
    """Writer for PS2 HDDs"""
    
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


def find_free_block(reader, partition_start: int, partition_size: int, start_from: int = 10) -> int:
    """Find a free block in the partition"""
    # Start checking from sector 10 (after headers and initial structures)
    for sector in range(start_from, min(start_from + 1000, partition_size)):
        try:
            data = reader.read_sector(partition_start + sector)
            # Check if sector is empty (all zeros or mostly zeros)
            if data == b'\x00' * SECTOR_SIZE or data[:4] == b'\x00\x00\x00\x00':
                return sector
        except:
            continue
    return None


def allocate_inode(reader, partition_start: int, inode_num: int) -> bool:
    """Allocate an inode slot"""
    # Inodes are typically at sector 2-3, 4 inodes per sector (128 bytes each)
    inode_sector = partition_start + 2 + (inode_num // 4)
    inode_offset = (inode_num % 4) * 128
    
    sector_data = bytearray(reader.read_sector(inode_sector))
    
    # Check if inode is already allocated
    if sector_data[inode_offset:inode_offset+4] != b'\x00\x00\x00\x00':
        return False  # Inode already in use
    
    return True


def create_inode(inode_num: int, filename: str, size: int, blocks: list, is_dir: bool = False) -> bytes:
    """Create an inode structure"""
    inode = bytearray(128)
    
    # Mode: directory flag + permissions
    mode = 0x1FF  # Standard permissions
    if is_dir:
        mode |= 0x4000  # Directory flag
    struct.pack_into('<I', inode, 0, mode)
    
    # Size
    struct.pack_into('<I', inode, 4, size)
    
    # Block pointers (first 8 direct blocks)
    for i, block in enumerate(blocks[:8]):
        struct.pack_into('<I', inode, 8 + (i * 4), block)
    
    # File name (32 bytes at offset 0x20)
    name_bytes = filename.encode('ascii', errors='ignore')[:31]
    inode[0x20:0x20+len(name_bytes)] = name_bytes
    
    # Timestamps
    now = int(datetime.now().timestamp())
    struct.pack_into('<I', inode, 0x40, now)  # Modification time
    struct.pack_into('<I', inode, 0x44, now)  # Creation time
    
    return bytes(inode)


def write_inode(reader, partition_start: int, inode_num: int, inode_data: bytes):
    """Write an inode to disk"""
    inode_sector = partition_start + 2 + (inode_num // 4)
    inode_offset = (inode_num % 4) * 128
    
    sector_data = bytearray(reader.read_sector(inode_sector))
    sector_data[inode_offset:inode_offset+128] = inode_data
    reader.write_sector(inode_sector, bytes(sector_data))


def add_directory_entry(reader, partition_start: int, dir_inode: int, file_inode: int, filename: str):
    """Add an entry to a directory"""
    # Read directory inode to find its data blocks
    dir_inode_data = reader.read_sector(partition_start + 2 + (dir_inode // 4))
    dir_inode_offset = (dir_inode % 4) * 128
    
    # Extract directory blocks (simplified - first block)
    dir_block = struct.unpack('<I', dir_inode_data[dir_inode_offset+8:dir_inode_offset+12])[0]
    
    if dir_block == 0:
        # Allocate a new block for directory
        dir_block = find_free_block(reader, partition_start, 1000000, 10)
        if dir_block is None:
            raise Exception("No free blocks available")
        
        # Update directory inode with new block
        dir_inode_bytes = bytearray(dir_inode_data[dir_inode_offset:dir_inode_offset+128])
        struct.pack_into('<I', dir_inode_bytes, 8, dir_block)
        write_inode(reader, partition_start, dir_inode, bytes(dir_inode_bytes))
    
    # Read directory block
    dir_block_data = bytearray(reader.read_sector(partition_start + dir_block))
    
    # Find empty slot (64 bytes per entry)
    entry_offset = None
    for offset in range(0, SECTOR_SIZE, 64):
        if dir_block_data[offset:offset+4] == b'\x00\x00\x00\x00':
            entry_offset = offset
            break
    
    if entry_offset is None:
        raise Exception("Directory block is full")
    
    # Write directory entry
    struct.pack_into('<I', dir_block_data, entry_offset, file_inode)
    name_bytes = filename.encode('ascii', errors='ignore')[:31]
    dir_block_data[entry_offset+4:entry_offset+4+len(name_bytes)] = name_bytes
    
    reader.write_sector(partition_start + dir_block, bytes(dir_block_data))


def extract_zip_if_needed(source_file: str) -> tuple[str, bool]:
    """Extract ZIP/7Z file if needed, return (file_path, is_temp)"""
    # Handle .zip files
    if source_file.lower().endswith('.zip'):
        print(f"Detected ZIP file: {source_file}")
        print("Extracting...")
        
        try:
            with zipfile.ZipFile(source_file, 'r') as zip_ref:
                # Look for ISO or BIN files in the ZIP (PS2 games can be either)
                game_files = [f for f in zip_ref.namelist() 
                             if f.lower().endswith('.iso') or f.lower().endswith('.bin')]
                
                if not game_files:
                    # If no ISO/BIN, extract all files to temp directory
                    print("No ISO/BIN file found in archive, extracting all files...")
                    temp_dir = tempfile.mkdtemp()
                    zip_ref.extractall(temp_dir)
                    
                    # Look for ISO/BIN in extracted files
                    extracted_files = []
                    for root, dirs, files in os.walk(temp_dir):
                        for file in files:
                            if file.lower().endswith(('.iso', '.bin')):
                                extracted_files.append(os.path.join(root, file))
                    
                    if extracted_files:
                        if len(extracted_files) == 1:
                            print(f"Found game file: {extracted_files[0]}")
                            return (extracted_files[0], True)  # Will need cleanup
                        else:
                            print(f"Found {len(extracted_files)} game files:")
                            for i, game_file in enumerate(extracted_files):
                                print(f"  [{i}] {os.path.basename(game_file)}")
                            # Use first one, or could prompt user
                            print(f"Using: {extracted_files[0]}")
                            return (extracted_files[0], True)
                    else:
                        print("Warning: No ISO/BIN files found in archive")
                        return (source_file, False)
                elif len(game_files) == 1:
                    # Extract the single game file to temp file
                    print(f"Extracting game file: {game_files[0]}")
                    temp_dir = tempfile.mkdtemp()
                    zip_ref.extract(game_files[0], temp_dir)
                    extracted_path = os.path.join(temp_dir, game_files[0])
                    return (extracted_path, True)  # Will need cleanup
                else:
                    # Multiple game files - extract first one
                    print(f"Found {len(game_files)} game files in archive:")
                    for i, game_file in enumerate(game_files):
                        print(f"  [{i}] {game_file}")
                    print(f"Extracting first one: {game_files[0]}")
                    temp_dir = tempfile.mkdtemp()
                    zip_ref.extract(game_files[0], temp_dir)
                    extracted_path = os.path.join(temp_dir, game_files[0])
                    return (extracted_path, True)
        except zipfile.BadZipFile:
            print(f"Error: {source_file} is not a valid ZIP file")
            return (source_file, False)
        except Exception as e:
            print(f"Error extracting ZIP: {e}")
            return (source_file, False)
    
    # Handle .7z files - need py7zr library or extract manually
    if source_file.lower().endswith('.7z'):
        print(f"Detected 7Z file: {source_file}")
        print("Note: 7Z extraction requires py7zr library.")
        print("Please extract the .7z file manually to get the .iso or .bin file, then transfer that.")
        print("Or install py7zr: pip install py7zr")
        return (source_file, False)
    
    return (source_file, False)


def write_file_to_ps2(device_path: str, partition_index: int, source_file: str, dest_path: str = None):
    """Write a file to the PS2 HDD"""
    # Import here to avoid circular imports
    import importlib.util
    spec = importlib.util.spec_from_file_location("ps2_hdd_reader", 
                                                  os.path.join(os.path.dirname(__file__), "ps2_hdd_reader.py"))
    reader_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader_module)
    
    PS2HDDReader = reader_module.PS2HDDReader
    APAParser = reader_module.APAParser
    
    if not os.path.exists(source_file):
        print(f"Error: Source file '{source_file}' not found.")
        return False
    
    # Extract ZIP if needed
    actual_file, is_temp = extract_zip_if_needed(source_file)
    temp_dir = None
    
    try:
        if is_temp:
            temp_dir = os.path.dirname(actual_file)
        
        if not os.path.exists(actual_file):
            print(f"Error: Extracted file '{actual_file}' not found.")
            return False
        
        if dest_path is None:
            # Use original filename but preserve extension (.iso or .bin)
            if source_file.lower().endswith(('.zip', '.7z')):
                # Keep the extension of the extracted file
                dest_path = os.path.basename(actual_file)
            else:
                dest_path = os.path.basename(actual_file)
        
        # Read source file (or extracted file)
        with open(actual_file, 'rb') as f:
            file_data = f.read()
        
        file_size = len(file_data)
        num_blocks = (file_size + SECTOR_SIZE - 1) // SECTOR_SIZE
        
        if is_temp:
            print(f"Writing file: {os.path.basename(source_file)} (extracted from ZIP)")
        else:
            print(f"Writing file: {source_file}")
        print(f"  Size: {file_size} bytes ({num_blocks} sectors)")
        print(f"  Destination: {dest_path}")
        
        with PS2HDDReader(device_path) as reader:
            # Parse partitions
            apa_parser = APAParser(reader)
            partitions = apa_parser.parse_mbr()
            
            if partition_index >= len(partitions):
                print(f"Error: Partition index {partition_index} out of range.")
                return False
            
            partition = partitions[partition_index]
            partition_start = partition.sector
        
        # Now open for writing
        with PS2HDDWriter(device_path) as writer:
            try:
                # Find free blocks for file data
                print("Allocating blocks...")
                file_blocks = []
                start_block = 10
                for i in range(num_blocks):
                    block = find_free_block(writer, partition_start, partition.size, start_block)
                    if block is None:
                        print(f"Error: Could not find free block {i+1}/{num_blocks}")
                        return False
                    file_blocks.append(block)
                    start_block = block + 1
                
                # Allocate inode (start from inode 3, 0=unused, 1=root?, 2=root)
                inode_num = 3
                while not allocate_inode(writer, partition_start, inode_num):
                    inode_num += 1
                    if inode_num > 1000:  # Safety limit
                        print("Error: Could not allocate inode")
                        return False
                
                print(f"Allocated inode: {inode_num}")
                
                # Write file data to blocks
                print("Writing file data...")
                for i, block in enumerate(file_blocks):
                    block_data = bytearray(SECTOR_SIZE)
                    offset = i * SECTOR_SIZE
                    chunk = file_data[offset:offset+SECTOR_SIZE]
                    block_data[:len(chunk)] = chunk
                    writer.write_sector(partition_start + block, bytes(block_data))
                
                # Create and write inode
                print("Creating inode...")
                inode_data = create_inode(inode_num, dest_path, file_size, file_blocks, is_dir=False)
                write_inode(writer, partition_start, inode_num, inode_data)
                
                # Add to root directory (inode 2)
                print("Adding to directory...")
                add_directory_entry(writer, partition_start, 2, inode_num, dest_path)
                
                print(f"\n✓ File written successfully!")
                print(f"  Inode: {inode_num}")
                print(f"  Blocks: {file_blocks[:5]}{'...' if len(file_blocks) > 5 else ''}")
                
                return True
            except Exception as e:
                print(f"Error writing file: {e}")
                import traceback
                traceback.print_exc()
                return False
            finally:
                # Clean up temp directory if we extracted a ZIP
                if is_temp and temp_dir and os.path.exists(temp_dir):
                    try:
                        shutil.rmtree(temp_dir)
                        print(f"Cleaned up temporary files")
                    except:
                        pass
    except Exception as e:
        print(f"Error in file transfer: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Write files to PS2 HDD on macOS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Write a single file
  sudo python3 ps2_hdd_writer.py --device /dev/disk4 --partition 0 --file ./myfile.iso
  
  # Write a file with custom destination name
  sudo python3 ps2_hdd_writer.py --device /dev/disk4 --partition 0 --file ./game.iso --dest "GAME.ISO"
        """
    )
    
    parser.add_argument('--device', '-d',
                       required=True,
                       help='PS2 HDD device path (e.g., /dev/disk4)')
    parser.add_argument('--partition', '-p',
                       type=int,
                       default=0,
                       help='Partition index (default: 0)')
    parser.add_argument('--file', '-f',
                       required=True,
                       help='Source file to write')
    parser.add_argument('--dest', '-o',
                       help='Destination filename on PS2 (default: same as source)')
    
    args = parser.parse_args()
    
    # Check if running as root
    if os.geteuid() != 0:
        print("Error: This tool requires root privileges (sudo) to write to disk devices.")
        print("Please run with: sudo python3 ps2_hdd_writer.py ...")
        sys.exit(1)
    
    # Import here to avoid circular imports
    success = write_file_to_ps2(args.device, args.partition, args.file, args.dest)
    
    if not success:
        sys.exit(1)


if __name__ == '__main__':
    main()

