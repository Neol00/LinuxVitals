#!/usr/bin/env python

# LinuxVitals - System Monitoring and Control Application for Linux
# Copyright (c) 2024 Noel Ejemyr <noelejemyr@protonmail.com>
#
# LinuxVitals is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# LinuxVitals is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import os
import re
import time
import gi
from typing import Dict, List, Tuple, Optional
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gdk
import cairo

class DiskInfo:
    """Class to represent disk information and I/O statistics"""
    def __init__(self, device_name, model=None, size=None):
        self.device_name = device_name
        self.model = model or "Unknown"
        self.size = size or "Unknown"

        # I/O statistics
        self.read_bytes_per_sec = 0.0
        self.write_bytes_per_sec = 0.0
        self.read_iops = 0.0
        self.write_iops = 0.0
        self.utilization = 0.0

        # History for graphs (60 seconds)
        self.read_history = [0.0] * 60
        self.write_history = [0.0] * 60
        self.utilization_history = [0.0] * 60

        # Previous values for rate calculation
        self.prev_read_bytes = 0
        self.prev_write_bytes = 0
        self.prev_read_ios = 0
        self.prev_write_ios = 0
        self.prev_io_time = 0
        self.prev_timestamp = 0  # Start at 0 to skip initial measurement

        # Warmup tracking to skip initial measurements
        self.warmup_start_time = time.time()
        self.warmup_complete = False

class DiskGraphArea(Gtk.DrawingArea):
    """Custom drawing area for disk I/O graphs"""
    def __init__(self, disk_info):
        super().__init__()
        self.disk_info = disk_info
        self.set_draw_func(self.draw)
        
        # Get style context for theme colors
        self.style_context = self.get_style_context()
        
    def get_theme_colors(self):
        try:
            # Get colors from the current GTK theme
            bg_color = None
            
            # Try to get theme background color
            bg_lookup = self.style_context.lookup_color('theme_bg_color')
            if bg_lookup[0]:
                bg_color = bg_lookup[1]
            else:
                # Fallback to base color
                base_lookup = self.style_context.lookup_color('theme_base_color')
                if base_lookup[0]:
                    bg_color = base_lookup[1]
            
            # If we got a valid background color, determine if it's light or dark
            if bg_color and hasattr(bg_color, 'red'):
                is_light = bg_color.red > 0.5
                bg_rgb = (bg_color.red, bg_color.green, bg_color.blue)
            else:
                # Fallback: assume dark theme
                is_light = False
                bg_rgb = (0.188, 0.196, 0.235)  # Original dark background
            
            # Choose colors based on theme
            if is_light:  # Light theme
                read_color = (0.2, 0.6, 0.2)    # Green for read
                write_color = (1.0, 0.4, 0.8)   # Pink for write
                read_tint = (0.2, 0.6, 0.2, 0.2)
                write_tint = (1.0, 0.4, 0.8, 0.2)
                outline_color = (0.6, 0.6, 0.6)
            else:  # Dark theme
                read_color = (0.4, 0.8, 0.4)    # Light green for read
                write_color = (1.0, 0.6, 0.9)   # Light pink for write
                read_tint = (0.4, 0.8, 0.4, 0.2)
                write_tint = (1.0, 0.6, 0.9, 0.2)
                outline_color = (0.4, 0.4, 0.4)
                
            return {
                'background': bg_rgb,
                'read': read_color,
                'write': write_color,
                'read_tint': read_tint,
                'write_tint': write_tint,
                'outline': outline_color
            }
            
        except Exception:
            # Fallback to original colors if theme detection fails
            return {
                'background': (0.188, 0.196, 0.235),
                'read': (0.4, 0.8, 0.4),
                'write': (1.0, 0.6, 0.9),
                'read_tint': (0.4, 0.8, 0.4, 0.2),
                'write_tint': (1.0, 0.6, 0.9, 0.2),
                'outline': (0.4, 0.4, 0.4)
            }

    def draw(self, area, cr, width, height):
        # Get theme-appropriate colors
        colors = self.get_theme_colors()
        
        # Background
        cr.set_source_rgb(*colors['background'])
        cr.paint()

        # Draw outline
        cr.set_source_rgb(*colors['outline'])
        cr.set_line_width(1)
        cr.rectangle(0.5, 0.5, width - 1, height - 1)
        cr.stroke()

        # Find max value for scaling
        max_read = max(self.disk_info.read_history) if self.disk_info.read_history else 1
        max_write = max(self.disk_info.write_history) if self.disk_info.write_history else 1
        max_value = max(max_read, max_write, 1)  # Ensure non-zero for scaling

        # Draw read tint
        cr.set_source_rgba(*colors['read_tint'])
        cr.move_to(0, height)
        for i, value in enumerate(self.disk_info.read_history):
            x = i * (width / 59)
            y = height - (value / max_value * height * 0.8)  # 80% of height max
            cr.line_to(x, y)
        cr.line_to(width, height)
        cr.close_path()
        cr.fill()

        # Draw write tint
        cr.set_source_rgba(*colors['write_tint'])
        cr.move_to(0, height)
        for i, value in enumerate(self.disk_info.write_history):
            x = i * (width / 59)
            y = height - (value / max_value * height * 0.8)  # 80% of height max
            cr.line_to(x, y)
        cr.line_to(width, height)
        cr.close_path()
        cr.fill()

        # Draw read line
        cr.set_source_rgb(*colors['read'])
        cr.set_line_width(1.5)
        if self.disk_info.read_history:
            cr.move_to(0, height - (self.disk_info.read_history[0] / max_value * height * 0.8))
            for i, value in enumerate(self.disk_info.read_history):
                x = i * (width / 59)
                y = height - (value / max_value * height * 0.8)
                cr.line_to(x, y)
            cr.stroke()

        # Draw write line
        cr.set_source_rgb(*colors['write'])
        cr.set_line_width(1.5)
        if self.disk_info.write_history:
            cr.move_to(0, height - (self.disk_info.write_history[0] / max_value * height * 0.8))
            for i, value in enumerate(self.disk_info.write_history):
                x = i * (width / 59)
                y = height - (value / max_value * height * 0.8)
                cr.line_to(x, y)
            cr.stroke()

