#!/usr/bin/env python3
"""
PS2 HDD Manager - GUI Application
A graphical interface for managing PS2 HDDs with drag-and-drop support.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import threading
import subprocess

# Try to import the reader/writer modules
try:
    import importlib.util
    spec_reader = importlib.util.spec_from_file_location("ps2_hdd_reader", 
                                                         os.path.join(os.path.dirname(__file__), "ps2_hdd_reader.py"))
    reader_module = importlib.util.module_from_spec(spec_reader)
    spec_reader.loader.exec_module(reader_module)
    
    spec_writer = importlib.util.spec_from_file_location("ps2_hdd_writer", 
                                                         os.path.join(os.path.dirname(__file__), "ps2_hdd_writer.py"))
    writer_module = importlib.util.module_from_spec(spec_writer)
    spec_writer.loader.exec_module(writer_module)
except Exception as e:
    print(f"Error importing modules: {e}")
    reader_module = None
    writer_module = None


class PS2HDDManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PS2 HDD Manager")
        self.root.geometry("900x700")
        
        # Variables
        self.selected_device = tk.StringVar()
        self.selected_partition = tk.StringVar()
        self.devices = []
        self.partitions = []
        self.files = []
        
        self.setup_ui()
        self.refresh_devices()
        
    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Device selection
        device_frame = ttk.LabelFrame(main_frame, text="PS2 HDD Device", padding="10")
        device_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(device_frame, text="Device:").grid(row=0, column=0, padx=5)
        self.device_combo = ttk.Combobox(device_frame, textvariable=self.selected_device, 
                                         width=30, state="readonly")
        self.device_combo.grid(row=0, column=1, padx=5)
        self.device_combo.bind("<<ComboboxSelected>>", self.on_device_selected)
        
        ttk.Button(device_frame, text="Refresh", command=self.refresh_devices).grid(row=0, column=2, padx=5)
        ttk.Button(device_frame, text="Detect", command=self.detect_devices).grid(row=0, column=3, padx=5)
        
        # Partition selection
        partition_frame = ttk.LabelFrame(main_frame, text="Partition", padding="10")
        partition_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(partition_frame, text="Partition:").grid(row=0, column=0, padx=5)
        self.partition_combo = ttk.Combobox(partition_frame, textvariable=self.selected_partition,
                                           width=30, state="readonly")
        self.partition_combo.grid(row=0, column=1, padx=5)
        self.partition_combo.bind("<<ComboboxSelected>>", self.on_partition_selected)
        
        ttk.Button(partition_frame, text="Refresh Files", command=self.refresh_files).grid(row=0, column=2, padx=5)
        
        # File browser
        file_frame = ttk.LabelFrame(main_frame, text="PS2 HDD Files", padding="10")
        file_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Tree view for files
        tree_frame = ttk.Frame(file_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.file_tree = ttk.Treeview(tree_frame, columns=("Size", "Type"), show="tree headings")
        self.file_tree.heading("#0", text="Name")
        self.file_tree.heading("Size", text="Size")
        self.file_tree.heading("Type", text="Type")
        self.file_tree.column("#0", width=300)
        self.file_tree.column("Size", width=100)
        self.file_tree.column("Type", width=100)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=scrollbar.set)
        
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Drag and drop area
        drop_frame = ttk.LabelFrame(main_frame, text="Drag & Drop Files Here", padding="10")
        drop_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.drop_label = ttk.Label(drop_frame, text="Drop files here to transfer to PS2 HDD", 
                                    font=("Arial", 12))
        self.drop_label.pack(pady=20)
        
        # Enable drag and drop
        self.drop_label.bind("<Button-1>", self.on_drop_click)
        drop_frame.bind("<Button-1>", self.on_drop_click)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="Add Files...", command=self.add_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Extract Selected", command=self.extract_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Delete Selected", command=self.delete_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Format Drive...", command=self.format_drive).pack(side=tk.LEFT, padx=5)
        
        # Status/Log area
        log_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        log_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, width=80)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        main_frame.rowconfigure(5, weight=1)
        
        # Enable drag and drop on the window
        self.setup_drag_drop()
        
    def setup_drag_drop(self):
        """Setup drag and drop functionality"""
        # Note: Native drag-and-drop on macOS with tkinter is limited
        # We'll use a file dialog button as the primary method
        # For true drag-and-drop, we'd need PyObjC or PyQt
        pass
    
    def log(self, message):
        """Add message to log"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def refresh_devices(self):
        """Refresh list of available devices"""
        self.devices = []
        for i in range(10):
            device_path = f"/dev/disk{i}"
            if os.path.exists(device_path):
                # Try to get device info
                try:
                    result = subprocess.run(['diskutil', 'info', device_path],
                                          capture_output=True, text=True, timeout=2)
                    if 'external' in result.stdout.lower() or 'physical' in result.stdout.lower():
                        # Extract device name
                        name = "Unknown"
                        for line in result.stdout.split('\n'):
                            if 'Device / Media Name' in line:
                                name = line.split(':')[-1].strip()
                                break
                        self.devices.append((device_path, name))
                except:
                    pass
        
        device_list = [f"{path} ({name})" for path, name in self.devices]
        self.device_combo['values'] = device_list
        
        if device_list:
            self.device_combo.current(0)
            self.on_device_selected()
    
    def detect_devices(self):
        """Run detection script"""
        self.log("Running device detection...")
        try:
            result = subprocess.run(['python3', 'detect_ps2_devices.py'],
                                  capture_output=True, text=True, cwd=os.path.dirname(__file__))
            self.log(result.stdout)
            if result.stderr:
                self.log(f"Error: {result.stderr}")
            self.refresh_devices()
        except Exception as e:
            self.log(f"Error running detection: {e}")
            messagebox.showerror("Error", f"Could not run detection: {e}")
    
    def on_device_selected(self, event=None):
        """Handle device selection"""
        selection = self.device_combo.get()
        if not selection:
            return
        
        device_path = selection.split(' ')[0]
        self.log(f"Selected device: {device_path}")
        self.load_partitions(device_path)
    
    def load_partitions(self, device_path):
        """Load partitions from device"""
        if not reader_module:
            self.log("Error: Reader module not available")
            return
        
        self.partitions = []
        self.log(f"Loading partitions from {device_path}...")
        
        def load_thread():
            try:
                with reader_module.PS2HDDReader(device_path) as reader:
                    apa_parser = reader_module.APAParser(reader)
                    partitions = apa_parser.parse_mbr()
                    
                    self.partitions = partitions
                    partition_list = [f"[{i}] {p.name} ({p.size} sectors)" 
                                    for i, p in enumerate(partitions)]
                    
                    self.root.after(0, lambda: self.update_partition_list(partition_list))
                    self.root.after(0, lambda: self.log(f"Found {len(partitions)} partition(s)"))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"Error loading partitions: {e}"))
                self.root.after(0, lambda: messagebox.showerror("Error", f"Could not load partitions: {e}"))
        
        threading.Thread(target=load_thread, daemon=True).start()
    
    def update_partition_list(self, partition_list):
        """Update partition combo box"""
        self.partition_combo['values'] = partition_list
        if partition_list:
            self.partition_combo.current(0)
            self.on_partition_selected()
    
    def on_partition_selected(self, event=None):
        """Handle partition selection"""
        selection = self.partition_combo.get()
        if selection:
            self.refresh_files()
    
    def refresh_files(self):
        """Refresh file list"""
        device_path = self.selected_device.get().split(' ')[0] if self.selected_device.get() else None
        partition_index = self.partition_combo.current()
        
        if device_path is None or partition_index < 0:
            return
        
        self.log(f"Loading files from partition {partition_index}...")
        
        def load_thread():
            try:
                with reader_module.PS2HDDReader(device_path) as reader:
                    apa_parser = reader_module.APAParser(reader)
                    partitions = apa_parser.parse_mbr()
                    
                    if partition_index >= len(partitions):
                        self.root.after(0, lambda: self.log("Invalid partition index"))
                        return
                    
                    partition = partitions[partition_index]
                    pfs_parser = reader_module.PFSParser(reader, partition)
                    
                    if pfs_parser.parse_superblock():
                        files = pfs_parser.list_directory()
                        self.root.after(0, lambda: self.update_file_tree(files))
                        self.root.after(0, lambda: self.log(f"Found {len(files)} file(s)"))
                    else:
                        self.root.after(0, lambda: self.log("Could not parse PFS superblock"))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"Error loading files: {e}"))
        
        threading.Thread(target=load_thread, daemon=True).start()
    
    def update_file_tree(self, files):
        """Update file tree view"""
        # Clear existing items
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        
        # Add files
        for file_info in files:
            file_type = "DIR" if file_info.get('is_dir', False) else "FILE"
            size_str = f"{file_info.get('size', 0)} bytes" if not file_info.get('is_dir', False) else "-"
            self.file_tree.insert("", tk.END, text=file_info.get('name', 'Unknown'),
                                values=(size_str, file_type))
    
    def on_drop_click(self, event):
        """Handle click on drop area (opens file dialog)"""
        self.add_files()
    
    def add_files(self):
        """Add files via file dialog"""
        files = filedialog.askopenfilenames(
            title="Select files to transfer to PS2 HDD",
            filetypes=[("All files", "*.*"), ("ISO files", "*.iso"), ("ELF files", "*.elf")]
        )
        
        if files:
            device_path = self.selected_device.get().split(' ')[0] if self.selected_device.get() else None
            partition_index = self.partition_combo.current()
            
            if device_path is None or partition_index < 0:
                messagebox.showerror("Error", "Please select a device and partition first")
                return
            
            self.transfer_files(files, device_path, partition_index)
    
    def transfer_files(self, files, device_path, partition_index):
        """Transfer files to PS2 HDD"""
        self.log(f"Transferring {len(files)} file(s)...")
        
        def transfer_thread():
            for file_path in files:
                try:
                    filename = os.path.basename(file_path)
                    self.root.after(0, lambda f=filename: self.log(f"Transferring {f}..."))
                    
                    # Use the writer module
                    if writer_module:
                        success = writer_module.write_file_to_ps2(device_path, partition_index, file_path)
                        if success:
                            self.root.after(0, lambda f=filename: self.log(f"✓ {f} transferred successfully"))
                        else:
                            self.root.after(0, lambda f=filename: self.log(f"✗ Failed to transfer {f}"))
                    else:
                        # Fallback to command line
                        cmd = ['sudo', 'python3', 'ps2_hdd_writer.py',
                              '--device', device_path,
                              '--partition', str(partition_index),
                              '--file', file_path]
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        if result.returncode == 0:
                            self.root.after(0, lambda f=filename: self.log(f"✓ {f} transferred successfully"))
                        else:
                            self.root.after(0, lambda f=filename: self.log(f"✗ Failed to transfer {f}: {result.stderr}"))
                except Exception as e:
                    self.root.after(0, lambda f=file_path, err=str(e): self.log(f"✗ Error transferring {os.path.basename(f)}: {err}"))
            
            self.root.after(0, lambda: self.log("Transfer complete"))
            self.root.after(0, self.refresh_files)
        
        threading.Thread(target=transfer_thread, daemon=True).start()
    
    def extract_selected(self):
        """Extract selected files"""
        selection = self.file_tree.selection()
        if not selection:
            messagebox.showinfo("Info", "Please select a file to extract")
            return
        
        # Get destination directory
        dest_dir = filedialog.askdirectory(title="Select extraction directory")
        if not dest_dir:
            return
        
        self.log("Extraction not yet implemented - use command line tool")
        messagebox.showinfo("Info", "Use the command line tool for extraction:\n"
                           "sudo python3 ps2_hdd_reader.py --device <device> extract --partition <n> --output <dir>")
    
    def delete_selected(self):
        """Delete selected files"""
        selection = self.file_tree.selection()
        if not selection:
            messagebox.showinfo("Info", "Please select a file to delete")
            return
        
        self.log("Deletion not yet implemented - use wLaunchELF on PS2")
        messagebox.showinfo("Info", "File deletion should be done using wLaunchELF on your PS2 console")
    
    def format_drive(self):
        """Format drive"""
        device_path = self.selected_device.get().split(' ')[0] if self.selected_device.get() else None
        if not device_path:
            messagebox.showerror("Error", "Please select a device first")
            return
        
        response = messagebox.askyesno("Warning", 
                                       f"This will ERASE ALL DATA on {device_path}!\n\n"
                                       "Are you sure you want to continue?")
        if response:
            self.log(f"Formatting {device_path}...")
            try:
                result = subprocess.run(['sudo', 'python3', 'ps2_hdd_formatter.py',
                                       '--device', device_path, '--yes'],
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    self.log("Formatting complete")
                    self.load_partitions(device_path)
                else:
                    self.log(f"Formatting error: {result.stderr}")
                    messagebox.showerror("Error", f"Formatting failed:\n{result.stderr}")
            except Exception as e:
                self.log(f"Error: {e}")
                messagebox.showerror("Error", f"Could not format drive: {e}")


def main():
    # Check if running as root
    if os.geteuid() != 0:
        print("Warning: Not running as root. Some operations may require sudo.")
        print("For full functionality, run with: sudo python3 ps2_hdd_gui.py")
        response = messagebox.askyesno("Warning", 
                                      "Not running as root. Some operations may fail.\n\n"
                                      "Continue anyway?")
        if not response:
            sys.exit(0)
    
    root = tk.Tk()
    app = PS2HDDManagerGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()

