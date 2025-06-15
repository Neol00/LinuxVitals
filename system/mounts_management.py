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
import shutil
import subprocess
import gi
from typing import Optional, Dict, List, Tuple, Any
from gi.repository import Gtk, GLib

class MountInfo:
    """Class to represent mount point information"""
    def __init__(self, device, mountpoint, filesystem, options="", 
                 total_space=0, used_space=0, available_space=0):
        self.device = device
        self.mountpoint = mountpoint
        self.filesystem = filesystem
        self.options = options
        self.total_space = total_space  # in bytes
        self.used_space = used_space    # in bytes  
        self.available_space = available_space  # in bytes
        
        # Calculate usage percentage
        if total_space > 0:
            self.usage_percent = (used_space / total_space) * 100
        else:
            self.usage_percent = 0.0

class MountsManagerConfig:
    BYTES_TO_GB = 1024 * 1024 * 1024
    BYTES_TO_MB = 1024 * 1024

class MountsManager:
    def __init__(self, logger, widget_factory=None):
        self.logger = logger
        self.widget_factory = widget_factory
        self.mounts = []  # List of MountInfo objects
        
        # GUI components
        self.mounts_tree_view = None
        self.mounts_store = None
        self.mounts_selection = None

    def scan_mounts(self) -> List[MountInfo]:
        """Scan all mounted filesystems"""
        try:
            mounts = []
            
            # Read /proc/mounts for mount information
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    fields = line.strip().split()
                    if len(fields) < 4:
                        continue
                    
                    device = fields[0]
                    mountpoint = fields[1]
                    filesystem = fields[2]
                    options = fields[3]
                    
                    # Skip virtual filesystems that users typically don't care about
                    if self.should_skip_mount(device, mountpoint, filesystem):
                        continue
                    
                    # Get disk usage information
                    total_space = 0
                    used_space = 0
                    available_space = 0
                    
                    try:
                        if os.path.exists(mountpoint):
                            disk_usage = shutil.disk_usage(mountpoint)
                            total_space = disk_usage.total
                            available_space = disk_usage.free
                            used_space = total_space - available_space
                    except (OSError, PermissionError):
                        # Can't access mount point
                        pass
                    
                    mount_info = MountInfo(
                        device=device,
                        mountpoint=mountpoint,
                        filesystem=filesystem,
                        options=options,
                        total_space=total_space,
                        used_space=used_space,
                        available_space=available_space
                    )
                    
                    mounts.append(mount_info)
            
            # Sort by mount point
            mounts.sort(key=lambda m: m.mountpoint)
            return mounts
            
        except Exception as e:
            self.logger.error(f"Error scanning mounts: {e}")
            return []

    def should_skip_mount(self, device, mountpoint, filesystem):
        """Determine if a mount should be skipped from display"""
        # Skip virtual/pseudo filesystems
        virtual_filesystems = {
            'proc', 'sysfs', 'devtmpfs', 'devpts', 'tmpfs', 'cgroup', 'cgroup2',
            'pstore', 'bpf', 'tracefs', 'debugfs', 'securityfs', 'hugetlbfs',
            'mqueue', 'ramfs', 'autofs', 'configfs', 'fuse.gvfsd-fuse'
        }
        
        if filesystem in virtual_filesystems:
            return True
        
        # Skip mount points that start with /sys, /proc, /dev (except /dev/sd*, /dev/nvme*)
        if mountpoint.startswith(('/sys', '/proc', '/run')):
            return True
            
        if mountpoint.startswith('/dev') and not any(
            device.startswith(prefix) for prefix in ['/dev/sd', '/dev/nvme', '/dev/hd', '/dev/vd']
        ):
            return True
        
        # Skip snap mounts
        if '/snap/' in mountpoint or filesystem == 'squashfs':
            return True
        
        return False

    def update_mounts(self):
        """Update the mounts list"""
        try:
            self.mounts = self.scan_mounts()
            
            # Update GUI if available
            if self.mounts_store:
                self.update_mounts_tree_view()
                
        except Exception as e:
            self.logger.error(f"Error updating mounts: {e}")

    def create_mounts_tree_view(self) -> Gtk.TreeView:
        """Create the mounts tree view widget"""
        try:
            # Create list store (Device, Mount Point, Filesystem, Size, Used, Available, Usage%)
            self.mounts_store = self.widget_factory.create_list_store([str, str, str, str, str, str, str, str])
            
            # Create tree view
            self.mounts_tree_view = self.widget_factory.create_tree_view(model=self.mounts_store)
            self.mounts_tree_view.set_headers_visible(True)
            
            # Create columns
            columns = [
                ("Device", 0, 200),
                ("Mount Point", 1, 150),
                ("Filesystem", 2, 100),
                ("Total Size", 3, 100),
                ("Used", 4, 100),
                ("Available", 5, 100),
                ("Usage %", 6, 80),
                ("Options", 7, 200)
            ]
            
            for title, column_id, width in columns:
                renderer = self.widget_factory.create_cell_renderer_text()
                column = self.widget_factory.create_tree_view_column(title, renderer, text_column=column_id)
                column.set_resizable(True)
                column.set_min_width(width)
                if column_id in [3, 4, 5, 6]:  # Size and percentage columns
                    column.set_alignment(1.0)  # Right align numbers
                    renderer.set_property("xalign", 1.0)
                self.mounts_tree_view.append_column(column)
            
            # Set up selection
            self.mounts_selection = self.mounts_tree_view.get_selection()
            self.mounts_selection.set_mode(Gtk.SelectionMode.SINGLE)
            
            return self.mounts_tree_view
            
        except Exception as e:
            self.logger.error(f"Error creating mounts tree view: {e}")
            return None

    def update_mounts_tree_view(self):
        """Update the mounts tree view with current mount data"""
        try:
            if not self.mounts_store:
                return
            
            # Clear existing data
            self.mounts_store.clear()
            
            # Add mounts to store
            for mount in self.mounts:
                # Format sizes
                total_gb = mount.total_space / MountsManagerConfig.BYTES_TO_GB
                used_gb = mount.used_space / MountsManagerConfig.BYTES_TO_GB
                available_gb = mount.available_space / MountsManagerConfig.BYTES_TO_GB
                
                # Format size strings
                if total_gb >= 1:
                    total_str = f"{total_gb:.1f} GB"
                    used_str = f"{used_gb:.1f} GB"
                    available_str = f"{available_gb:.1f} GB"
                else:
                    total_mb = mount.total_space / MountsManagerConfig.BYTES_TO_MB
                    used_mb = mount.used_space / MountsManagerConfig.BYTES_TO_MB
                    available_mb = mount.available_space / MountsManagerConfig.BYTES_TO_MB
                    total_str = f"{total_mb:.0f} MB"
                    used_str = f"{used_mb:.0f} MB"
                    available_str = f"{available_mb:.0f} MB"
                
                usage_str = f"{mount.usage_percent:.1f}%"
                
                # Truncate long device names and options
                device_display = mount.device
                if len(device_display) > 30:
                    device_display = "..." + device_display[-27:]
                
                options_display = mount.options
                if len(options_display) > 50:
                    options_display = options_display[:47] + "..."
                
                self.mounts_store.append([
                    device_display,
                    mount.mountpoint,
                    mount.filesystem,
                    total_str,
                    used_str,
                    available_str,
                    usage_str,
                    options_display
                ])
                
        except Exception as e:
            self.logger.error(f"Error updating mounts tree view: {e}")

    def get_mount_summary(self) -> str:
        """Get a summary of mounted filesystems"""
        try:
            total_mounts = len(self.mounts)
            return f"Mounted Filesystems: {total_mounts}"
        except:
            return "Mounted Filesystems: N/A"

    def get_selected_mount(self) -> Optional[MountInfo]:
        """Get the currently selected mount"""
        try:
            if not self.mounts_selection:
                return None
            
            model, iter = self.mounts_selection.get_selected()
            if not iter:
                return None
            
            # Get the mount point from the selected row
            mountpoint = model.get_value(iter, 1)
            
            # Find the corresponding MountInfo
            for mount in self.mounts:
                if mount.mountpoint == mountpoint:
                    return mount
            
            return None
        except Exception as e:
            self.logger.error(f"Error getting selected mount: {e}")
            return None

    def unmount_filesystem(self, mount_info: MountInfo):
        """Unmount a filesystem"""
        try:
            # Show confirmation dialog
            self.show_unmount_confirmation_dialog(mount_info)
        except Exception as e:
            self.logger.error(f"Error unmounting filesystem: {e}")

    def show_unmount_confirmation_dialog(self, mount_info: MountInfo):
        """Show confirmation dialog before unmounting"""
        try:
            dialog = self.widget_factory.create_message_dialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.YES_NO,
                text=f"Unmount Filesystem?",
                secondary_text=(
                    f"Are you sure you want to unmount '{mount_info.mountpoint}'?\n\n"
                    f"Device: {mount_info.device}\n"
                    f"Filesystem: {mount_info.filesystem}\n\n"
                    f"This may cause data loss if files are currently being accessed."
                )
            )
            
            def on_dialog_response(dialog, response):
                if response == Gtk.ResponseType.YES:
                    self.unmount_confirmed(mount_info)
                dialog.destroy()
            
            dialog.connect("response", on_dialog_response)
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error showing unmount confirmation dialog: {e}")

    def unmount_confirmed(self, mount_info: MountInfo):
        """Actually unmount the filesystem after confirmation"""
        try:
            # Use umount command
            cmd = ["sudo", "umount", mount_info.mountpoint]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.info(f"Successfully unmounted {mount_info.mountpoint}")
                # Refresh mounts list
                GLib.timeout_add(500, self.update_mounts)
            else:
                error_msg = result.stderr or "Unknown error"
                self.logger.error(f"Failed to unmount {mount_info.mountpoint}: {error_msg}")
                self.show_error_dialog("Unmount Failed", f"Failed to unmount {mount_info.mountpoint}:\n{error_msg}")
                
        except Exception as e:
            self.logger.error(f"Error unmounting {mount_info.mountpoint}: {e}")
            self.show_error_dialog("Unmount Error", f"Error unmounting {mount_info.mountpoint}:\n{str(e)}")

    def show_error_dialog(self, title: str, message: str):
        """Show an error dialog"""
        try:
            dialog = self.widget_factory.create_message_dialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=title,
                secondary_text=message
            )
            dialog.connect("response", lambda d, r: d.destroy())
            dialog.present()
        except Exception as e:
            self.logger.error(f"Error showing error dialog: {e}")

    def show_mount_properties(self, mount_info: MountInfo):
        """Show detailed properties of a mount"""
        try:
            # Create properties dialog
            dialog = self.widget_factory.create_dialog(title=f"Mount Properties - {mount_info.mountpoint}")
            dialog.set_default_size(500, 400)
            
            content_area = dialog.get_content_area()
            
            # Create scrolled window for mount details
            scrolled = self.widget_factory.create_scrolled_window(
                policy=(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            )
            
            text_view = self.widget_factory.create_text_view()
            text_view.set_editable(False)
            text_view.set_wrap_mode(Gtk.WrapMode.WORD)
            
            # Format mount details
            total_gb = mount_info.total_space / MountsManagerConfig.BYTES_TO_GB
            used_gb = mount_info.used_space / MountsManagerConfig.BYTES_TO_GB
            available_gb = mount_info.available_space / MountsManagerConfig.BYTES_TO_GB
            
            details = f"""Mount Point Details:

Device: {mount_info.device}
Mount Point: {mount_info.mountpoint}
Filesystem: {mount_info.filesystem}
Mount Options: {mount_info.options}

Disk Usage:
Total Size: {total_gb:.2f} GB ({mount_info.total_space:,} bytes)
Used Space: {used_gb:.2f} GB ({mount_info.used_space:,} bytes)
Available Space: {available_gb:.2f} GB ({mount_info.available_space:,} bytes)
Usage: {mount_info.usage_percent:.1f}%
"""
            
            text_buffer = text_view.get_buffer()
            text_buffer.set_text(details)
            
            scrolled.set_child(text_view)
            content_area.append(scrolled)
            
            # Add close button
            dialog.add_button("Close", Gtk.ResponseType.CLOSE)
            dialog.connect("response", lambda d, r: d.destroy())
            
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error showing mount properties: {e}")