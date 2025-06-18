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
import subprocess
import gi
from typing import Optional, Dict, List, Tuple, Any
from gi.repository import Gtk, GLib

class ServiceInfo:
    """Class to represent service information"""
    def __init__(self, name, status="unknown", enabled=False, service_type="systemd", 
                 description="", pid=None, memory_usage=0):
        self.name = name
        self.status = status  # active, inactive, failed, etc.
        self.enabled = enabled  # enabled/disabled for auto-start
        self.service_type = service_type  # systemd, init, autostart, etc.
        self.description = description
        self.pid = pid
        self.memory_usage = memory_usage

class ServicesManagerConfig:
    DEFAULT_UPDATE_INTERVAL = 5.0
    BYTES_TO_MB = 1024 * 1024

class ServicesManager:
    def __init__(self, logger, widget_factory=None):
        self.logger = logger
        self.widget_factory = widget_factory
        self.services = []  # List of ServiceInfo objects
        self.autostart_apps = []  # List of autostart applications
        
        # GUI components
        self.services_tree_view = None
        self.services_store = None
        self.services_selection = None
        
        # Filter options
        self.show_systemd_services = True
        self.show_autostart_apps = True
        self.show_only_running = False
        
    def _is_systemctl_available(self) -> bool:
        """Check if systemctl command is available"""
        try:
            subprocess.run(['systemctl', '--version'], capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def scan_systemd_services(self) -> List[ServiceInfo]:
        """Scan systemd services"""
        services = []
        try:
            # Check if systemctl is available
            if not self._is_systemctl_available():
                self.logger.info("systemctl not available, skipping systemd services scan")
                return services
                
            # Get list of all systemd services
            result = subprocess.run(
                ['systemctl', 'list-units', '--type=service', '--all', '--no-pager', '--plain'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # Skip header
                    if not line.strip() or line.startswith('●') or 'LOAD' in line:
                        continue
                    
                    parts = line.split()
                    if len(parts) >= 4:
                        unit_name = parts[0]
                        load_state = parts[1]
                        active_state = parts[2]
                        sub_state = parts[3]
                        description = ' '.join(parts[4:]) if len(parts) > 4 else ""
                        
                        # Only process .service units
                        if not unit_name.endswith('.service'):
                            continue
                        
                        service_name = unit_name.replace('.service', '')
                        
                        # Get enabled status
                        enabled = False
                        try:
                            enabled_result = subprocess.run(
                                ['systemctl', 'is-enabled', unit_name],
                                capture_output=True, text=True, timeout=5
                            )
                            enabled = enabled_result.stdout.strip() == 'enabled'
                        except:
                            pass
                        
                        # Get PID if service is active
                        pid = None
                        memory_mb = 0
                        if active_state == 'active':
                            try:
                                pid_result = subprocess.run(
                                    ['systemctl', 'show', unit_name, '--property=MainPID'],
                                    capture_output=True, text=True, timeout=5
                                )
                                if pid_result.returncode == 0:
                                    pid_line = pid_result.stdout.strip()
                                    if '=' in pid_line:
                                        pid_str = pid_line.split('=')[1]
                                        if pid_str.isdigit() and pid_str != '0':
                                            pid = int(pid_str)
                                            
                                            # Get memory usage
                                            memory_result = subprocess.run(
                                                ['systemctl', 'show', unit_name, '--property=MemoryCurrent'],
                                                capture_output=True, text=True, timeout=5
                                            )
                                            if memory_result.returncode == 0:
                                                mem_line = memory_result.stdout.strip()
                                                if '=' in mem_line:
                                                    mem_str = mem_line.split('=')[1]
                                                    if mem_str.isdigit():
                                                        memory_mb = int(mem_str) / ServicesManagerConfig.BYTES_TO_MB
                            except:
                                pass
                        
                        service_info = ServiceInfo(
                            name=service_name,
                            status=active_state,
                            enabled=enabled,
                            service_type="systemd",
                            description=description,
                            pid=pid,
                            memory_usage=memory_mb
                        )
                        
                        services.append(service_info)
            
        except FileNotFoundError:
            self.logger.info("systemctl command not found, skipping systemd services")
        except Exception as e:
            self.logger.error(f"Error scanning systemd services: {e}")
        
        return services

    def scan_autostart_applications(self) -> List[ServiceInfo]:
        """Scan autostart applications from .desktop files"""
        autostart_apps = []
        
        # Common autostart directories
        autostart_dirs = [
            os.path.expanduser('~/.config/autostart'),
            '/etc/xdg/autostart',
            '/usr/share/applications',  # Some apps here have autostart
        ]
        
        try:
            for autostart_dir in autostart_dirs:
                if not os.path.exists(autostart_dir):
                    continue
                
                for filename in os.listdir(autostart_dir):
                    if not filename.endswith('.desktop'):
                        continue
                    
                    desktop_file = os.path.join(autostart_dir, filename)
                    try:
                        with open(desktop_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        # Parse desktop file
                        name = filename.replace('.desktop', '')
                        description = ""
                        hidden = False
                        autostart_enabled = True
                        
                        for line in content.split('\n'):
                            line = line.strip()
                            if line.startswith('Name='):
                                name = line.split('=', 1)[1]
                            elif line.startswith('Comment='):
                                description = line.split('=', 1)[1]
                            elif line.startswith('Hidden='):
                                hidden = line.split('=', 1)[1].lower() == 'true'
                            elif line.startswith('X-GNOME-Autostart-enabled='):
                                autostart_enabled = line.split('=', 1)[1].lower() == 'true'
                        
                        # Only add if not hidden and in autostart directory
                        if not hidden and autostart_dir.endswith('autostart'):
                            service_info = ServiceInfo(
                                name=name,
                                status="enabled" if autostart_enabled else "disabled",
                                enabled=autostart_enabled,
                                service_type="autostart",
                                description=description
                            )
                            autostart_apps.append(service_info)
                    
                    except Exception as e:
                        continue  # Skip problematic files
                        
        except Exception as e:
            self.logger.error(f"Error scanning autostart applications: {e}")
        
        return autostart_apps

    def scan_init_services(self) -> List[ServiceInfo]:
        """Scan traditional init.d services (fallback)"""
        services = []
        
        try:
            init_dir = '/etc/init.d'
            if os.path.exists(init_dir):
                for filename in os.listdir(init_dir):
                    filepath = os.path.join(init_dir, filename)
                    if os.path.isfile(filepath) and os.access(filepath, os.X_OK):
                        # Check if service is running
                        status = "inactive"
                        try:
                            result = subprocess.run(
                                [filepath, 'status'],
                                capture_output=True, text=True, timeout=5
                            )
                            if result.returncode == 0:
                                status = "active"
                        except:
                            pass
                        
                        service_info = ServiceInfo(
                            name=filename,
                            status=status,
                            enabled=False,  # Hard to determine for init.d
                            service_type="init.d",
                            description=f"Init.d service: {filename}"
                        )
                        services.append(service_info)
                        
        except Exception as e:
            self.logger.error(f"Error scanning init.d services: {e}")
        
        return services

    def update_services(self):
        """Update the services and autostart applications list"""
        try:
            self.services = []
            self.autostart_apps = []
            
            if self.show_systemd_services:
                systemd_services = self.scan_systemd_services()
                self.services.extend(systemd_services)
                
                # Also scan init.d as fallback
                init_services = self.scan_init_services()
                self.services.extend(init_services)
            
            if self.show_autostart_apps:
                self.autostart_apps = self.scan_autostart_applications()
            
            # Update GUI if available
            if self.services_store:
                self.update_services_tree_view()
                
        except FileNotFoundError:
            self.logger.info("systemctl command not found, skipping systemd services scan")
        except Exception as e:
            self.logger.error(f"Error updating services: {e}")

    def create_services_tree_view(self) -> Gtk.TreeView:
        """Create the services tree view widget"""
        try:
            # Create list store (Name, Type, Status, Enabled, Description, PID, Memory)
            self.services_store = self.widget_factory.create_list_store([str, str, str, str, str, str, str])
            
            # Create tree view
            self.services_tree_view = self.widget_factory.create_tree_view(model=self.services_store)
            self.services_tree_view.set_headers_visible(True)
            
            # Create columns
            columns = [
                ("Name", 0, 200),
                ("Type", 1, 100),
                ("Status", 2, 100),
                ("Enabled", 3, 80),
                ("PID", 5, 80),
                ("Memory (MB)", 6, 100),
                ("Description", 4, 300)
            ]
            
            for title, column_id, width in columns:
                renderer = self.widget_factory.create_cell_renderer_text()
                column = self.widget_factory.create_tree_view_column(title, renderer, text_column=column_id)
                column.set_resizable(True)
                column.set_min_width(width)
                if column_id in [5, 6]:  # PID and Memory columns
                    column.set_alignment(1.0)  # Right align numbers
                    renderer.set_property("xalign", 1.0)
                self.services_tree_view.append_column(column)
            
            # Set up selection
            self.services_selection = self.services_tree_view.get_selection()
            self.services_selection.set_mode(Gtk.SelectionMode.SINGLE)
            
            # Right-click context menu removed - using static buttons instead
            
            return self.services_tree_view
            
        except Exception as e:
            self.logger.error(f"Error creating services tree view: {e}")
            return None

    def update_services_tree_view(self):
        """Update the services tree view with current data"""
        try:
            if not self.services_store:
                return
            
            # Clear existing data
            self.services_store.clear()
            
            # Combine services and autostart apps
            all_items = []
            
            for service in self.services:
                if self.show_only_running and service.status not in ['active', 'running']:
                    continue
                all_items.append(service)
            
            for app in self.autostart_apps:
                if self.show_only_running and app.status != 'enabled':
                    continue
                all_items.append(app)
            
            # Sort by name
            all_items.sort(key=lambda x: x.name.lower())
            
            # Add to store
            for item in all_items:
                enabled_str = "Yes" if item.enabled else "No"
                pid_str = str(item.pid) if item.pid else ""
                memory_str = f"{item.memory_usage:.1f}" if item.memory_usage > 0 else ""
                
                self.services_store.append([
                    item.name,
                    item.service_type,
                    item.status,
                    enabled_str,
                    item.description,
                    pid_str,
                    memory_str
                ])
                
        except Exception as e:
            self.logger.error(f"Error updating services tree view: {e}")

    def get_selected_service_info(self):
        """Get information about the currently selected service"""
        try:
            model, iter = self.services_selection.get_selected()
            if iter:
                service_name = model.get_value(iter, 0)
                service_type = model.get_value(iter, 1)
                service_status = model.get_value(iter, 2)
                return service_name, service_type, service_status
            return None, None, None
        except Exception as e:
            self.logger.error(f"Error getting selected service info: {e}")
            return None, None, None

    def control_systemd_service(self, service_name, action):
        """Control a systemd service (start, stop, restart, enable, disable)"""
        try:
            # Show confirmation for potentially disruptive actions
            if action in ['stop', 'disable']:
                self.show_service_action_confirmation(service_name, action)
            else:
                self.execute_systemd_action(service_name, action)
        except Exception as e:
            self.logger.error(f"Error controlling systemd service: {e}")

    def show_service_action_confirmation(self, service_name, action):
        """Show confirmation dialog for service actions"""
        try:
            dialog = self.widget_factory.create_message_dialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.YES_NO,
                text=f"{action.title()} Service?",
                secondary_text=(
                    f"Are you sure you want to {action} the service '{service_name}'?\n\n"
                    f"This action may affect system functionality."
                )
            )
            
            def on_dialog_response(dialog, response):
                if response == Gtk.ResponseType.YES:
                    self.execute_systemd_action(service_name, action)
                dialog.destroy()
            
            dialog.connect("response", on_dialog_response)
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error showing service action confirmation: {e}")

    def execute_systemd_action(self, service_name, action):
        """Execute a systemd action"""
        try:
            if not self._is_systemctl_available():
                self.logger.warning(f"Cannot execute systemctl {action} - systemctl not available")
                return
                
            service_unit = f"{service_name}.service"
            cmd = ["sudo", "systemctl", action, service_unit]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.logger.info(f"Successfully executed {action} on {service_name}")
                # Refresh services list after a short delay
                GLib.timeout_add(1000, self.update_services)
            else:
                error_msg = result.stderr or "Unknown error"
                self.logger.error(f"Failed to {action} {service_name}: {error_msg}")
                self.show_error_dialog(f"Service {action.title()} Failed", 
                                     f"Failed to {action} {service_name}:\n{error_msg}")
                
        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout while trying to {action} {service_name}")
            self.show_error_dialog("Service Action Timeout", 
                                 f"Timeout while trying to {action} {service_name}")
        except Exception as e:
            self.logger.error(f"Error executing {action} on {service_name}: {e}")
            self.show_error_dialog("Service Action Error", 
                                 f"Error executing {action} on {service_name}:\n{str(e)}")

    def toggle_autostart_app(self, app_name, enable):
        """Enable or disable an autostart application"""
        try:
            autostart_dir = os.path.expanduser('~/.config/autostart')
            desktop_file = os.path.join(autostart_dir, f"{app_name}.desktop")
            
            if not os.path.exists(desktop_file):
                # Look for the desktop file in system directories
                system_dirs = ['/etc/xdg/autostart', '/usr/share/applications']
                source_file = None
                
                for sys_dir in system_dirs:
                    candidate = os.path.join(sys_dir, f"{app_name}.desktop")
                    if os.path.exists(candidate):
                        source_file = candidate
                        break
                
                if not source_file:
                    self.show_error_dialog("Autostart Error", f"Could not find desktop file for {app_name}")
                    return
                
                # Create user autostart directory if it doesn't exist
                os.makedirs(autostart_dir, exist_ok=True)
                
                # Copy the desktop file to user autostart directory
                import shutil
                shutil.copy2(source_file, desktop_file)
            
            # Modify the desktop file to enable/disable autostart
            with open(desktop_file, 'r') as f:
                content = f.read()
            
            lines = content.split('\n')
            modified = False
            
            for i, line in enumerate(lines):
                if line.startswith('Hidden='):
                    lines[i] = f"Hidden={'false' if enable else 'true'}"
                    modified = True
                elif line.startswith('X-GNOME-Autostart-enabled='):
                    lines[i] = f"X-GNOME-Autostart-enabled={'true' if enable else 'false'}"
                    modified = True
            
            # Add the lines if they weren't found
            if not modified:
                if '[Desktop Entry]' in content:
                    for i, line in enumerate(lines):
                        if line.strip() == '[Desktop Entry]':
                            lines.insert(i + 1, f"Hidden={'false' if enable else 'true'}")
                            lines.insert(i + 2, f"X-GNOME-Autostart-enabled={'true' if enable else 'false'}")
                            break
            
            # Write back the modified content
            with open(desktop_file, 'w') as f:
                f.write('\n'.join(lines))
            
            self.logger.info(f"Successfully {'enabled' if enable else 'disabled'} autostart for {app_name}")
            # Refresh services list
            GLib.timeout_add(500, self.update_services)
            
        except Exception as e:
            self.logger.error(f"Error toggling autostart for {app_name}: {e}")
            self.show_error_dialog("Autostart Error", f"Error toggling autostart for {app_name}:\n{str(e)}")

    def show_service_properties(self, service_name, service_type):
        """Show detailed properties of a service"""
        try:
            # Create properties dialog
            dialog = self.widget_factory.create_dialog(title=f"Service Properties - {service_name}")
            dialog.set_default_size(600, 400)
            
            content_area = dialog.get_content_area()
            
            # Create scrolled window for service details
            scrolled = self.widget_factory.create_scrolled_window(
                policy=(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            )
            
            text_view = self.widget_factory.create_text_view()
            text_view.set_editable(False)
            text_view.set_wrap_mode(Gtk.WrapMode.WORD)
            
            # Get detailed service information
            if service_type == "systemd":
                details = self.get_systemd_service_details(service_name)
            elif service_type == "autostart":
                details = self.get_autostart_app_details(service_name)
            else:
                details = f"Service: {service_name}\nType: {service_type}\n\nNo detailed information available."
            
            text_buffer = text_view.get_buffer()
            text_buffer.set_text(details)
            
            scrolled.set_child(text_view)
            content_area.append(scrolled)
            
            # Add close button
            dialog.add_button("Close", Gtk.ResponseType.CLOSE)
            dialog.connect("response", lambda d, r: d.destroy())
            
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error showing service properties: {e}")

    def get_systemd_service_details(self, service_name):
        """Get detailed information about a systemd service"""
        try:
            service_unit = f"{service_name}.service"
            
            # Get service status
            result = subprocess.run(
                ['systemctl', 'status', service_unit, '--no-pager'],
                capture_output=True, text=True, timeout=10
            )
            
            status_output = result.stdout if result.returncode == 0 else "Status information not available"
            
            # Get service properties
            properties_result = subprocess.run(
                ['systemctl', 'show', service_unit],
                capture_output=True, text=True, timeout=10
            )
            
            properties = "Properties not available"
            if properties_result.returncode == 0:
                # Parse important properties
                props = {}
                for line in properties_result.stdout.split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        props[key] = value
                
                important_props = [
                    'Description', 'LoadState', 'ActiveState', 'SubState',
                    'UnitFileState', 'MainPID', 'ExecStart', 'ExecReload',
                    'MemoryCurrent', 'TasksCurrent', 'RestartSec'
                ]
                
                properties = "Service Properties:\n"
                for prop in important_props:
                    if prop in props and props[prop]:
                        properties += f"{prop}: {props[prop]}\n"
            
            details = f"""Service Details: {service_name}

{status_output}

{properties}
"""
            return details
            
        except Exception as e:
            return f"Error getting service details: {e}"

    def get_autostart_app_details(self, app_name):
        """Get details about an autostart application"""
        try:
            # Look for desktop file
            desktop_files = [
                os.path.expanduser(f'~/.config/autostart/{app_name}.desktop'),
                f'/etc/xdg/autostart/{app_name}.desktop',
                f'/usr/share/applications/{app_name}.desktop'
            ]
            
            desktop_file = None
            for candidate in desktop_files:
                if os.path.exists(candidate):
                    desktop_file = candidate
                    break
            
            if not desktop_file:
                return f"Desktop file not found for {app_name}"
            
            with open(desktop_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            details = f"""Autostart Application: {app_name}

Desktop File: {desktop_file}

Desktop File Contents:
{content}
"""
            return details
            
        except Exception as e:
            return f"Error getting autostart app details: {e}"

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

    def get_services_summary(self) -> str:
        """Get a summary of services"""
        try:
            total_services = len(self.services)
            total_autostart = len(self.autostart_apps)
            active_services = len([s for s in self.services if s.status == 'active'])
            return f"Services: {active_services}/{total_services} active, {total_autostart} autostart apps"
        except:
            return "Services: N/A"

    def set_filter_options(self, show_systemd=True, show_autostart=True, show_only_running=False):
        """Set filter options for the services display"""
        self.show_systemd_services = show_systemd
        self.show_autostart_apps = show_autostart
        self.show_only_running = show_only_running
        
        # Refresh the display
        if self.services_store:
            self.update_services_tree_view()