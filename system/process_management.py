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
        
        # CPU calculation tracking
        self.prev_proc_times = {}  # Store previous CPU times for processes  
        self.prev_total_time = 0   # Store previous total CPU time
        self.last_cpu_update = 0   # Timestamp of last CPU calculation
        self.cpu_cores = self._get_cpu_core_count()
        self.clock_ticks_per_second = os.sysconf(os.sysconf_names['SC_CLK_TCK']) if 'SC_CLK_TCK' in os.sysconf_names else 100
        self.psutil_procs = {}     # Cache psutil process objects for CPU tracking

    def initialize_cpu_tracking(self):
        """Initialize CPU tracking by doing a first measurement"""
        try:
            if PSUTIL_AVAILABLE:
                # Initialize psutil CPU tracking
                for proc in psutil.process_iter():
                    try:
                        proc.cpu_percent(interval=None)  # Initialize measurement
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
            
            # Initialize /proc-based tracking
            # Don't set prev_total_time yet - let the first calculation do that
            # Reset tracking variables to ensure clean start
            self.prev_total_time = 0
            self.last_cpu_update = 0
            self.prev_proc_times.clear()
            
            self.logger.info("CPU tracking initialized")
            
        except Exception as e:
            self.logger.error(f"Error initializing CPU tracking: {e}")

    def scan_processes(self) -> Dict[int, ProcessInfo]:
        """Scan all running processes and return process information"""
        try:
            self.logger.info(f"Scanning processes - psutil available: {PSUTIL_AVAILABLE}")
            if PSUTIL_AVAILABLE:
                processes = self.scan_processes_psutil()
            else:
                processes = self.scan_processes_proc()
            self.logger.info(f"Scanned {len(processes)} processes")
            return processes
        except Exception as e:
            self.logger.error(f"Error scanning processes: {e}")
            return {}

    def scan_processes_psutil(self) -> Dict[int, ProcessInfo]:
        """Scan processes using psutil library"""
        processes = {}
        current_procs = {}
        
        for proc in psutil.process_iter(['pid', 'ppid', 'name', 'username', 'status', 'cmdline']):
            try:
                pinfo = proc.info
                pid = pinfo['pid']
                current_procs[pid] = proc
                
                # Get CPU and memory usage
                try:
                    # Use cached process object if available for better CPU tracking
                    if pid in self.psutil_procs:
                        cached_proc = self.psutil_procs[pid]
                        try:
                            cpu_percent = cached_proc.cpu_percent(interval=None)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            # Process changed, use new one
                            cpu_percent = proc.cpu_percent(interval=None)
                    else:
                        # New process, initialize CPU tracking
                        cpu_percent = proc.cpu_percent(interval=None)
                    
                    memory_info = proc.memory_info()
                    memory_mb = memory_info.rss / ProcessManagerConfig.BYTES_TO_MB
                    memory_percent = proc.memory_percent()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    cpu_percent = 0.0
                    memory_mb = 0.0
                    memory_percent = 0.0
                
                # Create ProcessInfo object
                cmdline = ' '.join(pinfo.get('cmdline', []))
                if not cmdline:
                    cmdline = pinfo.get('name', '')
                
                # Format status for better readability
                raw_status = pinfo.get('status', '')
                formatted_status = self._format_process_status(raw_status)
                
                process_info = ProcessInfo(
                    pid=pid,
                    name=pinfo.get('name', 'Unknown'),
                    ppid=pinfo.get('ppid'),
                    cpu_percent=cpu_percent,
                    memory_percent=memory_percent,
                    memory_mb=memory_mb,
                    status=formatted_status,
                    user=pinfo.get('username', ''),
                    cmdline=cmdline
                )
                
                processes[pid] = process_info
                
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        # Update cached process objects for better CPU tracking
        self.psutil_procs = current_procs
        
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
                                raw_status = line.split()[1]
                                status = self._format_process_status(raw_status)
                    
                    # Calculate memory percentage and MB
                    memory_mb = memory_kb / 1024.0
                    memory_percent = (memory_kb / total_memory_kb) * 100.0 if total_memory_kb > 0 else 0.0
                    
                    
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
                    
                    # CPU percentage will be calculated later in batch
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
        
        # Calculate CPU percentages for all processes
        self.logger.info(f"Starting CPU calculation for {len(processes)} processes")
        self._calculate_all_cpu_percentages(processes)
        
        return processes

    def _format_process_status(self, status: str) -> str:
        """Convert process status code to readable format"""
        # Map Linux process states to readable names
        status_map = {
            'R': 'Running',
            'S': 'Sleeping', 
            'D': 'Disk Sleep',
            'T': 'Stopped',
            't': 'Tracing Stop',
            'Z': 'Zombie',
            'X': 'Dead',
            'x': 'Dead',
            'K': 'Wakekill',
            'W': 'Waking',
            'P': 'Parked',
            'I': 'Idle',
            'running': 'Running',
            'sleeping': 'Sleeping',
            'disk-sleep': 'Disk Sleep', 
            'stopped': 'Stopped',
            'tracing-stop': 'Tracing Stop',
            'zombie': 'Zombie',
            'dead': 'Dead',
            'wake-kill': 'Wakekill',
            'waking': 'Waking',
            'parked': 'Parked',
            'idle': 'Idle'
        }
        
        # Handle status with additional info (like "S (sleeping)")
        if '(' in status:
            status = status.split('(')[0].strip()
        
        return status_map.get(status, status.capitalize() if status else 'Unknown')

    def _get_cpu_core_count(self) -> int:
        """Get the number of CPU cores"""
        try:
            with open("/proc/cpuinfo", 'r') as f:
                return len([line for line in f if line.startswith("processor")])
        except:
            return 1  # Fallback to 1 core

    def _get_total_cpu_time(self) -> int:
        """Get total CPU time from /proc/stat"""
        try:
            with open("/proc/stat", 'r') as f:
                line = f.readline()
                # First line is: cpu user nice system idle iowait irq softirq steal guest guest_nice
                fields = line.split()
                if fields[0] == 'cpu':
                    # Sum all time values
                    return sum(int(field) for field in fields[1:])
        except:
            return 0

    def _calculate_all_cpu_percentages(self, processes: Dict[int, ProcessInfo]):
        """Calculate CPU percentages for all processes in batch"""
        try:
            current_time = time.time()
            current_total_time = self._get_total_cpu_time()
            
            # Skip calculation if we don't have previous data or enough time has passed
            time_delta = current_time - self.last_cpu_update
            self.logger.info(f"CPU calculation: time_delta={time_delta:.2f}s, prev_total_time={self.prev_total_time}")
            
            if self.prev_total_time == 0:
                self.logger.info("First CPU measurement - initializing baseline data")
                # First measurement - just store baseline data
                self.last_cpu_update = current_time
                self.prev_total_time = current_total_time
                for pid, process in processes.items():
                    self._store_process_cpu_time(pid)
                return
            
            if time_delta < 0.5:  # Minimum 0.5 second interval
                self.logger.info(f"Skipping CPU calculation - time interval too short ({time_delta:.2f}s)")
                return
            
            # Calculate total CPU time delta
            total_time_delta = current_total_time - self.prev_total_time
            
            self.logger.info(f"Total CPU time delta: {total_time_delta} over {time_delta:.2f}s")
            
            if total_time_delta <= 0:
                self.logger.warning(f"Invalid total CPU time delta: {total_time_delta}")
                return  # No CPU time passed, skip calculation
            
            # Calculate CPU percentage for each process
            calculated_count = 0
            for pid, process in processes.items():
                try:
                    current_proc_time = self._get_process_cpu_time(pid)
                    if current_proc_time is None:
                        continue
                    
                    if pid in self.prev_proc_times:
                        proc_time_delta = current_proc_time - self.prev_proc_times[pid]
                        
                        # Calculate CPU percentage using the standard method
                        # CPU% = (process_cpu_time_delta / total_cpu_time_delta) * 100 * num_cpus
                        if total_time_delta > 0:
                            cpu_percent = (proc_time_delta / total_time_delta) * 100.0 * self.cpu_cores
                        else:
                            cpu_percent = 0.0
                        
                        # Cap at reasonable values (100% per core)
                        cpu_percent = min(max(cpu_percent, 0.0), 100.0 * self.cpu_cores)
                        process.cpu_percent = round(cpu_percent, 1)
                        calculated_count += 1
                        
                    
                    # Store current values for next calculation
                    self.prev_proc_times[pid] = current_proc_time
                    
                except Exception as e:
                    # Process may have disappeared
                    continue
            
            if calculated_count > 0:
                self.logger.info(f"Successfully calculated CPU percentages for {calculated_count} processes")
            else:
                self.logger.warning("No CPU percentages were calculated - this may indicate an issue")
            
            # Update tracking variables
            self.prev_total_time = current_total_time
            self.last_cpu_update = current_time
            
            # Clean up old process entries
            current_pids = set(processes.keys())
            old_pids = set(self.prev_proc_times.keys()) - current_pids
            for old_pid in old_pids:
                del self.prev_proc_times[old_pid]
                
        except Exception as e:
            self.logger.error(f"Error calculating CPU percentages: {e}")

    def _get_process_cpu_time(self, pid: int) -> Optional[int]:
        """Get total CPU time for a process from /proc/[pid]/stat"""
        try:
            stat_path = f"/proc/{pid}/stat"
            if not os.path.exists(stat_path):
                return None
            
            with open(stat_path, 'r') as f:
                fields = f.read().split()
                
            if len(fields) < 17:  # Need at least fields 13-16
                return None
            
            # Extract CPU time fields (in clock ticks)
            utime = int(fields[13])   # User mode time
            stime = int(fields[14])   # Kernel mode time
            cutime = int(fields[15])  # Children user time  
            cstime = int(fields[16])  # Children kernel time
            
            # Total time for this process
            return utime + stime + cutime + cstime
            
        except (IOError, OSError, ValueError, IndexError):
            return None

    def _store_process_cpu_time(self, pid: int):
        """Store current CPU time for a process for future calculation"""
        cpu_time = self._get_process_cpu_time(pid)
        if cpu_time is not None:
            self.prev_proc_times[pid] = cpu_time

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
            
            # Calculate cumulative CPU and memory usage for the tree
            self._calculate_cumulative_usage(root_processes)
            
            return root_processes
            
        except Exception as e:
            self.logger.error(f"Error building process tree: {e}")
            return []

    def _calculate_cumulative_usage(self, processes: List):
        """Calculate cumulative CPU and memory usage for process trees"""
        try:
            for process in processes:
                self._calculate_process_cumulative_usage(process)
        except Exception as e:
            self.logger.error(f"Error calculating cumulative usage: {e}")

    def _calculate_process_cumulative_usage(self, process):
        """Recursively calculate cumulative CPU and memory usage for a process and its children"""
        try:
            # Store the process's own usage (before adding children)
            own_cpu = process.cpu_percent
            own_memory = process.memory_mb
            
            # Initialize totals with own usage
            total_cpu = own_cpu
            total_memory = own_memory
            
            # Add usage from all direct children (recursively)
            for child in process.children:
                # First calculate cumulative usage for the child
                self._calculate_process_cumulative_usage(child)
                
                # Then add the child's cumulative usage to this process
                total_cpu += child.cpu_percent
                total_memory += child.memory_mb
            
            # Update the process with cumulative values
            process.cpu_percent = round(total_cpu, 1)
            process.memory_mb = round(total_memory, 1)
            
            
        except Exception as e:
            self.logger.error(f"Error calculating cumulative usage for process {process.pid}: {e}")

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
            # Create tree store (PID, Name, CPU%, Memory MB, Status, User, Command Line)
            self.process_store = self.widget_factory.create_tree_store([int, str, str, str, str, str, str])
            
            # Create tree view
            self.process_tree_view = self.widget_factory.create_tree_view(model=self.process_store)
            self.process_tree_view.set_headers_visible(True)
            self.process_tree_view.set_enable_tree_lines(True)
            
            # Create columns
            columns = [
                ("PID", 0, 60),
                ("Process Name", 1, 200),
                ("CPU %", 2, 80),
                ("Memory (MB)", 3, 100),
                ("Status", 4, 80),
                ("User", 5, 100),
                ("Command Line", 6, 300)
            ]
            
            for title, column_id, width in columns:
                renderer = self.widget_factory.create_cell_renderer_text()
                column = self.widget_factory.create_tree_view_column(title, renderer, text_column=column_id)
                column.set_resizable(True)
                column.set_min_width(width)
                if column_id in [2, 3]:  # CPU and Memory columns
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
                3,  # Memory MB
                4,  # Status
                5,  # User
                6   # Command Line
            ], [
                process_info.pid,
                process_info.name,
                f"{process_info.cpu_percent:.1f}",
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
                memory_mb_str = f"{proc.memory_mb:.1f}"
                
                # Add process to store
                iter = self.process_store.append(parent_iter, [
                    proc.pid,
                    proc.name,
                    cpu_str,
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
            signal_names = {
                signal.SIGTERM: "terminate",
                signal.SIGKILL: "force kill",
                signal.SIGSTOP: "pause",
                signal.SIGCONT: "resume"
            }
            signal_name = signal_names.get(sig, f"send signal {sig} to")
            
            self.logger.info(f"Showing confirmation dialog for {proc_info.name} (user: {proc_info.user})")
            
            # Show confirmation dialog
            self.show_kill_confirmation_dialog(pid, proc_info.name, signal_name, sig)
            
        except Exception as e:
            self.logger.error(f"Error ending process {pid}: {e}")

    def show_kill_confirmation_dialog(self, pid, process_name, signal_name, sig):
        """Show confirmation dialog before killing process"""
        try:
            # For now, execute directly since dialog interaction has issues in GTK4
            # TODO: Fix dialog interaction in GTK4 when time permits
            self.logger.info(f"Executing {signal_name} on {process_name} (PID: {pid}) - dialog interaction disabled in GTK4")
            self.kill_process_confirmed(pid, sig)
            return
            # Get main window as parent if available
            main_window = None
            if hasattr(self, 'main_window'):
                main_window = self.main_window
            elif hasattr(self, 'widget_factory') and hasattr(self.widget_factory, 'main_window'):
                main_window = self.widget_factory.main_window
            
            dialog = self.widget_factory.create_message_dialog(
                transient_for=main_window,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.YES_NO,
                text=f"End Process?",
                secondary_text=(
                    f"Are you sure you want to {signal_name} process '{process_name}' (PID: {pid})?\n\n"
                    f"This action cannot be undone and may cause data loss."
                )
            )
            
            if not dialog:
                self.logger.error("Failed to create confirmation dialog")
                # Fallback: Execute without confirmation
                self.logger.info("Executing process action without confirmation as fallback")
                self.kill_process_confirmed(pid, sig)
                return
            
            self.logger.info(f"Dialog created successfully for PID {pid}")
            
            def on_dialog_response(dialog, response):
                self.logger.info(f"Dialog response received: {response}")
                if response == Gtk.ResponseType.YES:
                    self.logger.info(f"User confirmed kill for PID {pid}")
                    self.kill_process_confirmed(pid, sig)
                else:
                    self.logger.info(f"User cancelled kill for PID {pid}")
                dialog.destroy()
            
            # Add a timeout as fallback in case dialog doesn't work
            def dialog_timeout():
                self.logger.warning(f"Dialog timeout for PID {pid} - executing without confirmation")
                dialog.destroy()
                self.kill_process_confirmed(pid, sig)
                return False  # Don't repeat timeout
            
            dialog.connect("response", on_dialog_response)
            self.logger.info(f"Presenting dialog for PID {pid}")
            dialog.present()
            self.logger.info(f"Dialog.present() called for PID {pid}")
            
            # Set 10 second timeout as fallback
            GLib.timeout_add(10000, dialog_timeout)
            
        except Exception as e:
            self.logger.error(f"Error showing kill confirmation dialog: {e}")

    def kill_process_confirmed(self, pid, sig):
        """Actually kill the process after confirmation"""
        try:
            self.logger.info(f"kill_process_confirmed called: pid={pid}, signal={sig}")
            
            # Check if process still exists
            if pid not in self.processes:
                self.logger.warning(f"Process {pid} no longer exists in our process list")
                # Still try to kill it in case it exists but wasn't scanned yet
            
            self.logger.info(f"About to attempt process kill with signal {sig}")
            self.logger.info(f"PSUTIL_AVAILABLE: {PSUTIL_AVAILABLE}")
            
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
                    signal_name = {
                        signal.SIGTERM: "SIGTERM(15)",
                        signal.SIGKILL: "SIGKILL(9)", 
                        signal.SIGSTOP: "SIGSTOP(19)",
                        signal.SIGCONT: "SIGCONT(18)"
                    }.get(sig, f"SIG{sig}")
                    
                    self.logger.info(f"Using os.kill to send {signal_name} to process {pid}")
                    os.kill(pid, sig)
                    self.logger.info(f"os.kill SUCCESS: sent {signal_name} to process {pid}")
                    
                    # Show success notification with process info
                    action_name = {
                        signal.SIGTERM: "terminated",
                        signal.SIGKILL: "killed", 
                        signal.SIGSTOP: "stopped",
                        signal.SIGCONT: "continued"
                    }.get(sig, f"sent signal {sig} to")
                    
                    proc_info = self.processes.get(pid)
                    proc_name = proc_info.name if proc_info else f"PID {pid}"
                    self._show_success_notification(f"Process '{proc_name}' successfully {action_name}")
                    
                except OSError as e:
                    self.logger.info(f"os.kill failed for process {pid}: errno={e.errno}, strerror='{e.strerror}', error={e}")
                    if e.errno == 1:  # Operation not permitted
                        self.logger.info(f"Permission denied, trying pkexec for process {pid}")
                        self.kill_process_with_pkexec(pid, sig)
                        return  # Don't refresh process list here, pkexec will handle it
                    elif e.errno == 3:  # No such process
                        self.logger.warning(f"Process {pid} no longer exists (ESRCH)")
                    else:
                        self.logger.error(f"Unexpected os.kill error for process {pid}: errno={e.errno}, {e}")
                except Exception as e:
                    self.logger.error(f"Unexpected exception in os.kill for process {pid}: {e}")
            
            # Refresh process list after a short delay
            self.logger.info(f"Scheduling process list refresh after {self.get_update_interval_ms()}ms")
            GLib.timeout_add(self.get_update_interval_ms(), self.update_processes)
            
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
            
            dialog = self.widget_factory.create_message_dialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Administrative Privileges Required",
                secondary_text=(
                    f"To {signal_name} process '{proc_info.name}' (PID: {pid}) owned by '{proc_info.user}', "
                    f"administrative privileges are required.\n\n"
                    f"You will be prompted for authentication. Do you want to continue?"
                )
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
                action_name = {
                    signal.SIGTERM: "terminated",
                    signal.SIGKILL: "killed", 
                    signal.SIGSTOP: "stopped",
                    signal.SIGCONT: "continued"
                }.get(sig, f"sent signal {sig} to")
                self._show_success_notification(f"Process '{proc_info.name}' successfully {action_name} (required admin privileges)")
                # Refresh process list after a short delay
                GLib.timeout_add(self.get_update_interval_ms(), self.update_processes)
            
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
    
    def _show_success_notification(self, message):
        """Show success notification using multiple fallback methods"""
        try:
            self.logger.info(f"SUCCESS NOTIFICATION: {message}")
            
            # Method 1: Try creating a simple dialog with better GTK4 compatibility
            try:
                # Get main window reference for proper dialog parenting
                main_window = None
                if hasattr(self.widget_factory, 'main_window'):
                    main_window = self.widget_factory.main_window
                
                dialog = self.widget_factory.create_message_dialog(
                    transient_for=main_window,
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    text="Process Action Completed",
                    secondary_text=message
                )
                
                if dialog:
                    # Make dialog more visible
                    dialog.set_modal(True)
                    if main_window:
                        dialog.set_transient_for(main_window)
                    
                    def on_dialog_response(dialog, response):
                        self.logger.info(f"Success dialog closed with response: {response}")
                        dialog.destroy()
                    
                    dialog.connect("response", on_dialog_response)
                    dialog.present()
                    self.logger.info("Success dialog presented")
                    return
                    
            except Exception as e:
                self.logger.error(f"Failed to show success dialog: {e}")
            
            # Method 2: Fallback to console notification
            print(f"\n=== LinuxVitals Notification ===")
            print(f"✓ {message}")
            print(f"================================\n")
            
        except Exception as e:
            self.logger.error(f"Error showing success notification: {e}")
    
    def _show_success_dialog(self, message):
        """Legacy method - redirects to new notification system"""
        self._show_success_notification(message)
    
    def _show_error_dialog(self, title, message):
        """Show error dialog"""
        try:
            dialog = self.widget_factory.create_message_dialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=title,
                secondary_text=message
            )
            
            def on_dialog_response(dialog, response):
                dialog.destroy()
            
            dialog.connect("response", on_dialog_response)
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error showing error dialog: {e}")

    def show_process_properties(self, pid):
        """Show detailed properties of a process"""
        try:
            self.logger.info(f"show_process_properties called for PID {pid}")
            if pid not in self.processes:
                self.logger.error(f"Process {pid} not found for properties")
                return
            
            proc_info = self.processes[pid]
            
            # Create properties dialog
            self.logger.info(f"Creating properties dialog for {proc_info.name}")
            dialog = self.widget_factory.create_dialog(title=f"Process Properties - {proc_info.name}")
            if not dialog:
                self.logger.error("Failed to create properties dialog")
                return
            dialog.set_default_size(700, 600)
            
            content_area = dialog.get_content_area()
            
            # Create scrolled window for process details
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_vexpand(True)
            scrolled.set_hexpand(True)
            scrolled.set_margin_top(10)
            scrolled.set_margin_bottom(10)
            scrolled.set_margin_start(10)
            scrolled.set_margin_end(10)
            
            text_view = Gtk.TextView()
            text_view.set_editable(False)
            text_view.set_wrap_mode(Gtk.WrapMode.WORD)
            text_view.set_margin_top(10)
            text_view.set_margin_bottom(10)
            text_view.set_margin_start(10)
            text_view.set_margin_end(10)
            
            # Get detailed process information
            try:
                details = self._get_detailed_process_info(pid, proc_info)
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

    def _get_detailed_process_info(self, pid, proc_info):
        """Get comprehensive process information from /proc filesystem"""
        try:
            # Start with basic information
            details = """Process Information
==================================================

Basic Details:
  PID: {}
  Name: {}
  Status: {}
  User: {}
  Parent PID: {}

Performance:
  CPU Usage: {:.1f}%
  Memory Usage: {:.1f} MB
  Command Line: {}

""".format(
                proc_info.pid,
                proc_info.name,
                proc_info.status,
                proc_info.user,
                proc_info.ppid or 'None',
                proc_info.cpu_percent,
                proc_info.memory_mb,
                proc_info.cmdline
            )

            # Read additional information from /proc filesystem
            proc_dir = '/proc/{}'.format(pid)
            
            # Get status information
            try:
                with open('{}/status'.format(proc_dir), 'r') as f:
                    status_info = {}
                    for line in f:
                        if ':' in line:
                            key, value = line.strip().split(':', 1)
                            status_info[key.strip()] = value.strip()
                
                details += "Process Status Details:\n"
                
                # Priority and scheduling
                if 'State' in status_info:
                    details += "  State: {}\n".format(status_info['State'])
                if 'Tgid' in status_info:
                    details += "  Thread Group ID: {}\n".format(status_info['Tgid'])
                if 'Ngid' in status_info:
                    details += "  NUMA Group ID: {}\n".format(status_info['Ngid'])
                
                # Memory details
                details += "\nMemory Information:\n"
                if 'VmPeak' in status_info:
                    details += "  Virtual Memory Peak: {}\n".format(status_info['VmPeak'])
                if 'VmSize' in status_info:
                    details += "  Virtual Memory Size: {}\n".format(status_info['VmSize'])
                if 'VmRSS' in status_info:
                    details += "  Physical Memory (RSS): {}\n".format(status_info['VmRSS'])
                if 'VmSwap' in status_info:
                    details += "  Swap Usage: {}\n".format(status_info['VmSwap'])
                
                # Thread information
                if 'Threads' in status_info:
                    details += "\nThread Count: {}\n".format(status_info['Threads'])
                
                # User/Group IDs
                details += "\nProcess Ownership:\n"
                if 'Uid' in status_info:
                    uids = status_info['Uid'].split()
                    details += "  Real UID: {} | Effective UID: {}\n".format(uids[0], uids[1])
                if 'Gid' in status_info:
                    gids = status_info['Gid'].split()
                    details += "  Real GID: {} | Effective GID: {}\n".format(gids[0], gids[1])
                
            except Exception as e:
                details += "  Status info unavailable: {}\n".format(e)
            
            # Get command line arguments
            try:
                with open('{}/cmdline'.format(proc_dir), 'r') as f:
                    cmdline_raw = f.read()
                    if cmdline_raw:
                        # Split on null bytes and filter empty strings
                        args = [arg for arg in cmdline_raw.split('\0') if arg]
                        details += "\nCommand Line Arguments:\n"
                        for i, arg in enumerate(args):
                            details += "  [{}]: {}\n".format(i, arg)
                    else:
                        details += "\nCommand Line: [kernel thread]\n"
            except Exception as e:
                details += "\nCommand line unavailable: {}\n".format(e)
            
            # Get environment variables (limited for security)
            try:
                with open('{}/environ'.format(proc_dir), 'r') as f:
                    environ_raw = f.read()
                    if environ_raw:
                        env_vars = [env for env in environ_raw.split('\0') if env and not any(secret in env.upper() for secret in ['PASSWORD', 'TOKEN', 'KEY', 'SECRET'])]
                        details += "\nEnvironment Variables (filtered):\n"
                        for env in env_vars[:10]:  # Limit to first 10 to avoid clutter
                            if '=' in env:
                                key, value = env.split('=', 1)
                                # Truncate very long values
                                if len(value) > 100:
                                    value = value[:97] + "..."
                                details += "  {}={}\n".format(key, value)
                        if len(env_vars) > 10:
                            details += "  ... and {} more variables\n".format(len(env_vars) - 10)
            except Exception as e:
                details += "\nEnvironment variables unavailable: {}\n".format(e)
            
            # Get file descriptor information
            try:
                fd_dir = '{}/fd'.format(proc_dir)
                if os.path.exists(fd_dir):
                    fds = os.listdir(fd_dir)
                    details += "\nFile Descriptors: {} open\n".format(len(fds))
                    
                    # Show first few file descriptors
                    for fd in sorted(fds, key=int)[:5]:
                        try:
                            target = os.readlink('{}/{}'.format(fd_dir, fd))
                            details += "  {}: {}\n".format(fd, target)
                        except:
                            details += "  {}: [access denied]\n".format(fd)
                    if len(fds) > 5:
                        details += "  ... and {} more file descriptors\n".format(len(fds) - 5)
            except Exception as e:
                details += "\nFile descriptor info unavailable: {}\n".format(e)
            
            # Get working directory
            try:
                cwd = os.readlink('{}/cwd'.format(proc_dir))
                details += "\nWorking Directory: {}\n".format(cwd)
            except Exception as e:
                details += "\nWorking directory unavailable: {}\n".format(e)
            
            # Get executable path
            try:
                exe = os.readlink('{}/exe'.format(proc_dir))
                details += "Executable: {}\n".format(exe)
            except Exception as e:
                details += "Executable path unavailable: {}\n".format(e)
            
            # Get process timing information
            try:
                with open('{}/stat'.format(proc_dir), 'r') as f:
                    stat_line = f.read().strip()
                    fields = stat_line.split()
                    if len(fields) >= 22:
                        # Calculate process start time
                        starttime_ticks = int(fields[21])
                        boot_time = self._get_boot_time()
                        if boot_time:
                            clock_ticks = os.sysconf(os.sysconf_names.get('SC_CLK_TCK', 100))
                            start_time = boot_time + (starttime_ticks / clock_ticks)
                            import datetime
                            start_dt = datetime.datetime.fromtimestamp(start_time)
                            details += "Start Time: {}\n".format(start_dt.strftime('%Y-%m-%d %H:%M:%S'))
                        
                        # Priority and nice values
                        priority = int(fields[17])
                        nice = int(fields[18])
                        details += "Priority: {} | Nice: {}\n".format(priority, nice)
                        
            except Exception as e:
                details += "Timing information unavailable: {}\n".format(e)
            
            return details
            
        except Exception as e:
            return "Error gathering process details: {}".format(e)
    
    def _get_boot_time(self):
        """Get system boot time from /proc/stat"""
        try:
            with open('/proc/stat', 'r') as f:
                for line in f:
                    if line.startswith('btime '):
                        return float(line.split()[1])
        except:
            pass
        return None

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
            self.logger.info(f"Restarting process {proc_info.name} (PID: {pid}) - sending SIGTERM")
            
            # Just terminate the process - if it's a service, the system will restart it
            self.kill_process_confirmed(pid, signal.SIGTERM)
            
            return  # Skip the old dialog code
            
            # Show confirmation dialog first
            dialog = self.widget_factory.create_message_dialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Restart Process?",
                secondary_text=(
                    f"Are you sure you want to restart process '{proc_info.name}' (PID: {pid})?\n\n"
                    f"This will terminate the process and rely on the system to restart it. "
                    f"Note that not all processes will automatically restart."
                )
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