class DiskManagerConfig:
    UPDATE_INTERVAL = 1.0
    SECTOR_SIZE = 512  # Standard sector size in bytes
    BYTES_TO_MB = 1024 * 1024
    BYTES_TO_KB = 1024
    HISTORY_SIZE = 60

    @staticmethod
    def format_bytes_per_sec(bytes_per_sec):
        """Format bytes/sec to appropriate unit (B/s, KB/s, or MB/s)"""
        if bytes_per_sec >= DiskManagerConfig.BYTES_TO_MB:
            return f"{bytes_per_sec / DiskManagerConfig.BYTES_TO_MB:.1f} MB/s"
        elif bytes_per_sec >= DiskManagerConfig.BYTES_TO_KB:
            return f"{bytes_per_sec / DiskManagerConfig.BYTES_TO_KB:.1f} KB/s"
        else:
            return f"{bytes_per_sec:.0f} B/s"

    @staticmethod
    def get_disk_colors(style_context):
        """Get read/write colors based on current theme"""
        try:
            # Try to get theme background color
            bg_lookup = style_context.lookup_color('theme_bg_color')
            if bg_lookup[0]:
                bg_color = bg_lookup[1]
                is_light = bg_color.red > 0.5
            else:
                # Fallback to base color
                base_lookup = style_context.lookup_color('theme_base_color')
                if base_lookup[0]:
                    bg_color = base_lookup[1]
                    is_light = bg_color.red > 0.5
                else:
                    is_light = False

            # Return hex colors for markup
            if is_light:  # Light theme
                return {'read': '#339933', 'write': '#ff66cc'}  # Green and Pink
            else:  # Dark theme
                return {'read': '#66cc66', 'write': '#ff99e6'}  # Light green and light pink

        except Exception:
            # Fallback to dark theme colors
            return {'read': '#66cc66', 'write': '#ff99e6'}

