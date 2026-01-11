#!/usr/bin/env python3
"""
PS2 HDD Manager - Web GUI
A web-based graphical interface for managing PS2 HDDs with drag-and-drop support.
"""

import os
import sys
import json
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import threading
import subprocess
import webbrowser
import time

# Try to import the reader/writer modules
reader_module = None
writer_module = None

def load_modules():
    """Load the reader and writer modules"""
    global reader_module, writer_module
    
    if reader_module is not None:
        return  # Already loaded
    
    try:
        import importlib.util
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Load reader module
        reader_path = os.path.join(script_dir, "ps2_hdd_reader.py")
        if not os.path.exists(reader_path):
            print(f"✗ Reader module not found at {reader_path}")
            print(f"  Current directory: {os.getcwd()}")
            print(f"  Script directory: {script_dir}")
            return
        
        try:
            spec_reader = importlib.util.spec_from_file_location("ps2_hdd_reader", reader_path)
            if spec_reader is None:
                print(f"✗ Failed to create spec for {reader_path}")
                return
            
            reader_module = importlib.util.module_from_spec(spec_reader)
            if spec_reader.loader is None:
                print(f"✗ No loader for {reader_path}")
                return
            
            spec_reader.loader.exec_module(reader_module)
            print(f"✓ Loaded reader module from {reader_path}")
        except Exception as e:
            import traceback
            print(f"✗ Error loading reader module: {e}")
            print(traceback.format_exc())
            reader_module = None
        
        # Load writer module
        writer_path = os.path.join(script_dir, "ps2_hdd_writer.py")
        if os.path.exists(writer_path):
            try:
                spec_writer = importlib.util.spec_from_file_location("ps2_hdd_writer", writer_path)
                if spec_writer and spec_writer.loader:
                    writer_module = importlib.util.module_from_spec(spec_writer)
                    spec_writer.loader.exec_module(writer_module)
                    print(f"✓ Loaded writer module from {writer_path}")
                else:
                    print(f"✗ Failed to create spec for writer module")
            except Exception as e:
                print(f"✗ Error loading writer module: {e}")
                writer_module = None
        else:
            print(f"✗ Writer module not found at {writer_path}")
            
    except Exception as e:
        import traceback
        print(f"Error importing modules: {e}")
        print(traceback.format_exc())
        reader_module = None
        writer_module = None

# Load modules on import
load_modules()


HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>PS2 HDD Manager</title>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 20px;
        }
        h1 {
            color: #333;
            margin-bottom: 20px;
        }
        .section {
            margin-bottom: 30px;
            padding: 15px;
            background: #f9f9f9;
            border-radius: 5px;
        }
        .section h2 {
            margin-bottom: 15px;
            color: #555;
            font-size: 18px;
        }
        select, button {
            padding: 10px 15px;
            font-size: 14px;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin: 5px;
        }
        button {
            background: #007AFF;
            color: white;
            border: none;
            cursor: pointer;
        }
        button:hover {
            background: #0056CC;
        }
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .drop-zone {
            border: 3px dashed #007AFF;
            border-radius: 8px;
            padding: 40px;
            text-align: center;
            background: #f0f7ff;
            cursor: pointer;
            transition: all 0.3s;
        }
        .drop-zone:hover {
            background: #e0efff;
            border-color: #0056CC;
        }
        .drop-zone.dragover {
            background: #d0e7ff;
            border-color: #003d99;
        }
        #file-input {
            display: none;
        }
        .file-list {
            margin-top: 20px;
            max-height: 300px;
            overflow-y: auto;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 10px;
        }
        .file-item {
            padding: 8px;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
        }
        .file-item:last-child {
            border-bottom: none;
        }
        .log {
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 15px;
            border-radius: 4px;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 12px;
            max-height: 200px;
            overflow-y: auto;
            white-space: pre-wrap;
        }
        .status {
            padding: 10px;
            margin: 10px 0;
            border-radius: 4px;
        }
        .status.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .status.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .status.info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        th, td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background: #f8f9fa;
            font-weight: 600;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎮 PS2 HDD Manager</h1>
        
        <div class="section">
            <h2>Device Selection</h2>
            <select id="device-select">
                <option value="">Loading devices...</option>
            </select>
            <button onclick="refreshDevices()">Refresh</button>
            <button onclick="detectDevices()">Detect PS2 HDDs</button>
        </div>
        
        <div class="section">
            <h2>Partition Selection</h2>
            <select id="partition-select">
                <option value="">Select device first</option>
            </select>
            <button onclick="refreshFiles()">Refresh Files</button>
        </div>
        
        <div class="section">
            <h2>PS2 HDD Files</h2>
            <div id="files-container">
                <p>Select a partition to view files</p>
            </div>
        </div>
        
        <div class="section">
            <h2>Transfer Files</h2>
            <div class="drop-zone" id="drop-zone" onclick="document.getElementById('file-input').click()">
                <p style="font-size: 18px; margin-bottom: 10px;">📁 Drag & Drop Files Here</p>
                <p style="color: #666;">or click to select files</p>
            </div>
            <input type="file" id="file-input" multiple>
            <div id="file-list" class="file-list" style="display: none;"></div>
            <button onclick="transferFiles()" id="transfer-btn" disabled>Transfer Files</button>
        </div>
        
        <div class="section">
            <h2>Status Log</h2>
            <div id="log" class="log">Ready...\n</div>
        </div>
    </div>
    
    <script>
        let selectedFiles = [];
        let currentDevice = '';
        let currentPartition = -1;
        
        // Initialize
        window.onload = function() {
            refreshDevices();
            setupDragDrop();
        };
        
        function setupDragDrop() {
            const dropZone = document.getElementById('drop-zone');
            const fileInput = document.getElementById('file-input');
            
            dropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropZone.classList.add('dragover');
            });
            
            dropZone.addEventListener('dragleave', () => {
                dropZone.classList.remove('dragover');
            });
            
            dropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropZone.classList.remove('dragover');
                handleFiles(e.dataTransfer.files);
            });
            
            fileInput.addEventListener('change', (e) => {
                handleFiles(e.target.files);
            });
        }
        
        function handleFiles(files) {
            selectedFiles = Array.from(files);
            const fileList = document.getElementById('file-list');
            const transferBtn = document.getElementById('transfer-btn');
            
            if (selectedFiles.length > 0) {
                fileList.style.display = 'block';
                fileList.innerHTML = selectedFiles.map(f => 
                    `<div class="file-item">
                        <span>${f.name}</span>
                        <span>${(f.size / 1024 / 1024).toFixed(2)} MB</span>
                    </div>`
                ).join('');
                transferBtn.disabled = false;
                log(`Selected ${selectedFiles.length} file(s)`);
            }
        }
        
        function log(message) {
            const logDiv = document.getElementById('log');
            const time = new Date().toLocaleTimeString();
            logDiv.textContent += `[${time}] ${message}\n`;
            logDiv.scrollTop = logDiv.scrollHeight;
        }
        
        async function refreshDevices() {
            try {
                const response = await fetch('/api/devices');
                const data = await response.json();
                const select = document.getElementById('device-select');
                select.innerHTML = '<option value="">Select device...</option>';
                data.devices.forEach(dev => {
                    const option = document.createElement('option');
                    option.value = dev.path;
                    option.textContent = `${dev.path} (${dev.name})`;
                    select.appendChild(option);
                });
                select.addEventListener('change', onDeviceSelected);
            } catch (e) {
                log('Error loading devices: ' + e);
            }
        }
        
        function onDeviceSelected() {
            const select = document.getElementById('device-select');
            currentDevice = select.value;
            if (currentDevice) {
                log(`Selected device: ${currentDevice}`);
                loadPartitions(currentDevice);
            }
        }
        
        async function loadPartitions(device) {
            try {
                log('Loading partitions...');
                log('Device path: ' + device);
                const response = await fetch(`/api/partitions?device=${encodeURIComponent(device)}`);
                const data = await response.json();
                const select = document.getElementById('partition-select');
                select.innerHTML = '<option value="">Select partition...</option>';
                
                if (data.error) {
                    log('Error: ' + data.error);
                    if (data.details) {
                        console.error('Details:', data.details);
                    }
                    select.innerHTML = `<option value="">Error: ${data.error}</option>`;
                } else if (data.partitions && data.partitions.length > 0) {
                    data.partitions.forEach((part, idx) => {
                        const option = document.createElement('option');
                        option.value = idx;
                        option.textContent = `[${idx}] ${part.name} (${part.size} sectors)`;
                        select.appendChild(option);
                    });
                    select.addEventListener('change', onPartitionSelected);
                    log(`Found ${data.partitions.length} partition(s)`);
                } else {
                    log('No partitions found. The drive may not be formatted for PS2.');
                    log('Try running: sudo python3 ps2_hdd_formatter.py --device ' + device);
                    select.innerHTML = '<option value="">No partitions found</option>';
                }
            } catch (e) {
                log('Error loading partitions: ' + e);
            }
        }
        
        function onPartitionSelected() {
            const select = document.getElementById('partition-select');
            currentPartition = parseInt(select.value);
            if (currentPartition >= 0) {
                refreshFiles();
            }
        }
        
        async function refreshFiles() {
            if (currentDevice && currentPartition >= 0) {
                try {
                    log('Loading files...');
                    const container = document.getElementById('files-container');
                    container.innerHTML = '<p>Loading files...</p>';
                    
                    const response = await fetch(`/api/files?device=${encodeURIComponent(currentDevice)}&partition=${currentPartition}`);
                    const data = await response.json();
                    
                    if (data.error) {
                        log('Error: ' + data.error);
                        container.innerHTML = `<p style="color: red;">Error: ${data.error}</p>`;
                        return;
                    }
                    
                    if (data.files && data.files.length > 0) {
                        container.innerHTML = `
                            <table>
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Size</th>
                                        <th>Type</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${data.files.map(f => `
                                        <tr>
                                            <td>${f.name}</td>
                                            <td>${f.is_dir ? '-' : formatBytes(f.size)}</td>
                                            <td>${f.is_dir ? 'DIR' : 'FILE'}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        `;
                        log(`✓ Found ${data.files.length} file(s)`);
                    } else {
                        container.innerHTML = '<p>No files found. Files may take a moment to appear after transfer.</p>';
                        log('No files found (this is normal for a newly formatted drive)');
                    }
                } catch (e) {
                    log('✗ Error loading files: ' + e);
                    document.getElementById('files-container').innerHTML = `<p style="color: red;">Error: ${e}</p>`;
                }
            }
        }
        
        function formatBytes(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
        }
        
        async function transferFiles() {
            if (!currentDevice || currentPartition < 0) {
                alert('Please select a device and partition first');
                return;
            }
            
            if (selectedFiles.length === 0) {
                alert('Please select files to transfer');
                return;
            }
            
            log(`Preparing to transfer ${selectedFiles.length} file(s)...`);
            
            // Show instructions for command-line transfer
            const fileList = selectedFiles.map(f => `  - ${f.name} (${formatBytes(f.size)})`).join('\\n');
            const command = `sudo python3 ps2_hdd_writer.py --device ${currentDevice} --partition ${currentPartition} --file`;
            
            const message = `To transfer files, use the command line:\\n\\n${command} <file_path>\\n\\n\\nSelected files:\\n${fileList}\\n\\n\\nExample:\\n${command} "/path/to/${selectedFiles[0].name}"\\n\\n\\nNote: The web GUI file transfer is being improved. For now, use the command line tool for reliable transfers.`;
            
            alert(message);
            
            log('File transfer instructions shown.');
            log(`Command template: ${command} <file_path>`);
            log(`Selected ${selectedFiles.length} file(s) - see alert for details`);
            
            // Clear selection
            selectedFiles = [];
            document.getElementById('file-list').style.display = 'none';
            document.getElementById('transfer-btn').disabled = true;
        }
        
        async function detectDevices() {
            log('Running device detection...');
            try {
                const response = await fetch('/api/detect');
                const data = await response.json();
                log(data.message);
                refreshDevices();
            } catch (e) {
                log('Error: ' + e);
            }
        }
    </script>
</body>
</html>
"""


class PS2HDDHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode())
        elif self.path.startswith('/api/'):
            self.handle_api()
        else:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == '/api/transfer' or self.path == '/api/transfer-file':
            # File transfer via web GUI not fully implemented
            # Just return a helpful message without trying to read the file
            self.send_json({
                'success': False,
                'error': 'File transfer via web GUI is not yet fully implemented. Please use the command line tool.',
                'command': 'sudo python3 ps2_hdd_writer.py --device /dev/disk4 --partition 0 --file <your_file>'
            })
        else:
            self.send_error(404)
    
    def handle_api(self):
        path = self.path.split('?')[0]
        params = {}
        if '?' in self.path:
            query = self.path.split('?')[1]
            # Properly decode URL parameters
            import urllib.parse
            # Parse query string
            parsed = urllib.parse.parse_qs(query)
            # Decode each parameter value
            params = {}
            for k, v in parsed.items():
                if isinstance(v, list) and len(v) > 0:
                    params[k] = urllib.parse.unquote(v[0])
                else:
                    params[k] = urllib.parse.unquote(str(v))
            
            # Debug: log the decoded device path
            if 'device' in params:
                print(f"DEBUG: Decoded device path: {params['device']}")
        
        if path == '/api/devices':
            self.send_json(self.get_devices())
        elif path == '/api/partitions':
            device = params.get('device', '')
            self.send_json(self.get_partitions(device))
        elif path == '/api/files':
            device = params.get('device', '')
            partition = int(params.get('partition', '-1'))
            self.send_json(self.get_files(device, partition))
        elif path == '/api/detect':
            self.send_json(self.detect_devices())
        else:
            self.send_error(404)
    
    def handle_transfer(self):
        try:
            content_type = self.headers.get('Content-Type', '')
            if not content_type.startswith('multipart/form-data'):
                self.send_error(400)
                return
            
            # Get content length
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_json({'success': False, 'error': 'No data received'})
                return
            
            # For now, use command-line tool for file transfer
            # Full multipart parsing is complex, so we'll use a simpler approach
            self.send_json({
                'success': False, 
             'error': 'File transfer via web interface not fully implemented yet. Please use the command line: sudo python3 ps2_hdd_writer.py --device <device> --partition <n> --file <file>'
            })
        except Exception as e:
            import traceback
            self.send_json({'success': False, 'error': f'Error: {str(e)}', 'details': traceback.format_exc()})
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def get_devices(self):
        devices = []
        for i in range(10):
            device_path = f"/dev/disk{i}"
            if os.path.exists(device_path):
                try:
                    result = subprocess.run(['diskutil', 'info', device_path],
                                          capture_output=True, text=True, timeout=2)
                    if 'external' in result.stdout.lower() or 'physical' in result.stdout.lower():
                        name = "Unknown"
                        for line in result.stdout.split('\n'):
                            if 'Device / Media Name' in line:
                                name = line.split(':')[-1].strip()
                                break
                        devices.append({'path': device_path, 'name': name})
                except:
                    pass
        return {'devices': devices}
    
    def get_partitions(self, device):
        if not device:
            return {'partitions': [], 'error': 'No device specified'}
        
        # Ensure device path is properly decoded (handle double encoding)
        import urllib.parse
        device = urllib.parse.unquote(device)
        # In case it's still encoded, decode again
        if '%' in device:
            device = urllib.parse.unquote(device)
        
        print(f"DEBUG get_partitions: device = '{device}'")
        
        # Try to load modules if not already loaded
        load_modules()
        
        # Fallback to command line if module not available
        if not reader_module:
            try:
                # Use command line tool as fallback
                result = subprocess.run(['sudo', 'python3', 'ps2_hdd_reader.py', 
                                       '--device', device, 'list-partitions'],
                                      capture_output=True, text=True, timeout=10,
                                      cwd=os.path.dirname(os.path.abspath(__file__)))
                
                if result.returncode == 0:
                    # Parse output
                    partitions = []
                    for line in result.stdout.split('\n'):
                        if 'Found' in line and 'partition' in line:
                            continue
                        if '[' in line and ']' in line:
                            # Parse line like: [0] __mbr - Sector: 1, Size: 234441647 sectors
                            try:
                                parts = line.split(']')
                                if len(parts) >= 2:
                                    idx = int(parts[0].replace('[', ''))
                                    rest = parts[1].strip()
                                    name = rest.split(' - ')[0]
                                    # Extract size
                                    size_str = [p for p in rest.split(',') if 'Size:' in p]
                                    size = 0
                                    if size_str:
                                        size = int(size_str[0].split('Size:')[1].strip().split()[0])
                                    partitions.append({'name': name, 'size': size, 'sector': 0})
                            except:
                                pass
                    
                    if partitions:
                        return {'partitions': partitions}
                
                return {'partitions': [], 'error': f'Reader module not available. Command line fallback failed: {result.stderr}'}
            except Exception as e:
                return {'partitions': [], 'error': f'Reader module not available and fallback failed: {str(e)}'}
        
        try:
            # Check if we have root access
            if os.geteuid() != 0:
                return {'partitions': [], 'error': 'Root access required. Please run the web server with sudo.'}
            
            # Verify device exists
            if not os.path.exists(device):
                return {'partitions': [], 'error': f'Device {device} does not exist'}
            
            # Try to read partitions
            with reader_module.PS2HDDReader(device) as reader:
                apa_parser = reader_module.APAParser(reader)
                partitions = apa_parser.parse_mbr(verbose=False)
                
                # If no partitions found, the drive might not be formatted
                if not partitions:
                    # Check if device is readable
                    try:
                        test_sector = reader.read_sector(0)
                        # Check for APA magic
                        if test_sector[0x1B0:0x1B3] != b'APA':
                            return {'partitions': [], 
                                  'error': 'Drive is not formatted for PS2. Run: sudo python3 ps2_hdd_formatter.py --device ' + device}
                    except Exception as read_err:
                        return {'partitions': [], 'error': f'Cannot read device: {read_err}'}
                
                return {'partitions': [{'name': p.name, 'size': p.size, 'sector': p.sector} 
                                     for p in partitions]}
        except PermissionError as e:
            return {'partitions': [], 'error': f'Permission denied: {e}. Make sure the web server is running with sudo.'}
        except FileNotFoundError as e:
            return {'partitions': [], 'error': f'Device not found: {e}'}
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            return {'partitions': [], 'error': f'Error: {str(e)}', 'details': error_details}
    
    def get_files(self, device, partition_index):
        if not device or partition_index < 0:
            return {'files': []}
        
        # Try to load modules if not already loaded
        load_modules()
        
        if not reader_module:
            return {'files': [], 'error': 'Reader module not available'}
        
        try:
            with reader_module.PS2HDDReader(device) as reader:
                apa_parser = reader_module.APAParser(reader)
                partitions = apa_parser.parse_mbr()
                
                if partition_index >= len(partitions):
                    return {'files': [], 'error': 'Invalid partition'}
                
                partition = partitions[partition_index]
                pfs_parser = reader_module.PFSParser(reader, partition)
                
                if pfs_parser.parse_superblock():
                    files = pfs_parser.list_directory()
                    if files:
                        return {'files': [{'name': f.get('name', 'Unknown'),
                                         'size': f.get('size', 0),
                                         'is_dir': f.get('is_dir', False)}
                                        for f in files]}
                    else:
                        # Empty directory is normal for a new partition
                        return {'files': []}
                else:
                    return {'files': [], 'error': 'Could not parse PFS superblock. The partition may need to be formatted or initialized on a PS2.'}
        except Exception as e:
            import traceback
            return {'files': [], 'error': f'Error reading files: {str(e)}', 'details': traceback.format_exc()}
    
    def detect_devices(self):
        try:
            result = subprocess.run(['python3', 'detect_ps2_devices.py'],
                                  capture_output=True, text=True, 
                                  cwd=os.path.dirname(__file__))
            return {'success': True, 'message': result.stdout}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def log_message(self, format, *args):
        pass  # Suppress server logs


def main():
    # Check if running as root
    if os.geteuid() != 0:
        print("=" * 60)
        print("WARNING: Not running as root!")
        print("=" * 60)
        print("The web server needs root access to read/write PS2 HDDs.")
        print("Please run with: sudo python3 ps2_hdd_web_gui.py")
        print("=" * 60)
        response = input("\nContinue anyway? (some features won't work) [y/N]: ")
        if response.lower() != 'y':
            sys.exit(0)
    
    port = 8080
    server_address = ('', port)
    httpd = HTTPServer(server_address, PS2HDDHandler)
    
    url = f'http://localhost:{port}'
    print(f"PS2 HDD Manager - Web GUI")
    print(f"=" * 40)
    print(f"Server starting on {url}")
    if os.geteuid() == 0:
        print(f"✓ Running with root privileges")
    else:
        print(f"⚠ Running without root - some features may not work")
    print(f"Opening browser...")
    print(f"\nPress Ctrl+C to stop the server")
    
    # Open browser after a short delay
    def open_browser():
        time.sleep(1)
        webbrowser.open(url)
    
    threading.Thread(target=open_browser, daemon=True).start()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.shutdown()


if __name__ == '__main__':
    # Check if running as root
    if os.geteuid() != 0:
        print("Warning: Not running as root. Some operations may require sudo.")
        print("For full functionality, run with: sudo python3 ps2_hdd_web_gui.py")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(0)
    
    main()

