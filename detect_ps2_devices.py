#!/usr/bin/env python3
"""
Helper script to detect potential PS2 HDD devices on macOS
"""

import os
import subprocess
import sys

def get_disk_info():
    """Get information about all connected disks"""
    try:
        result = subprocess.run(['diskutil', 'list'], 
                              capture_output=True, 
                              text=True, 
                              check=True)
        return result.stdout
    except subprocess.CalledProcessError:
        return None

def check_ps2_device(device_path):
    """Check if a device might be a PS2 HDD"""
    if not os.path.exists(device_path):
        return False
    
    try:
        with open(device_path, 'rb') as f:
            # Read MBR
            mbr = f.read(512)
            
            # Check for APA magic at offset 0x1B0
            if mbr[0x1B0:0x1B3] == b'APA':
                return True
    except (PermissionError, IOError):
        # Can't read without sudo
        return None
    
    return False

def main():
    print("PS2 HDD Device Detector for macOS")
    print("=" * 40)
    print()
    
    # Show diskutil list output
    disk_info = get_disk_info()
    if disk_info:
        print("Connected disks:")
        print(disk_info)
        print()
    
    print("Checking for PS2 HDDs (requires sudo for full detection)...")
    print()
    
    potential_devices = []
    external_devices = []
    
    for i in range(10):
        device_path = f"/dev/disk{i}"
        if os.path.exists(device_path):
            result = check_ps2_device(device_path)
            if result is True:
                print(f"✓ {device_path} - PS2 HDD detected!")
                potential_devices.append(device_path)
            elif result is None:
                print(f"? {device_path} - Cannot check (needs sudo)")
                # Check if it's an external drive
                if disk_info and f"disk{i}" in disk_info and "external" in disk_info.lower():
                    external_devices.append(device_path)
            else:
                # Check if it's an external drive that might be the PS2 drive
                if disk_info and f"disk{i}" in disk_info:
                    disk_lines = [line for line in disk_info.split('\n') if f"disk{i}" in line]
                    if disk_lines and ("external" in disk_lines[0].lower() or "physical" in disk_lines[0].lower()):
                        external_devices.append(device_path)
                        print(f"  {device_path} - External drive (might be PS2 - try with sudo)")
                    else:
                        print(f"  {device_path} - Not a PS2 HDD")
    
    print()
    if potential_devices:
        print("✓ PS2 HDDs found:")
        for dev in potential_devices:
            print(f"  - {dev}")
        print()
        print("To use with ps2_hdd_reader.py:")
        print(f"  sudo python3 ps2_hdd_reader.py --device {potential_devices[0]} list-partitions")
    elif external_devices:
        print("⚠ External drive(s) detected that might be your PS2 HDD:")
        for dev in external_devices:
            print(f"  - {dev}")
        print()
        print("These drives need sudo to read properly. Try running:")
        print(f"  sudo python3 ps2_hdd_reader.py --device {external_devices[0]} list-partitions")
        print()
        print("Or run this detection script with sudo:")
        print("  sudo python3 detect_ps2_devices.py")
    else:
        print("No PS2 HDDs detected.")
        print("Make sure:")
        print("  1. Your PS2 HDD/SSD is connected via USB")
        print("  2. macOS recognizes the device (check Disk Utility)")
        print("  3. Run this script with sudo for better detection:")
        print("     sudo python3 detect_ps2_devices.py")

if __name__ == '__main__':
    main()