class DiskManager:
    def __init__(self, logger, config_manager=None):
        self.logger = logger or self._create_dummy_logger()
        self.config_manager = config_manager
        self.disks = {}  # Dict of device_name -> DiskInfo
        
        # GUI components (initialized by UI setup)
        self.disk_graphs = {}  # Dict of device_name -> DiskGraphArea
        self.disk_usage_labels = {}  # Dict of device_name -> usage label
        self.disk_details_labels = {}  # Dict of device_name -> details label
        
        # Legacy attributes for compatibility
        self.disk_labels = {}  # Dict of device_name -> labels dict
        self.disk_graph = None  # Single graph reference (legacy)
        self.disk_usage_label = None  # Single usage label (legacy)
        self.disk_details_label = None  # Single details label (legacy)
        
        # Task management
        self.update_task_id = None
        
        # Detect if we're in a virtualized environment
        self.is_virtualized = self._detect_virtualization()
        
        # Discover physical disks
        self.logger.info("DiskManager initializing - discovering disks")
        self.discover_disks()
    
    def _create_dummy_logger(self):
        """Create a dummy logger for testing"""
        import logging
        return logging.getLogger(__name__)
    
    def _detect_virtualization(self):
        """Detect if we're running in a virtualized environment"""
        try:
            # Check for WSL
            if os.path.exists('/proc/version'):
                with open('/proc/version', 'r') as f:
                    version = f.read().lower()
                    if 'microsoft' in version or 'wsl' in version:
                        return True
            
            # Check for common virtualization indicators
            virt_indicators = [
                '/sys/class/dmi/id/product_name',
                '/sys/class/dmi/id/sys_vendor',
                '/sys/class/dmi/id/board_vendor'
            ]
            
            for path in virt_indicators:
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        content = f.read().lower()
                        virt_keywords = ['vmware', 'virtualbox', 'qemu', 'kvm', 'xen', 'hyper-v', 'microsoft corporation']
                        if any(keyword in content for keyword in virt_keywords):
                            return True
            
            return False
        except:
            return False

    def discover_disks(self):
        """Discover all physical disk drives and mounted zram devices (not partitions or virtual devices)"""
        try:
            self.disks.clear()
            
            # Read from /sys/block to find block devices
            physical_devices = []
            if os.path.exists('/sys/block'):
                for device in os.listdir('/sys/block'):
                    # Handle zram devices specially - only include if mounted as filesystem (not swap)
                    if device.startswith('zram'):
                        if self._is_zram_filesystem(device):
                            physical_devices.append(device)
                        continue
                    
                    # Skip other virtual devices
                    if device.startswith(('loop', 'ram', 'dm-', 'sr', 'fd')):
                        continue
                    
                    device_path = f'/sys/block/{device}'
                    if os.path.exists(device_path):
                        # Check if this is a whole disk (not a partition)
                        if os.path.exists(f'{device_path}/partition'):
                            continue
                        
                        # Additional checks to filter out virtual devices
                        if self._is_physical_disk(device, device_path):
                            physical_devices.append(device)
            
            # Get additional info for each disk
            for device in physical_devices:
                model = self._get_disk_model(device)
                size = self._get_disk_size(device)
                
                disk_info = DiskInfo(device, model, size)
                self.disks[device] = disk_info
                
                if device.startswith('zram'):
                    self.logger.info(f"Discovered mounted zram device: {device} ({model}, {size})")
                else:
                    self.logger.info(f"Discovered physical disk: {device} ({model}, {size})")
                
        except Exception as e:
            self.logger.error(f"Error discovering disks: {e}")
    
    def _is_zram_filesystem(self, device):
        """Check if a zram device is mounted as a filesystem (not swap)"""
        try:
            device_path = f'/dev/{device}'
            
            # Read /proc/mounts to check if zram device is mounted
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    fields = line.strip().split()
                    if len(fields) >= 3:
                        mount_device = fields[0]
                        mount_point = fields[1]
                        filesystem_type = fields[2]
                        
                        # Check if this is our zram device
                        if mount_device == device_path:
                            # Exclude swap filesystems
                            if filesystem_type.lower() != 'swap':
                                self.logger.info(f"Found zram device {device} mounted as {filesystem_type} on {mount_point}")
                                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking zram device {device}: {e}")
            return False
    
    def _is_physical_disk(self, device, device_path):
        """Check if a device is a real physical disk"""
        try:
            # Check if device has a reasonable size (> 100MB to exclude very small virtual devices)
            size_path = f'{device_path}/size'
            if os.path.exists(size_path):
                with open(size_path, 'r') as f:
                    sectors = int(f.read().strip())
                    bytes_size = sectors * DiskManagerConfig.SECTOR_SIZE
                    # Skip devices smaller than 100MB (likely virtual)
                    if bytes_size < 100 * 1024 * 1024:
                        self.logger.info(f"Skipping {device}: too small ({bytes_size} bytes)")
                        return False
            
            # Check if it's removable (USB drives, etc.) - we want to include these
            removable_path = f'{device_path}/removable'
            is_removable = False
            if os.path.exists(removable_path):
                with open(removable_path, 'r') as f:
                    is_removable = f.read().strip() == '1'
            
            # Check device type through queue/rotational (0=SSD, 1=HDD)
            rotational_path = f'{device_path}/queue/rotational'
            has_rotational_info = os.path.exists(rotational_path)
            
            # Check if device has a model (physical devices usually do)
            model = self._get_disk_model(device)
            has_model = model and model != "Unknown Model"
            
            # In virtualized environments, be more selective
            if self.is_virtualized:
                # Check for specific virtual patterns
                virtual_patterns = ['Virtual Disk', 'QEMU', 'VMware']
                if has_model and any(pattern in model for pattern in virtual_patterns):
                    # Check device size - only include larger virtual disks that represent real storage
                    if os.path.exists(size_path):
                        with open(size_path, 'r') as f:
                            sectors = int(f.read().strip())
                            bytes_size = sectors * DiskManagerConfig.SECTOR_SIZE
                            # Only include virtual disks > 10GB (likely representing real storage)
                            if bytes_size > 10 * 1024 * 1024 * 1024:  # 10GB
                                self.logger.info(f"Including large virtual disk: {device} ({bytes_size // (1024**3)}GB)")
                                return True
                            else:
                                self.logger.info(f"Skipping small virtual disk: {device} ({bytes_size // (1024**2)}MB)")
                                return False
                    else:
                        return False
                
                # In virtualized environments, be more strict about what we include
                if not (is_removable or (has_model and 'Virtual Disk' not in model)):
                    return False
            
            # If it's removable, has a model, or has rotational info, it's likely physical
            if is_removable or has_model or has_rotational_info:
                return True
            
            # Default to including if we can't determine (better to show too many than too few)
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking if {device} is physical: {e}")
            return True  # Default to including on error

    def _get_disk_model(self, device):
        """Get disk model from sysfs"""
        try:
            # Handle zram devices specially
            if device.startswith('zram'):
                return "zram Compressed RAM Device"
            
            model_path = f'/sys/block/{device}/device/model'
            if os.path.exists(model_path):
                with open(model_path, 'r') as f:
                    return f.read().strip()
        except:
            pass
        return "Unknown Model"

    def _get_disk_size(self, device):
        """Get disk size from sysfs"""
        try:
            size_path = f'/sys/block/{device}/size'
            if os.path.exists(size_path):
                with open(size_path, 'r') as f:
                    sectors = int(f.read().strip())
                    bytes_size = sectors * DiskManagerConfig.SECTOR_SIZE
                    
                    # Convert to human readable
                    if bytes_size >= 1024**4:  # TB
                        return f"{bytes_size / (1024**4):.1f}T"
                    elif bytes_size >= 1024**3:  # GB
                        return f"{bytes_size / (1024**3):.1f}G"
                    elif bytes_size >= 1024**2:  # MB
                        return f"{bytes_size / (1024**2):.1f}M"
                    else:
                        return f"{bytes_size}B"
        except:
            pass
        return "Unknown Size"

    def update_disk_stats(self):
        """Update I/O statistics for all disks"""
        try:
            # Read /proc/diskstats
            if not os.path.exists('/proc/diskstats'):
                self.logger.warning("'/proc/diskstats' not found")
                return
                
            current_time = time.time()
            processed_devices = []
            
            with open('/proc/diskstats', 'r') as f:
                for line in f:
                    fields = line.strip().split()
                    if len(fields) < 14:
                        continue
                        
                    device_name = fields[2]
                    
                    # Only process our tracked disks
                    if device_name not in self.disks:
                        continue
                        
                    disk_info = self.disks[device_name]
                    processed_devices.append(device_name)
                    
                    try:
                        # Parse diskstats fields with error handling
                        read_ios = int(fields[3])
                        read_sectors = int(fields[5])
                        write_ios = int(fields[7])
                        write_sectors = int(fields[9])
                        io_time_ms = int(fields[12])
                        
                        # Convert sectors to bytes
                        read_bytes = read_sectors * DiskManagerConfig.SECTOR_SIZE
                        write_bytes = write_sectors * DiskManagerConfig.SECTOR_SIZE

                        # Check if warmup period has elapsed (0.5 seconds)
                        if not disk_info.warmup_complete:
                            if current_time - disk_info.warmup_start_time >= 0.5:
                                disk_info.warmup_complete = True
                            # During warmup, just store values but don't calculate rates
                            disk_info.prev_read_bytes = read_bytes
                            disk_info.prev_write_bytes = write_bytes
                            disk_info.prev_read_ios = read_ios
                            disk_info.prev_write_ios = write_ios
                            disk_info.prev_io_time = io_time_ms
                            disk_info.prev_timestamp = current_time
                            continue

                        # Calculate rates if we have previous data
                        time_delta = current_time - disk_info.prev_timestamp
                        # Only calculate rates if:
                        # 1. We have a valid time delta (> 0)
                        # 2. We have previous data (prev_timestamp > 0)
                        # 3. Time delta is reasonable (< 5 seconds to avoid spikes on tab switches)
                        if time_delta > 0 and disk_info.prev_timestamp > 0 and time_delta < 5:
                            # Calculate bytes per second
                            read_bytes_delta = read_bytes - disk_info.prev_read_bytes
                            write_bytes_delta = write_bytes - disk_info.prev_write_bytes

                            # Handle counter rollover (unlikely but possible)
                            if read_bytes_delta < 0:
                                read_bytes_delta = read_bytes
                            if write_bytes_delta < 0:
                                write_bytes_delta = write_bytes

                            disk_info.read_bytes_per_sec = read_bytes_delta / time_delta
                            disk_info.write_bytes_per_sec = write_bytes_delta / time_delta

                            # Calculate IOPS
                            read_ios_delta = read_ios - disk_info.prev_read_ios
                            write_ios_delta = write_ios - disk_info.prev_write_ios

                            # Handle counter rollover
                            if read_ios_delta < 0:
                                read_ios_delta = read_ios
                            if write_ios_delta < 0:
                                write_ios_delta = write_ios

                            disk_info.read_iops = read_ios_delta / time_delta
                            disk_info.write_iops = write_ios_delta / time_delta

                            # Calculate utilization percentage
                            io_time_delta = io_time_ms - disk_info.prev_io_time
                            if io_time_delta < 0:
                                io_time_delta = io_time_ms

                            disk_info.utilization = min(100.0, max(0, (io_time_delta / (time_delta * 1000)) * 100))

                            # Update history (convert bytes/sec to MB/sec for display)
                            disk_info.read_history.pop(0)
                            disk_info.read_history.append(disk_info.read_bytes_per_sec / DiskManagerConfig.BYTES_TO_MB)

                            disk_info.write_history.pop(0)
                            disk_info.write_history.append(disk_info.write_bytes_per_sec / DiskManagerConfig.BYTES_TO_MB)

                            disk_info.utilization_history.pop(0)
                            disk_info.utilization_history.append(disk_info.utilization)
                        elif disk_info.prev_timestamp > 0:
                            # Time delta too large (tab switch or pause) - reset to zero to avoid spike
                            disk_info.read_bytes_per_sec = 0.0
                            disk_info.write_bytes_per_sec = 0.0
                            disk_info.read_iops = 0.0
                            disk_info.write_iops = 0.0
                            disk_info.utilization = 0.0

                            # Add zero to history to show the gap
                            disk_info.read_history.pop(0)
                            disk_info.read_history.append(0.0)

                            disk_info.write_history.pop(0)
                            disk_info.write_history.append(0.0)

                            disk_info.utilization_history.pop(0)
                            disk_info.utilization_history.append(0.0)
                        
                        # Store current values for next iteration
                        disk_info.prev_read_bytes = read_bytes
                        disk_info.prev_write_bytes = write_bytes
                        disk_info.prev_read_ios = read_ios
                        disk_info.prev_write_ios = write_ios
                        disk_info.prev_io_time = io_time_ms
                        disk_info.prev_timestamp = current_time
                        
                    except (ValueError, IndexError) as e:
                        self.logger.error(f"Error parsing diskstats for {device_name}: {e}")
                        continue
            
            if not processed_devices:
                self.logger.warning("No disk devices were processed from /proc/diskstats")
                    
        except Exception as e:
            self.logger.error(f"Error updating disk stats: {e}")

    def update_disk_gui(self):
        """Update GUI elements with current disk stats"""
        try:
            for device_name, disk_info in self.disks.items():
                # Update graph
                if hasattr(self, 'disk_graphs') and device_name in self.disk_graphs:
                    self.disk_graphs[device_name].queue_draw()

                # Update usage labels (total throughput) with dynamic units
                if hasattr(self, 'disk_usage_labels') and device_name in self.disk_usage_labels:
                    total_throughput_bytes = disk_info.read_bytes_per_sec + disk_info.write_bytes_per_sec
                    self.disk_usage_labels[device_name].set_text(DiskManagerConfig.format_bytes_per_sec(total_throughput_bytes))

                # Update details labels (read/write breakdown) with dynamic units and colored text
                if hasattr(self, 'disk_details_labels') and device_name in self.disk_details_labels:
                    # Get theme colors
                    label = self.disk_details_labels[device_name]
                    style_context = label.get_style_context()
                    colors = DiskManagerConfig.get_disk_colors(style_context)

                    read_speed_str = DiskManagerConfig.format_bytes_per_sec(disk_info.read_bytes_per_sec)
                    write_speed_str = DiskManagerConfig.format_bytes_per_sec(disk_info.write_bytes_per_sec)

                    # Use markup to color the Read/Write words
                    details_markup = (
                        f"Size: {disk_info.size} | "
                        f"<span foreground='{colors['read']}'>Read</span>: {read_speed_str} | "
                        f"<span foreground='{colors['write']}'>Write</span>: {write_speed_str}"
                    )
                    label.set_markup(details_markup)

        except Exception as e:
            self.logger.error(f"Error updating disk GUI: {e}")

    def start_monitoring(self):
        """Start disk monitoring tasks"""
        if self.update_task_id:
            GLib.source_remove(self.update_task_id)
        interval_ms = self.get_update_interval_ms()
        self.update_task_id = GLib.timeout_add(interval_ms, self.run_update_tasks)

    def stop_monitoring(self):
        """Stop disk monitoring tasks"""
        if self.update_task_id:
            GLib.source_remove(self.update_task_id)
            self.update_task_id = None

    def run_update_tasks(self):
        """Execute disk monitoring tasks"""
        try:
            self.update_disk_stats()
            self.update_disk_gui()
        except Exception as e:
            self.logger.error(f"Error running disk update tasks: {e}")
        
        # Reschedule if task is still active
        if self.update_task_id:
            self.start_monitoring()
        return False

    def get_disk_count(self):
        """Get the number of discovered disks"""
        return len(self.disks)

    def get_update_interval_ms(self) -> int:
        """Get the update interval in milliseconds from config"""
        try:
            if self.config_manager:
                interval_seconds = float(self.config_manager.get_setting('Settings', 'update_interval', '1.0'))
                return int(interval_seconds * 1000)
            return 1000  # Default to 1 second
        except Exception as e:
            self.logger.error(f"Error getting update interval: {e}")
            return 1000

    def get_disk_summary(self):
        """Get a summary of disk activity"""
        try:
            if not self.disks:
                return "Disks: None"
            
            total_read = sum(disk.read_bytes_per_sec for disk in self.disks.values())
            total_write = sum(disk.write_bytes_per_sec for disk in self.disks.values())
            
            total_read_mb = total_read / DiskManagerConfig.BYTES_TO_MB
            total_write_mb = total_write / DiskManagerConfig.BYTES_TO_MB
            
            return f"Disks: {len(self.disks)} | R: {total_read_mb:.1f} MB/s | W: {total_write_mb:.1f} MB/s"
        except:
            return f"Disks: {len(self.disks)}"