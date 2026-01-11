# PS2 HDD Reader for macOS

A Python tool to read and extract files from PlayStation 2 hard drives on macOS.

## Overview

This tool suite allows you to:
- Detect and list PS2 partitions on a connected HDD
- Browse files within PS2 partitions
- Extract files from PS2 HDDs to your Mac
- Write/transfer files to PS2 HDDs from your Mac
- Format drives for PS2 use
- **GUI application with drag-and-drop support** (see below)

## Requirements

- macOS
- Python 3.6 or higher
- Root/sudo access (required for raw disk access)
- PS2 HDD/SSD connected via USB (IDE-to-USB adapter, SATA-to-USB, or direct USB connection)

## Installation

1. Clone or download this repository
2. No additional Python packages are required (uses only standard library)

## Usage

### Step 1: Connect Your PS2 HDD/SSD

Connect your PS2 HDD or SSD to your Mac via USB. This can be:
- Direct USB connection (if your drive has USB)
- IDE-to-USB adapter
- SATA-to-USB adapter

Make sure macOS recognizes the device (it should appear in Disk Utility or when you run `diskutil list`).

### Step 2: Identify the Device

You can use the included detection script to help identify your PS2 HDD:

```bash
python3 detect_ps2_devices.py
```

Or manually list all connected disks:

```bash
diskutil list
```

Look for your PS2 HDD in the list. It will typically appear as `/dev/disk2`, `/dev/disk3`, etc. Note the device identifier.

**Important:** Make sure you identify the correct device! Using the wrong device could damage your data.

### Step 3: List Partitions

First, list all partitions on the PS2 HDD:

```bash
sudo python3 ps2_hdd_reader.py --device /dev/disk2 list-partitions
```

Replace `/dev/disk2` with your actual device path.

### Step 4: List Files in a Partition

To see what files are in a specific partition:

```bash
sudo python3 ps2_hdd_reader.py --device /dev/disk2 list-files --partition 0
```

Replace `0` with the partition index you want to browse.

### Step 5: Extract Files

To extract all files from a partition to a directory:

```bash
sudo python3 ps2_hdd_reader.py --device /dev/disk2 extract --partition 0 --output ./extracted_files/
```

This will create the output directory if it doesn't exist and extract all files from the specified partition.

### Step 6: Transfer Files to PS2 HDD

To write/copy files to your PS2 HDD:

```bash
sudo python3 ps2_hdd_writer.py --device /dev/disk2 --partition 0 --file ./myfile.iso
```

Or specify a custom destination filename:

```bash
sudo python3 ps2_hdd_writer.py --device /dev/disk2 --partition 0 --file ./game.iso --dest "GAME.ISO"
```

This will write the file to the PS2 partition and make it accessible on your PS2 console.

## Examples

```bash
# List all partitions
sudo python3 ps2_hdd_reader.py -d /dev/disk2 list-partitions

# Browse files in partition 0
sudo python3 ps2_hdd_reader.py -d /dev/disk2 list-files -p 0

# Extract all files from partition 1 to ./my_files/
sudo python3 ps2_hdd_reader.py -d /dev/disk2 extract -p 1 -o ./my_files/
```

## Important Notes

⚠️ **WARNING:**
- This tool requires **sudo/root access** to read raw disk devices
- **Always double-check** the device path before running commands
- Using the wrong device could result in **data loss**
- This tool is **read-only** - it will not modify your PS2 HDD
- Make sure your PS2 HDD is properly connected and recognized by macOS

## How It Works

The tool implements parsers for:
- **APA (Aligned Partition Allocation)**: The partition system used by PS2
- **PFS (PlayStation File System)**: The file system format used within PS2 partitions

It reads the raw disk sectors and interprets the PS2-specific data structures to extract files.

## Formatting a PS2 HDD/SSD

If your drive is unformatted or you need to format it for PS2 use, you can use the included formatter:

```bash
sudo python3 ps2_hdd_formatter.py --device /dev/disk4
```

**WARNING:** This will **ERASE ALL DATA** on the drive!

The formatter will:
- Create an APA Master Boot Record
- Initialize a PS2 partition
- Set up a basic PFS file system structure

After formatting, you may still need to use wLaunchELF or the PS2 HDD Utility Disc on your PS2 console to create additional partitions or complete the setup.

**Note:** After formatting, macOS will show a message saying the device is "not readable" - this is **normal and expected**! macOS cannot read PS2 file systems, but your PS2 console will be able to use it. You can verify the format worked by running the reader tool to list partitions.

## Web GUI Application (Recommended)

For a user-friendly web-based interface with drag-and-drop support:

```bash
sudo python3 ps2_hdd_web_gui.py
```

This will:
- Start a local web server on `http://localhost:8080`
- Automatically open your web browser
- Provide a modern, drag-and-drop interface

The Web GUI provides:
- **Visual file browser** - See all files and folders on your PS2 HDD in a table
- **True drag-and-drop** - Drag files from Finder directly into the browser
- **Device detection** - Automatically find your PS2 HDD
- **Partition management** - View and select partitions
- **Real-time status log** - See what's happening as it happens
- **File selection** - Click to select files or drag multiple files at once

**Note:** The web GUI requires sudo for full functionality. Some operations may work without sudo, but writing to the drive requires root privileges.

**Alternative:** If you prefer a desktop GUI, you can install tkinter:
```bash
brew install python-tk
```
Then use: `sudo python3 ps2_hdd_gui.py`

## Limitations

- This is a simplified implementation. The actual PFS structure can be more complex depending on the PS2 software version
- Some advanced PFS features may not be fully supported
- Large files spanning many blocks may have incomplete extraction
- Directory traversal is simplified and may not work for deeply nested structures
- The formatter creates a basic structure; you may need additional PS2 tools for full functionality

## Troubleshooting

**"Permission denied" error:**
- Make sure you're running with `sudo`

**"Device not found" error:**
- Verify the device path with `diskutil list`
- Make sure the HDD/SSD is properly connected via USB
- Check that macOS recognizes the device in Disk Utility
- Some USB adapters may not work - try a different adapter or cable

**"No PS2 partitions found":**
- The HDD might not be formatted for PS2
- The HDD might be using a different format
- Try checking if the device is recognized: `diskutil info /dev/diskX`

## Legal Notice

This tool is for personal use only. Ensure that you own the PS2 HDD and that transferring data complies with applicable laws and regulations.

## License

This tool is provided as-is for educational and personal use.

# PlayStation2TransferForMac
