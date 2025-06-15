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
import signal
import subprocess
import time
import gi
from typing import Optional, Dict, List, Tuple, Any
from gi.repository import Gtk, GLib, GObject

# Try to import psutil, but provide fallback if not available
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

class ProcessInfo:
    """Class to represent process information"""
    def __init__(self, pid, name, ppid=None, cpu_percent=0.0, memory_percent=0.0, 
                 memory_mb=0.0, status="", user="", cmdline=""):
        self.pid = pid
        self.name = name
        self.ppid = ppid
        self.cpu_percent = cpu_percent
        self.memory_percent = memory_percent
        self.memory_mb = memory_mb
        self.status = status
        self.user = user
        self.cmdline = cmdline
        self.children = []  # List of child processes

class ProcessManagerConfig:
    DEFAULT_UPDATE_INTERVAL = 2.0
    MIN_UPDATE_INTERVAL = 0.1
    MAX_UPDATE_INTERVAL = 20.0
    MAX_PROCESSES_DISPLAY = 1000
    BYTES_TO_MB = 1024 * 1024

class ProcessManager:
    def __init__(self, logger, config_manager=None, privileged_actions=None, widget_factory=None):
        self.logger = logger
        self.config_manager = config_manager
        self.privileged_actions = privileged_actions
        self.widget_factory = widget_factory
        self.processes = {}  # Dict of PID -> ProcessInfo
        self.process_tree = []  # Root processes (no parent or parent not found)
        
        # GUI components
        self.process_tree_view = None
        self.process_store = None
        self.process_selection = None
        
        # Context menu and selection tracking
        self.context_menu = None
        self.selected_pid = None
        self.selected_process_pid = None  # For compatibility with main.py
        
        # Update interval configuration
        if config_manager:
            self.update_interval = float(config_manager.get_setting("Settings", "update_interval", str(ProcessManagerConfig.DEFAULT_UPDATE_INTERVAL)))
        else:
            self.update_interval = ProcessManagerConfig.DEFAULT_UPDATE_INTERVAL

    def scan_processes(self) -> Dict[int, ProcessInfo]:
        """Scan all running processes and return process information"""
        try:
            if PSUTIL_AVAILABLE:
                return self.scan_processes_psutil()
            else:
                return self.scan_processes_proc()
        except Exception as e:
            self.logger.error(f"Error scanning processes: {e}")
            return {}

    def scan_processes_psutil(self) -> Dict[int, ProcessInfo]:
        """Scan processes using psutil library"""
        processes = {}
        
        for proc in psutil.process_iter(['pid', 'ppid', 'name', 'username', 'status', 'cmdline']):
            try:
                pinfo = proc.info
                pid = pinfo['pid']
                
                # Get CPU and memory usage
                try:
                    cpu_percent = proc.cpu_percent(interval=None)
                    memory_info = proc.memory_info()
                    memory_mb = memory_info.rss / ProcessManagerConfig.BYTES_TO_MB
                    memory_percent = proc.memory_percent()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    cpu_percent = 0.0
                    memory_mb = 0.0
                    memory_percent = 0.0
                
                # Create ProcessInfo object
                cmdline = ' '.join(pinfo.get('cmdline', []))
                if not cmdline:
                    cmdline = pinfo.get('name', '')
                
                process_info = ProcessInfo(
                    pid=pid,
                    name=pinfo.get('name', 'Unknown'),
                    ppid=pinfo.get('ppid'),
                    cpu_percent=cpu_percent,
                    memory_percent=memory_percent,
                    memory_mb=memory_mb,
                    status=pinfo.get('status', ''),
                    user=pinfo.get('username', ''),
                    cmdline=cmdline
                )
                
                processes[pid] = process_info
                
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
                
        return processes

    def scan_processes_proc(self) -> Dict[int, ProcessInfo]:
        """Scan processes using /proc filesystem (fallback when psutil unavailable)"""
        processes = {}
        
        try:
            # Get total memory for percentage calculations
            try:
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if line.startswith('MemTotal:'):
                            total_memory_kb = int(line.split()[1])
                            break
                    else:
                        total_memory_kb = 1024 * 1024  # 1GB fallback
            except:
                total_memory_kb = 1024 * 1024  # 1GB fallback
            
            # Scan /proc for process directories
            for entry in os.listdir('/proc'):
                if not entry.isdigit():
                    continue
                
                pid = int(entry)
                proc_dir = f'/proc/{pid}'
                
                try:
                    # Read process status
                    status_file = f'{proc_dir}/status'
                    stat_file = f'{proc_dir}/stat'
                    cmdline_file = f'{proc_dir}/cmdline'
                    
                    if not os.path.exists(status_file):
                        continue
                    
                    # Parse status file
                    name = "Unknown"
                    ppid = None
                    memory_kb = 0
                    status = ""
                    
                    with open(status_file, 'r') as f:
                        for line in f:
                            if line.startswith('Name:'):
                                name = line.split()[1]
                            elif line.startswith('PPid:'):
                                ppid = int(line.split()[1])
                            elif line.startswith('VmRSS:'):
                                memory_kb = int(line.split()[1])
                            elif line.startswith('State:'):
                                status = line.split()[1]
                    
                    # Calculate memory percentage and MB
                    memory_mb = memory_kb / 1024.0
                    memory_percent = (memory_kb / total_memory_kb) * 100
                    
                    # Get command line
                    cmdline = ""
                    try:
                        with open(cmdline_file, 'r') as f:
                            cmdline = f.read().replace('\x00', ' ').strip()
                    except:
                        cmdline = name
                    
                    if not cmdline:
                        cmdline = name
                    
                    # Get user (simplified)
                    try:
                        stat_info = os.stat(proc_dir)
                        import pwd
                        user = pwd.getpwuid(stat_info.st_uid).pw_name
                    except:
                        user = "unknown"
                    
                    # CPU percentage is complex to calculate from /proc, so we'll set it to 0 for now
                    cpu_percent = 0.0
                    
                    process_info = ProcessInfo(
                        pid=pid,
                        name=name,
                        ppid=ppid,
                        cpu_percent=cpu_percent,
                        memory_percent=memory_percent,
                        memory_mb=memory_mb,
                        status=status,
                        user=user,
                        cmdline=cmdline
                    )
                    
                    processes[pid] = process_info
                    
                except (IOError, OSError, ValueError):
                    # Process may have disappeared or we don't have permission
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error scanning /proc: {e}")
        
        return processes

    def build_process_tree(self, processes: Dict[int, ProcessInfo]) -> List[ProcessInfo]:
        """Build a hierarchical process tree from flat process list"""
        try:
            # First, link children to their parents
            for pid, proc in processes.items():
                if proc.ppid and proc.ppid in processes:
                    parent = processes[proc.ppid]
                    parent.children.append(proc)
            
            # Find root processes (processes with no parent or parent not in our list)
            root_processes = []
            for pid, proc in processes.items():
                if not proc.ppid or proc.ppid not in processes:
                    root_processes.append(proc)
            
            # Sort root processes by name
            root_processes.sort(key=lambda p: p.name.lower())
            
            return root_processes
            
        except Exception as e:
            self.logger.error(f"Error building process tree: {e}")
            return []

    def update_processes(self):
        """Update the process list and tree structure"""
        try:
            # Scan current processes
            new_processes = self.scan_processes()
            
            # Build process tree
            self.process_tree = self.build_process_tree(new_processes)
            self.processes = new_processes
            
            # Update GUI if available
            if self.process_store:
                self.update_process_tree_view()
                
        except Exception as e:
            self.logger.error(f"Error updating processes: {e}")

    def create_process_tree_view(self) -> Gtk.TreeView:
        """Create the process tree view widget"""
        try:
            # Create tree store (PID, Name, CPU%, Memory%, Memory MB, Status, User)
            self.process_store = Gtk.TreeStore(int, str, str, str, str, str, str, str)
            
            # Create tree view
            self.process_tree_view = Gtk.TreeView(model=self.process_store)
            self.process_tree_view.set_headers_visible(True)
            self.process_tree_view.set_enable_tree_lines(True)
            
            # Create columns
            columns = [
                ("PID", 0, 60),
                ("Process Name", 1, 200),
                ("CPU %", 2, 80),
                ("Memory %", 3, 80),
                ("Memory (MB)", 4, 100),
                ("Status", 5, 80),
                ("User", 6, 100),
                ("Command Line", 7, 300)
            ]
            
            for title, column_id, width in columns:
                renderer = Gtk.CellRendererText()
                column = Gtk.TreeViewColumn(title, renderer, text=column_id)
                column.set_resizable(True)
                column.set_min_width(width)
                if column_id in [2, 3, 4]:  # CPU and Memory columns
                    column.set_alignment(1.0)  # Right align numbers
                    renderer.set_property("xalign", 1.0)
                self.process_tree_view.append_column(column)
            
            # Set up selection
            self.process_selection = self.process_tree_view.get_selection()
            self.process_selection.set_mode(Gtk.SelectionMode.SINGLE)
            
            # Note: Context menu now handled by selection-based menu bar in main UI
            
            return self.process_tree_view
            
        except Exception as e:
            self.logger.error(f"Error creating process tree view: {e}")
            return None

    def update_process_tree_view(self):
        """Update the process tree view with current process data"""
        try:
            if not self.process_store:
                return
            
            # Save current expansion, selection, and scroll state
            expanded_paths = self._save_expansion_state()
            selected_pid = self._save_selection_state()
            scroll_position = self._save_scroll_position()
            
            # For debugging, let's temporarily disable in-place updates and add logging
            # to see if the problem is elsewhere
            self.logger.info("Process tree view update starting...")
            
            # Try just updating without clearing first
            self._update_tree_store_without_flashing()
            
            # Restore expansion, selection, and scroll state
            self._restore_expansion_state(expanded_paths)
            self._restore_selection_state(selected_pid)
            self._restore_scroll_position(scroll_position)
            
        except Exception as e:
            self.logger.error(f"Error updating process tree view: {e}")
    
    def _save_expansion_state(self):
        """Save the current expansion state of the tree view"""
        expanded_paths = set()
        try:
            if not self.process_tree_view:
                return expanded_paths
                
            def check_expanded(model, path, iter, data):
                if self.process_tree_view.row_expanded(path):
                    # Get PID to identify the row reliably
                    pid = model.get_value(iter, 0)
                    expanded_paths.add(pid)
                return False
            
            self.process_store.foreach(check_expanded, None)
        except Exception as e:
            self.logger.error(f"Error saving expansion state: {e}")
        
        return expanded_paths
    
    def _restore_expansion_state(self, expanded_pids):
        """Restore the expansion state of the tree view"""
        try:
            if not expanded_pids or not self.process_tree_view:
                return
                
            def restore_expanded(model, path, iter, data):
                pid = model.get_value(iter, 0)
                if pid in expanded_pids:
                    self.process_tree_view.expand_row(path, False)
                return False
            
            # Use GLib.idle_add to ensure the tree is fully built before expanding
            GLib.idle_add(lambda: self.process_store.foreach(restore_expanded, None))
            
        except Exception as e:
            self.logger.error(f"Error restoring expansion state: {e}")
    
    def _save_selection_state(self):
        """Save the currently selected process PID"""
        try:
            if not self.process_selection:
                return None
            
            model, tree_iter = self.process_selection.get_selected()
            if tree_iter:
                return model.get_value(tree_iter, 0)  # Return PID
            return None
        except Exception as e:
            self.logger.error(f"Error saving selection state: {e}") 
            return None
    
    def _restore_selection_state(self, selected_pid):
        """Restore the selection state by PID"""
        try:
            if not selected_pid or not self.process_tree_view or not self.process_selection:
                return
            
            def find_and_select(model, path, iter, data):
                pid = model.get_value(iter, 0)
                if pid == selected_pid:
                    self.process_selection.select_iter(iter)
                    # Scroll to the selected row
                    self.process_tree_view.scroll_to_cell(path, None, True, 0.5, 0.0)
                    return True  # Stop iteration
                return False
            
            # Use GLib.idle_add to ensure the tree is fully built before selecting
            GLib.idle_add(lambda: self.process_store.foreach(find_and_select, None))
            
        except Exception as e:
            self.logger.error(f"Error restoring selection state: {e}")
    
    def _save_scroll_position(self):
        """Save the current scroll position of the tree view"""
        try:
            if not self.process_tree_view or not self.process_tree_view.get_parent():
                return None
            
            # Get the scrolled window that contains the tree view
            scrolled_window = self.process_tree_view.get_parent()
            if hasattr(scrolled_window, 'get_vadjustment'):
                vadj = scrolled_window.get_vadjustment()
                return vadj.get_value()
            return None
        except Exception as e:
            self.logger.error(f"Error saving scroll position: {e}")
            return None
    
    def _restore_scroll_position(self, scroll_position):
        """Restore the scroll position of the tree view"""
        try:
            if scroll_position is None or not self.process_tree_view or not self.process_tree_view.get_parent():
                return
            
            # Get the scrolled window that contains the tree view
            scrolled_window = self.process_tree_view.get_parent()
            if hasattr(scrolled_window, 'get_vadjustment'):
                vadj = scrolled_window.get_vadjustment()
                # Use GLib.idle_add to ensure the tree is fully updated before scrolling
                GLib.idle_add(lambda: vadj.set_value(scroll_position))
                
        except Exception as e:
            self.logger.error(f"Error restoring scroll position: {e}")
    
    def _update_tree_store_in_place(self):
        """Update the tree store in-place to prevent flashing"""
        try:
            # For now, let's try a simpler approach - just update existing rows without adding/removing
            # This should prevent most flashing while we debug the full implementation
            
            # Create a mapping of existing PIDs to their tree iters and data
            existing_pids = {}
            
            def collect_existing_pids(model, path, iter, data):
                pid = model.get_value(iter, 0)
                existing_pids[pid] = iter
                return False
            
            self.process_store.foreach(collect_existing_pids, None)
            
            # Get current process data
            current_processes = {}
            self._flatten_process_tree(self.process_tree, current_processes)
            
            # Count how many new processes we have
            new_processes = 0
            removed_processes = 0
            
            for pid in current_processes:
                if pid not in existing_pids:
                    new_processes += 1
            
            for pid in existing_pids:
                if pid not in current_processes:
                    removed_processes += 1
            
            # If there are significant changes in process count, fall back to full rebuild
            # Otherwise, just update existing processes
            if new_processes > 5 or removed_processes > 5:
                self.logger.info(f"Too many process changes (new: {new_processes}, removed: {removed_processes}), falling back to full rebuild")
                self._fallback_to_full_rebuild()
                return
            
            # Update existing processes only
            for pid, process_info in current_processes.items():
                if pid in existing_pids:
                    tree_iter = existing_pids[pid]
                    self._update_process_row(tree_iter, process_info)
            
            # Only remove a few processes if needed
            pids_to_remove = []
            for pid in existing_pids:
                if pid not in current_processes:
                    pids_to_remove.append(pid)
            
            for pid in pids_to_remove:
                if pid in existing_pids:
                    self.process_store.remove(existing_pids[pid])
            
            # Add new processes if there are only a few
            for pid, process_info in current_processes.items():
                if pid not in existing_pids:
                    self._add_single_process_to_store(process_info)
            
        except Exception as e:
            self.logger.error(f"Error updating tree store in-place: {e}")
            self._fallback_to_full_rebuild()
    
    def _flatten_process_tree(self, process_list, result_dict, parent_pid=None):
        """Flatten the process tree into a simple PID -> ProcessInfo mapping"""
        for process_info in process_list:
            result_dict[process_info.pid] = process_info
            if process_info.children:
                self._flatten_process_tree(process_info.children, result_dict, process_info.pid)
    
    def _update_process_row(self, tree_iter, process_info):
        """Update a single process row in the tree store"""
        try:
            # Update all columns with new data
            self.process_store.set(tree_iter, [
                0,  # PID (shouldn't change)
                1,  # Name
                2,  # CPU %
                3,  # Memory %
                4,  # Memory MB
                5,  # Status
                6,  # User
                7   # Command Line
            ], [
                process_info.pid,
                process_info.name,
                f"{process_info.cpu_percent:.1f}",
                f"{process_info.memory_percent:.1f}",
                f"{process_info.memory_mb:.1f}",
                process_info.status,
                process_info.user,
                process_info.cmdline[:100] + "..." if len(process_info.cmdline) > 100 else process_info.cmdline
            ])
        except Exception as e:
            self.logger.error(f"Error updating process row: {e}")
    
    def _fallback_to_full_rebuild(self):
        """Fallback to the original clear-and-rebuild method"""
        try:
            # Clear existing data
            self.process_store.clear()
            
            # Add processes to tree store
            self._add_processes_to_store(None, self.process_tree)
            
        except Exception as e:
            self.logger.error(f"Error in fallback rebuild: {e}")
    
    def _add_single_process_to_store(self, process_info):
        """Add a single process to the tree store (without hierarchy for now)"""
        try:
            # For simplicity, add as top-level process (could enhance to maintain hierarchy later)
            self.process_store.append(None, [
                process_info.pid,
                process_info.name,
                f"{process_info.cpu_percent:.1f}",
                f"{process_info.memory_percent:.1f}",
                f"{process_info.memory_mb:.1f}",
                process_info.status,
                process_info.user,
                process_info.cmdline[:100] + "..." if len(process_info.cmdline) > 100 else process_info.cmdline
            ])
        except Exception as e:
            self.logger.error(f"Error adding single process to store: {e}")
    
    def _update_tree_store_without_flashing(self):
        """Simple approach: just update existing data without clearing"""
        try:
            # Create a mapping of existing PIDs to their tree iters
            existing_pids = {}
            
            def collect_existing_pids(model, path, iter, data):
                pid = model.get_value(iter, 0)
                existing_pids[pid] = iter
                return False
            
            self.process_store.foreach(collect_existing_pids, None)
            self.logger.info(f"Found {len(existing_pids)} existing processes in tree view")
            
            # Get current process data
            current_processes = {}
            self._flatten_process_tree(self.process_tree, current_processes)
            self.logger.info(f"Current scan found {len(current_processes)} processes")
            
            # Update existing processes with new data
            updated_count = 0
            for pid, process_info in current_processes.items():
                if pid in existing_pids:
                    tree_iter = existing_pids[pid]
                    self._update_process_row(tree_iter, process_info)
                    updated_count += 1
            
            self.logger.info(f"Updated {updated_count} existing processes")
            
            # If we have significantly different process counts, fall back to full rebuild
            if abs(len(current_processes) - len(existing_pids)) > 10:
                self.logger.info("Process count changed significantly, doing full rebuild")
                self._fallback_to_full_rebuild()
            
        except Exception as e:
            self.logger.error(f"Error in simplified update: {e}")
            self._fallback_to_full_rebuild()

    def _add_processes_to_store(self, parent_iter, processes):
        """Recursively add processes to the tree store"""
        try:
            for proc in processes:
                # Format data for display
                cpu_str = f"{proc.cpu_percent:.1f}"
                memory_str = f"{proc.memory_percent:.1f}"
                memory_mb_str = f"{proc.memory_mb:.1f}"
                
                # Add process to store
                iter = self.process_store.append(parent_iter, [
                    proc.pid,
                    proc.name,
                    cpu_str,
                    memory_str,
                    memory_mb_str,
                    proc.status,
                    proc.user,
                    proc.cmdline
                ])
                
                # Add children recursively
                if proc.children:
                    # Sort children by name
                    proc.children.sort(key=lambda p: p.name.lower())
                    self._add_processes_to_store(iter, proc.children)
                    
        except Exception as e:
            self.logger.error(f"Error adding processes to store: {e}")

    # Old context menu methods removed - now using selection-based menu bar in main UI

    def end_process(self, pid, sig):
        """End a process with the specified signal"""
        try:
            self.logger.info(f"end_process called: pid={pid}, signal={sig}")
            
            # Get process info
            if pid not in self.processes:
                self.logger.error(f"Process {pid} not found")
                return
            
            proc_info = self.processes[pid]
            signal_name = "SIGTERM" if sig == signal.SIGTERM else "SIGKILL"
            
            self.logger.info(f"Showing confirmation dialog for {proc_info.name} (user: {proc_info.user})")
            
            # Show confirmation dialog
            self.show_kill_confirmation_dialog(pid, proc_info.name, signal_name, sig)
            
        except Exception as e:
            self.logger.error(f"Error ending process {pid}: {e}")

    def show_kill_confirmation_dialog(self, pid, process_name, signal_name, sig):
        """Show confirmation dialog before killing process"""
        try:
            dialog = Gtk.MessageDialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.YES_NO,
                text=f"End Process?"
            )
            
            dialog.format_secondary_text(
                f"Are you sure you want to {signal_name} process '{process_name}' (PID: {pid})?\n\n"
                f"This action cannot be undone and may cause data loss."
            )
            
            def on_dialog_response(dialog, response):
                if response == Gtk.ResponseType.YES:
                    self.kill_process_confirmed(pid, sig)
                dialog.destroy()
            
            dialog.connect("response", on_dialog_response)
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error showing kill confirmation dialog: {e}")

    def kill_process_confirmed(self, pid, sig):
        """Actually kill the process after confirmation"""
        try:
            self.logger.info(f"kill_process_confirmed called: pid={pid}, signal={sig}")
            
            if PSUTIL_AVAILABLE:
                # Try using psutil first
                try:
                    proc = psutil.Process(pid)
                    self.logger.info(f"Using psutil to kill process {pid}")
                    if sig == signal.SIGKILL:
                        proc.kill()
                    else:
                        proc.terminate()
                    self.logger.info(f"Successfully sent signal {sig} to process {pid}")
                except psutil.NoSuchProcess:
                    self.logger.warning(f"Process {pid} no longer exists")
                except psutil.AccessDenied as e:
                    self.logger.info(f"Access denied for process {pid}, trying pkexec: {e}")
                    # Try with pkexec
                    self.kill_process_with_pkexec(pid, sig)
                    return  # Don't refresh process list here, pkexec will handle it
                except Exception as e:
                    self.logger.error(f"Unexpected error with psutil: {e}")
                    # Try with pkexec as fallback
                    self.kill_process_with_pkexec(pid, sig)
                    return
            else:
                # Use OS kill when psutil not available
                try:
                    self.logger.info(f"Using os.kill to kill process {pid}")
                    os.kill(pid, sig)
                    self.logger.info(f"Successfully sent signal {sig} to process {pid}")
                except OSError as e:
                    self.logger.info(f"os.kill failed for process {pid}: errno={e.errno}, {e}")
                    if e.errno == 1:  # Operation not permitted
                        self.kill_process_with_pkexec(pid, sig)
                        return  # Don't refresh process list here, pkexec will handle it
                    elif e.errno == 3:  # No such process
                        self.logger.warning(f"Process {pid} no longer exists")
                    else:
                        self.logger.error(f"Error killing process {pid}: {e}")
            
            # Refresh process list after a short delay
            GLib.timeout_add(500, self.update_processes)
            
        except Exception as e:
            self.logger.error(f"Error killing process {pid}: {e}")

    def kill_process_with_pkexec(self, pid, sig):
        """Kill process using pkexec when access is denied"""
        try:
            self.logger.info(f"kill_process_with_pkexec called: pid={pid}, signal={sig}")
            
            if not self.privileged_actions:
                self.logger.error("Privileged actions not available")
                self._show_error_dialog("Error", "Privileged actions not available")
                return
            
            # Get process info for user confirmation
            proc_info = self.processes.get(pid)
            if not proc_info:
                self.logger.error(f"Process {pid} not found")
                return
            
            self.logger.info(f"Showing pkexec confirmation for {proc_info.name} (user: {proc_info.user})")
            
            # Show confirmation dialog first
            self._show_pkexec_confirmation_dialog(pid, sig, proc_info)
                
        except Exception as e:
            self.logger.error(f"Error killing process {pid} with pkexec: {e}")
    
    def _show_pkexec_confirmation_dialog(self, pid, sig, proc_info):
        """Show confirmation dialog before using pkexec"""
        try:
            signal_name = {
                signal.SIGTERM: "terminate",
                signal.SIGKILL: "force kill", 
                signal.SIGSTOP: "pause",
                signal.SIGCONT: "resume"
            }.get(sig, f"send signal {sig} to")
            
            dialog = Gtk.MessageDialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Administrative Privileges Required"
            )
            
            dialog.format_secondary_text(
                f"To {signal_name} process '{proc_info.name}' (PID: {pid}) owned by '{proc_info.user}', "
                f"administrative privileges are required.\n\n"
                f"You will be prompted for authentication. Do you want to continue?"
            )
            
            def on_dialog_response(dialog, response):
                if response == Gtk.ResponseType.YES:
                    dialog.destroy()
                    self._execute_pkexec_kill(pid, sig, proc_info)
                else:
                    dialog.destroy()
            
            dialog.connect("response", on_dialog_response)
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error showing pkexec confirmation dialog: {e}")
    
    def _execute_pkexec_kill(self, pid, sig, proc_info):
        """Execute pkexec kill command using existing PrivilegedActions"""
        try:
            signal_num = int(sig)
            
            # Build the kill command
            cmd = f"kill -{signal_num} {pid}"
            
            self.logger.info(f"Executing pkexec command: {cmd}")
            
            # Define success and failure callbacks
            def on_success():
                self.logger.info(f"pkexec SUCCESS: terminated process {pid}")
                self._show_success_dialog(f"Process '{proc_info.name}' (PID: {pid}) terminated successfully")
                # Refresh process list after a short delay
                GLib.timeout_add(500, self.update_processes)
            
            def on_failure(reason):
                self.logger.info(f"pkexec FAILED: reason={reason}")
                if reason == 'canceled':
                    self.logger.info("pkexec operation cancelled by user")
                else:
                    self._show_error_dialog("Operation Failed", 
                                           f"Failed to terminate process: {reason}")
            
            # Use the existing PrivilegedActions class
            self.privileged_actions.run_pkexec_command(
                cmd, 
                success_callback=on_success,
                failure_callback=on_failure
            )
            
        except Exception as e:
            self.logger.error(f"Error executing pkexec kill: {e}")
            self._show_error_dialog("Error", f"Failed to execute command: {str(e)}")
    
    def _show_success_dialog(self, message):
        """Show success dialog"""
        try:
            dialog = Gtk.MessageDialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Success"
            )
            dialog.format_secondary_text(message)
            
            def on_dialog_response(dialog, response):
                dialog.destroy()
            
            dialog.connect("response", on_dialog_response)
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error showing success dialog: {e}")
    
    def _show_error_dialog(self, title, message):
        """Show error dialog"""
        try:
            dialog = Gtk.MessageDialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=title
            )
            dialog.format_secondary_text(message)
            
            def on_dialog_response(dialog, response):
                dialog.destroy()
            
            dialog.connect("response", on_dialog_response)
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error showing error dialog: {e}")

    def show_process_properties(self, pid):
        """Show detailed properties of a process"""
        try:
            if pid not in self.processes:
                return
            
            proc_info = self.processes[pid]
            
            # Create properties dialog
            dialog = Gtk.Dialog(title=f"Process Properties - {proc_info.name}")
            dialog.set_default_size(500, 400)
            
            content_area = dialog.get_content_area()
            
            # Create scrolled window for process details
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            
            text_view = Gtk.TextView()
            text_view.set_editable(False)
            text_view.set_wrap_mode(Gtk.WrapMode.WORD)
            
            # Get detailed process information
            try:
                if PSUTIL_AVAILABLE:
                    proc = psutil.Process(pid)
                    details = f"""Process Details:

PID: {proc_info.pid}
Name: {proc_info.name}
Status: {proc_info.status}
User: {proc_info.user}
CPU Usage: {proc_info.cpu_percent:.1f}%
Memory Usage: {proc_info.memory_percent:.1f}% ({proc_info.memory_mb:.1f} MB)
Parent PID: {proc_info.ppid or 'None'}

Command Line:
{proc_info.cmdline}

Working Directory: {proc.cwd() if hasattr(proc, 'cwd') else 'N/A'}
Create Time: {proc.create_time() if hasattr(proc, 'create_time') else 'N/A'}
"""
                else:
                    # Basic details when psutil not available
                    details = f"""Process Details:

PID: {proc_info.pid}
Name: {proc_info.name}
Status: {proc_info.status}
User: {proc_info.user}
CPU Usage: {proc_info.cpu_percent:.1f}%
Memory Usage: {proc_info.memory_percent:.1f}% ({proc_info.memory_mb:.1f} MB)
Parent PID: {proc_info.ppid or 'None'}

Command Line:
{proc_info.cmdline}

Note: Install psutil for more detailed process information.
"""
            except Exception as e:
                details = f"Error getting detailed process information: {e}"
            
            text_buffer = text_view.get_buffer()
            text_buffer.set_text(details)
            
            scrolled.set_child(text_view)
            content_area.append(scrolled)
            
            # Add close button
            dialog.add_button("Close", Gtk.ResponseType.CLOSE)
            dialog.connect("response", lambda d, r: d.destroy())
            
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error showing process properties: {e}")

    def set_update_interval(self, interval: float) -> None:
        """Set the update interval for process monitoring"""
        self.update_interval = max(ProcessManagerConfig.MIN_UPDATE_INTERVAL, 
                                 min(ProcessManagerConfig.MAX_UPDATE_INTERVAL, interval))
        self.logger.info(f"Process update interval set to {self.update_interval} seconds")
        if self.config_manager:
            self.config_manager.set_setting("Settings", "update_interval", f"{self.update_interval:.1f}")
    
    def get_update_interval_ms(self) -> int:
        """Get the update interval in milliseconds for GLib.timeout_add"""
        return int(self.update_interval * 1000)
    
    def execute_process_action(self, action_type: str, selected_pid: int = None):
        """Execute process actions for selected process"""
        try:
            self.logger.info(f"execute_process_action called: action={action_type}, pid={selected_pid}")
            
            if not selected_pid:
                self.logger.warning("No process selected for action")
                return
            
            # Check if process exists
            if selected_pid not in self.processes:
                self.logger.error(f"Process {selected_pid} not found in process list")
                return
            
            proc_info = self.processes[selected_pid]
            self.logger.info(f"Process info: name={proc_info.name}, user={proc_info.user}")
            
            signal_map = {
                'end': signal.SIGTERM,
                'kill': signal.SIGKILL,
                'stop': signal.SIGSTOP,
                'continue': signal.SIGCONT
            }
            
            if action_type in signal_map:
                self.logger.info(f"Calling end_process for {selected_pid} with signal {signal_map[action_type]}")
                self.end_process(selected_pid, signal_map[action_type])
            elif action_type == 'restart':
                self._restart_process(selected_pid)
            elif action_type == 'properties':
                self.show_process_properties(selected_pid)
            else:
                self.logger.error(f"Unknown process action: {action_type}")
                
        except Exception as e:
            self.logger.error(f"Error executing process action {action_type}: {e}")
    
    def _restart_process(self, pid: int):
        """Restart a process (terminate and let system restart it)"""
        try:
            if pid not in self.processes:
                self.logger.error(f"Process {pid} not found")
                return
            
            proc_info = self.processes[pid]
            
            # Show confirmation dialog first
            dialog = Gtk.MessageDialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Restart Process?"
            )
            
            dialog.format_secondary_text(
                f"Are you sure you want to restart process '{proc_info.name}' (PID: {pid})?\n\n"
                f"This will terminate the process and rely on the system to restart it. "
                f"Note that not all processes will automatically restart."
            )
            
            def on_dialog_response(dialog, response):
                if response == Gtk.ResponseType.YES:
                    dialog.destroy()
                    self.logger.info(f"Attempting to restart process {proc_info.name} (PID: {pid})")
                    # Use SIGTERM to gracefully terminate the process
                    self.end_process(pid, signal.SIGTERM)
                else:
                    dialog.destroy()
            
            dialog.connect("response", on_dialog_response)
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error restarting process {pid}: {e}")
    
    def update_selected_process(self):
        """Update the currently selected process PID"""
        try:
            if not self.process_selection:
                self.selected_process_pid = None
                return
            
            model, tree_iter = self.process_selection.get_selected()
            if tree_iter:
                self.selected_process_pid = model.get_value(tree_iter, 0)  # Get PID from first column
            else:
                self.selected_process_pid = None
                
        except Exception as e:
            self.logger.error(f"Error updating selected process: {e}")
            self.selected_process_pid = None
    
    def get_selected_process_pid(self) -> Optional[int]:
        """Get the currently selected process PID"""
        self.update_selected_process()
        return self.selected_process_pid

    def get_process_summary(self) -> str:
        """Get a summary of running processes"""
        try:
            total_processes = len(self.processes)
            return f"Processes: {total_processes}"
        except:
            return "Processes: N/A"