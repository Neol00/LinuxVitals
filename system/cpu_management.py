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
import gi
from typing import Optional, Dict, List, Tuple, Any, Callable, Union
from gi.repository import Gtk, GLib

# Configuration constants
class CPUManagerConfig:
    DEFAULT_UPDATE_INTERVAL = 1.0
    MIN_UPDATE_INTERVAL = 0.1
    MAX_UPDATE_INTERVAL = 20.0
    DEFAULT_MIN_FREQ_MHZ = 400
    DEFAULT_MAX_FREQ_MHZ = 5000
    DEFAULT_MIN_FREQ_FALLBACK = 1000
    DEFAULT_MAX_FREQ_FALLBACK = 2000
    MAX_SPEED_LIMIT = 6000
    KHZ_TO_MHZ_DIVISOR = 1000
    MICROSECONDS_TO_SECONDS = 1000
    MICROWATTS_TO_WATTS = 1_000_000
    WATTS_TO_MILLIWATTS = 1000
    CPU_LOAD_HISTORY_SIZE = 60
    PERCENTAGE_MULTIPLIER = 100
    TEMP_MILLIDEGREES_TO_CELSIUS = 1000
    BINARY_SHIFT_16 = 16
    TWO_COMPLEMENT_MASK = 0xFFFF

class CPUManager:
    def __init__(self, config_manager, logger, global_state, gui_components, widget_factory, cpu_file_search, privileged_actions, settings_applier):
        # References to instances
        self.config_manager = config_manager
        self.logger = logger
        self.global_state = global_state
        self.gui_components = gui_components
        self.widget_factory = widget_factory
        self.cpu_file_search = cpu_file_search
        self.privileged_actions = privileged_actions
        self.settings_applier = settings_applier
        self.monitor_tab_manager = None

        self.monitor_task_id = None
        self.control_task_id = None

        self.cpu_load_history = {i: [0] * CPUManagerConfig.CPU_LOAD_HISTORY_SIZE for i in range(self.cpu_file_search.thread_count)}

        # Load update interval from config or use default
        self.update_interval = float(config_manager.get_setting("Settings", "update_interval", str(CPUManagerConfig.DEFAULT_UPDATE_INTERVAL)))

        # Read initial CPU statistics
        self.prev_stat = self.read_stat_file()

        # Keep track of the previous loads to not update unnecessarily
        self.prev_loads = {}
    
    def set_monitor_tab_manager(self, monitor_tab_manager):
        """Set the monitor tab manager for conditional label creation"""
        self.monitor_tab_manager = monitor_tab_manager

        # Schedule monitor tasks on startup
        self.schedule_monitor_tasks()

        # Initialize dictionaries for GUI components
        self.clock_labels = {}
        self.progress_bars = {}
        self.min_scales = {}
        self.max_scales = {}
        self.cpu_max_min_checkbuttons = {}

        # GUI components
        self.average_clock_entry = None
        self.average_progress_bar = None
        self.package_temp_entry = None
        self.current_governor_label = None
        self.governor_dropdown = None
        self.boost_checkbutton = None
        self.tdp_scale = None
        self.pbo_curve_scale = None

        # Set of valid CPU governors
        self.valid_governors = frozenset([
            'conservative', 
            'ondemand', 
            'performance', 
            'powersave', 
            'schedutil',
            'userspace'
        ])

        # Keep track if CPU is currently throttling
        self.prev_package_throttle_time = [None] * self.cpu_file_search.thread_count
        self.is_throttling = False  # Flag to indicate if throttling is occurring

    def schedule_monitor_tasks(self):
        # Schedule the periodic tasks for the monitor tab with the specified update interval
        if self.monitor_task_id:
            GLib.source_remove(self.monitor_task_id)
        self.monitor_task_id = GLib.timeout_add(int(self.update_interval * 1000), self.run_monitor_tasks)

    def stop_monitor_tasks(self):
        # Stop the periodic tasks for the monitor tab if they are running
        if self.monitor_task_id:
            GLib.source_remove(self.monitor_task_id)
            self.monitor_task_id = None

    def schedule_control_tasks(self):
        # Schedule the periodic tasks for the control tab with the specified update interval
        if self.control_task_id:
            GLib.source_remove(self.control_task_id)
        self.control_task_id = GLib.timeout_add(int(self.update_interval * 1000), self.run_control_tasks)

    def stop_control_tasks(self):
        # Stop the periodic tasks for the control tab if they are running
        if self.control_task_id:
            GLib.source_remove(self.control_task_id)
            self.control_task_id = None

    def run_monitor_tasks(self):
        # Execute the monitor tasks periodically
        try:
            self.update_cpu_load()
            self.update_clock_speeds()
            self.read_package_temperature()
            self.get_current_governor()
            self.update_throttle()
            # Memory monitoring will be handled by main app
        except Exception as e:
            self.logger.error("Failed to run monitor tasks: %s", e)

        # Only reschedule if the task ID is still valid (i.e., periodic tasks haven't been stopped)
        if self.monitor_task_id:
            self.schedule_monitor_tasks()
        return False  # Prevent automatic re-scheduling by GLib

    def run_control_tasks(self):
        # Execute the control tasks periodically
        try:
            self.update_boost_checkbutton()
        except Exception as e:
            self.logger.error("Failed to run control tasks: %s", e)
        if self.control_task_id:
            self.schedule_control_tasks()
        return False  # Prevent automatic re-scheduling by GLib

    def set_update_interval(self, interval: float) -> None:
        # Set the update interval for periodic tasks and save it in the config
        self.update_interval = round(max(CPUManagerConfig.MIN_UPDATE_INTERVAL, min(CPUManagerConfig.MAX_UPDATE_INTERVAL, interval)), 1)
        self.logger.info(f"Update interval set to {self.update_interval} seconds")
        self.config_manager.set_setting("Settings", "update_interval", f"{self.update_interval:.1f}")
        self.schedule_monitor_tasks()
        self.schedule_control_tasks()

    def setup_gui_components(self):
        # Set up references to GUI components from the shared dictionary
        try:
            self.clock_labels = self.gui_components['clock_labels']
            self.usage_labels = self.gui_components['usage_labels']
            self.cpu_graphs = self.gui_components['cpu_graphs']
            self.avg_usage_graph = self.gui_components['avg_usage_graph']
            self.avg_usage_label = self.gui_components['avg_usage_label']
            self.avg_clock_label = self.gui_components['avg_clock_label']
            self.package_temp_label = self.gui_components['package_temp_label']
            self.current_governor_label = self.gui_components['current_governor_label']
            self.thermal_throttle_label = self.gui_components['thermal_throttle_label']
            self.cpu_max_min_checkbuttons = self.gui_components['cpu_max_min_checkbuttons']
            self.max_scales = self.gui_components['cpu_max_scales']
            self.min_scales = self.gui_components['cpu_min_scales']
            self.apply_max_min_button = self.gui_components['apply_max_min_button']
            self.governor_dropdown = self.gui_components['governor_dropdown']
            self.boost_checkbutton = self.gui_components['boost_checkbutton']
            self.tdp_scale = self.gui_components['tdp_scale']
            self.apply_tdp_button = self.gui_components['apply_tdp_button']
            self.pbo_curve_scale = self.gui_components['pbo_curve_scale']
            self.apply_pbo_button = self.gui_components['apply_pbo_button']
            self.epb_dropdown = self.gui_components['epb_dropdown']
        except KeyError as e:
            self.logger.error(f"Error setting up cpu_manager gui_components: Component {e} not found")

    def get_cpu_info(self) -> Dict[str, Any]:
        # Retrieve CPU information from system files
        try:
            cpuinfo_file = self.cpu_file_search.proc_files['cpuinfo']
            meminfo_file = self.cpu_file_search.proc_files['meminfo']

            if not cpuinfo_file:
                self.logger.error("cpuinfo file not found.")
                # Return default values for ARM or unknown architectures
                return {
                    "Model Name": "Unknown CPU Model",
                    "Cache Sizes": {},
                    "Total RAM (MB)": 0,
                    "Min (MHz)": [CPUManagerConfig.DEFAULT_MIN_FREQ_FALLBACK] * self.cpu_file_search.thread_count,
                    "Max (MHz)": [CPUManagerConfig.DEFAULT_MAX_FREQ_FALLBACK] * self.cpu_file_search.thread_count,
                    "Physical Cores": self.cpu_file_search.thread_count // 2 or 1,
                    "Virtual Cores (Threads)": self.cpu_file_search.thread_count
                }
                
            if not meminfo_file:
                self.logger.error("meminfo file not found.")
                return {
                    "Model Name": "Unknown CPU Model",
                    "Cache Sizes": {},
                    "Total RAM (MB)": 0,
                    "Min (MHz)": [CPUManagerConfig.DEFAULT_MIN_FREQ_FALLBACK] * self.cpu_file_search.thread_count,
                    "Max (MHz)": [CPUManagerConfig.DEFAULT_MAX_FREQ_FALLBACK] * self.cpu_file_search.thread_count,
                    "Physical Cores": self.cpu_file_search.thread_count // 2 or 1,
                    "Virtual Cores (Threads)": self.cpu_file_search.thread_count
                }

            # Parse the CPU information
            model_name, cache_sizes, physical_cores, virtual_cores = self.parse_cpu_info(cpuinfo_file)
            
            # Get the allowed CPU frequencies
            min_allowed_freqs, max_allowed_freqs = self.get_allowed_cpu_frequency()
            
            # If frequencies couldn't be determined, use default values
            if not min_allowed_freqs or not max_allowed_freqs:
                min_allowed_freqs = [CPUManagerConfig.DEFAULT_MIN_FREQ_FALLBACK] * self.cpu_file_search.thread_count
                max_allowed_freqs = [CPUManagerConfig.DEFAULT_MAX_FREQ_FALLBACK] * self.cpu_file_search.thread_count
                
            # Read the total RAM from the meminfo file
            total_ram = self.read_total_ram(meminfo_file)

            # Filter out any None cache sizes
            if cache_sizes:
                cache_sizes = {k: v for k, v in cache_sizes.items() if v is not None}
            else:
                cache_sizes = {}

            # If model_name is None (can happen on ARM), use a default
            if not model_name:
                model_name = "ARM Processor"

            # If physical_cores is None or 0, estimate based on thread count
            if not physical_cores:
                physical_cores = self.cpu_file_search.thread_count // 2 or 1

            # Create a dictionary with the CPU information
            cpu_info = {
                "Model Name": model_name,
                "Cache Sizes": cache_sizes,
                "Total RAM (MB)": total_ram or 0,
                "Min (MHz)": min_allowed_freqs,
                "Max (MHz)": max_allowed_freqs,
                "Physical Cores": physical_cores,
                "Virtual Cores (Threads)": virtual_cores
            }

            return cpu_info

        except Exception as e:
            self.logger.error(f"Error retrieving CPU info: {e}")
            # Return a default set of values as fallback
            return {
                "Model Name": "Unknown CPU Model",
                "Cache Sizes": {},
                "Total RAM (MB)": 0,
                "Min (MHz)": [1000] * self.cpu_file_search.thread_count,
                "Max (MHz)": [2000] * self.cpu_file_search.thread_count,
                "Physical Cores": self.cpu_file_search.thread_count // 2 or 1,
                "Virtual Cores (Threads)": self.cpu_file_search.thread_count
            }

    def parse_cpu_info(self, cpuinfo_file: str) -> Tuple[str, Dict[str, Any], int, int]:
        """Parse the CPU information file to extract model name and core counts with comprehensive detection"""
        try:
            model_name = None
            cache_sizes = self._get_cache_sizes()
            virtual_cores = self.cpu_file_search.thread_count

            # Parse processor information from cpuinfo file
            processor_data = self._parse_cpuinfo_file(cpuinfo_file)
            
            # Determine physical cores using multiple methods
            # Extract only the parameters needed for _determine_physical_cores
            physical_cores = self._determine_physical_cores(
                cpu_cores_field=processor_data.get('cpu_cores_field'),
                siblings_field=processor_data.get('siblings_field'),
                physical_ids=processor_data.get('physical_ids'),
                core_ids_per_physical=processor_data.get('core_ids_per_physical'),
                processor_count=processor_data.get('processor_count'),
                cpu_parts=processor_data.get('cpu_parts'),
                clusters=processor_data.get('clusters'),
                virtual_cores=virtual_cores
            )
            
            # Ensure we have valid values
            if not processor_data.get('model_name'):
                model_name = self._detect_cpu_model_fallback()
            else:
                model_name = processor_data['model_name']
            
            if physical_cores <= 0:
                physical_cores = max(1, virtual_cores // 2)  # Fallback assumption
            
            return model_name, cache_sizes, physical_cores, virtual_cores

        except Exception as e:
            self.logger.error(f"Error parsing CPU info: {e}")
            # Return safe defaults
            return ("Unknown CPU", {}, max(1, self.cpu_file_search.thread_count // 2), self.cpu_file_search.thread_count)

    def _get_cache_sizes(self):
        """Get cache sizes from cpu_file_search"""
        return {
            "L1 Data": self.cpu_file_search.cache_files.get("1_Data", None),
            "L1 Instruction": self.cpu_file_search.cache_files.get("1_Instruction", None),
            "L2 Unified": self.cpu_file_search.cache_files.get("2_Unified", None),
            "L3 Unified": self.cpu_file_search.cache_files.get("3_Unified", None)
        }

    def _parse_cpuinfo_file(self, cpuinfo_file):
        """Parse the cpuinfo file and extract processor information"""
        model_name = None
        physical_ids = set()
        core_ids_per_physical = {}
        processor_count = 0
        cpu_cores_field = None
        siblings_field = None
        cpu_parts = set()
        clusters = set()
        
        with open(cpuinfo_file, 'r') as file:
            current_processor = {}
            
            for line in file:
                line = line.strip()
                if not line:
                    # End of processor block, process it
                    if current_processor:
                        processor_count += 1
                        self._process_processor_block(current_processor, physical_ids, 
                                                    core_ids_per_physical, cpu_parts, clusters)
                    current_processor = {}
                    continue
                
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    current_processor[key] = value
                    
                    # Extract various fields
                    if not model_name:
                        model_name = self._extract_model_name(key, value)
                    
                    if cpu_cores_field is None:
                        cpu_cores_field = self._extract_cpu_cores(key, value)
                    
                    if siblings_field is None:
                        siblings_field = self._extract_siblings(key, value)
        
        # Process the last processor if file doesn't end with blank line
        if current_processor:
            processor_count += 1
            self._process_processor_block(current_processor, physical_ids, 
                                        core_ids_per_physical, cpu_parts, clusters)
        
        return {
            'model_name': model_name,
            'cpu_cores_field': cpu_cores_field,
            'siblings_field': siblings_field,
            'physical_ids': physical_ids,
            'core_ids_per_physical': core_ids_per_physical,
            'processor_count': processor_count,
            'cpu_parts': cpu_parts,
            'clusters': clusters
        }

    def _process_processor_block(self, processor, physical_ids, core_ids_per_physical, cpu_parts, clusters):
        """Process a single processor block from cpuinfo"""
        # Track physical IDs and core IDs (x86/AMD)
        if 'physical id' in processor:
            phys_id = processor['physical id']
            physical_ids.add(phys_id)
            
            if 'core id' in processor:
                core_id = processor['core id']
                if phys_id not in core_ids_per_physical:
                    core_ids_per_physical[phys_id] = set()
                core_ids_per_physical[phys_id].add(core_id)
        
        # Track ARM-specific information
        if 'CPU part' in processor:
            cpu_parts.add(processor['CPU part'])
        if 'cluster' in processor:
            clusters.add(processor['cluster'])

    def _extract_model_name(self, key, value):
        """Extract CPU model name from cpuinfo key-value pair"""
        if key in ['model name', 'Model name', 'cpu model']:
            return value
        return None

    def _extract_cpu_cores(self, key, value):
        """Extract cpu cores field from cpuinfo"""
        if key == 'cpu cores':
            try:
                return int(value)
            except ValueError:
                pass
        return None

    def _extract_siblings(self, key, value):
        """Extract siblings field from cpuinfo"""
        if key == 'siblings':
            try:
                return int(value)
            except ValueError:
                pass
        return None

    # Utility methods for common operations
    def _read_file_safely(self, file_path: Optional[str], conversion_func: Optional[Callable] = None) -> Optional[Any]:
        """Safely read a file with optional conversion"""
        try:
            if not file_path or not os.path.exists(file_path):
                return None
            
            with open(file_path, 'r') as file:
                content = file.read().strip()
                if conversion_func:
                    return conversion_func(content)
                return content
        except (IOError, ValueError, OSError) as e:
            self.logger.warning(f"Error reading file {file_path}: {e}")
            return None

    def _set_widget_sensitivity(self, widget: Optional[Any], sensitive: bool) -> None:
        """Set widget sensitivity safely"""
        if widget:
            widget.set_sensitive(sensitive)

    def _create_command_list(self, commands: List[str]) -> Optional[str]:
        """Create a command list and join with &&"""
        valid_commands = [cmd for cmd in commands if cmd]
        return ' && '.join(valid_commands) if valid_commands else None


    def _save_applied_settings(self, settings_dict: Dict[str, Any]) -> None:
        """Save applied settings with error handling"""
        try:
            for key, value in settings_dict.items():
                self.settings_applier.applied_settings[key] = value
            self.settings_applier.save_settings()
        except Exception as e:
            self.logger.error(f"Error saving applied settings: {e}")

    def _get_dropdown_selection(self, dropdown: Any) -> Optional[str]:
        """Get selected item from dropdown safely"""
        try:
            selected = dropdown.get_selected()
            model = dropdown.get_model()
            if selected >= 0:
                return model.get_string(selected)
        except Exception as e:
            self.logger.error(f"Error getting dropdown selection: {e}")
        return None

    def _determine_physical_cores(self, cpu_cores_field, siblings_field, physical_ids, 
                                 core_ids_per_physical, processor_count, cpu_parts, 
                                 clusters, virtual_cores):
        """Determine physical cores using multiple detection methods"""
        
        # Method 1: Use cpu cores field if available and reliable (x86/AMD)
        if cpu_cores_field is not None and cpu_cores_field > 0:
            # Validate against other information
            if physical_ids:
                total_cores_from_topology = sum(len(cores) for cores in core_ids_per_physical.values())
                if total_cores_from_topology > 0 and abs(cpu_cores_field - total_cores_from_topology) <= 1:
                    self.logger.info(f"Using cpu cores field: {cpu_cores_field}")
                    return cpu_cores_field
        
        # Method 2: Count from physical topology (x86/AMD/some ARM)
        if core_ids_per_physical:
            total_cores = sum(len(cores) for cores in core_ids_per_physical.values())
            if total_cores > 0:
                self.logger.info(f"Determined from topology: {total_cores} physical cores")
                return total_cores
        
        # Method 3: ARM cluster-based detection
        if clusters and len(clusters) > 1:
            # For big.LITTLE architectures, count cores per cluster
            cores_per_cluster = processor_count // len(clusters)
            if cores_per_cluster > 0:
                self.logger.info(f"ARM cluster detection: {processor_count} cores in {len(clusters)} clusters")
                return processor_count
        
        # Method 4: ARM CPU part detection for symmetric cores
        if cpu_parts and len(cpu_parts) == 1:
            # Single CPU part type suggests all cores are the same (not big.LITTLE)
            self.logger.info(f"ARM symmetric cores detected: {processor_count} cores")
            return processor_count
        
        # Method 5: Physical ID count (fallback for some systems)
        if physical_ids:
            # If we have physical IDs but no core topology, estimate
            num_physical_packages = len(physical_ids)
            cores_per_package = max(1, processor_count // num_physical_packages)
            estimated_cores = cores_per_package * num_physical_packages
            self.logger.info(f"Estimated from {num_physical_packages} packages: {estimated_cores} cores")
            return estimated_cores
        
        # Method 6: Hyperthreading detection (x86/AMD)
        if siblings_field is not None and siblings_field > 0:
            # siblings field shows threads per package
            # If siblings > cpu_cores, hyperthreading is enabled
            if cpu_cores_field and siblings_field > cpu_cores_field:
                # Hyperthreading detected
                physical_cores = cpu_cores_field
                self.logger.info(f"Hyperthreading detected: {physical_cores} cores, {siblings_field} threads")
                return physical_cores
            elif siblings_field == processor_count:
                # No hyperthreading, siblings equals total processor count
                self.logger.info(f"No hyperthreading: {siblings_field} cores")
                return siblings_field
        
        # Method 7: Special case for ARM with explicit thread count
        # On ARM, if we have more than 8 logical CPUs and no topology info,
        # it's likely all are physical cores (ARM rarely has SMT)
        if processor_count > 8 and not physical_ids and cpu_parts:
            self.logger.info(f"ARM system with {processor_count} cores (likely no SMT)")
            return processor_count
        
        # Method 8: Fallback - assume half are physical cores if no other method works
        # This is conservative for x86 with hyperthreading but better than overestimating
        fallback_cores = max(1, processor_count // 2) if processor_count > 2 else processor_count
        self.logger.warning(f"Using fallback method: {fallback_cores} cores (from {processor_count} processors)")
        return fallback_cores

    def _detect_cpu_model_fallback(self):
        """Fallback method to detect CPU model when not found in /proc/cpuinfo"""
        try:
            # Try reading from device tree (ARM systems)
            try:
                with open('/proc/device-tree/model', 'r') as f:
                    model = f.read().strip().replace('\x00', '')
                    if model:
                        return f"ARM Device: {model}"
            except (IOError, OSError):
                pass
            
            # Try reading from DMI (x86 systems)
            try:
                with open('/sys/class/dmi/id/product_name', 'r') as f:
                    product = f.read().strip()
                    with open('/sys/class/dmi/id/product_version', 'r') as f:
                        version = f.read().strip()
                    if product and version:
                        return f"{product} {version}"
                    elif product:
                        return product
            except (IOError, OSError):
                pass
            
            # Try CPU architecture detection
            import platform
            machine = platform.machine()
            if machine.startswith('arm') or machine.startswith('aarch'):
                return f"ARM Processor ({machine})"
            elif machine in ['x86_64', 'AMD64']:
                return f"x86_64 Processor"
            elif machine.startswith('i'):
                return f"x86 Processor"
            else:
                return f"Unknown Processor ({machine})"
                
        except Exception as e:
            self.logger.error(f"Error in CPU model fallback detection: {e}")
            return "Unknown CPU"

    def read_total_ram(self, meminfo_file):
        # Read the total RAM from the meminfo file
        total_ram = None
        try:
            with open(meminfo_file, 'r') as file:
                for line in file:
                    if line.startswith('MemTotal'):
                        total_ram = int(line.split()[1]) // 1024  # Convert to MB
                        break
        except Exception as e:
            self.logger.error(f"Error reading meminfo file: {e}")
        return total_ram

    def get_allowed_cpu_frequency(self):
        # Get the allowed CPU frequencies from the system files
        try:
            min_allowed_freqs = []
            max_allowed_freqs = []

            for i in range(self.cpu_file_search.thread_count):
                min_freq_file = self.cpu_file_search.cpu_files['cpuinfo_min_files'].get(i)
                max_freq_file = self.cpu_file_search.cpu_files['cpuinfo_max_files'].get(i)

                if not min_freq_file or not max_freq_file:
                    # Default values when the files aren't found
                    min_allowed_freqs.append(CPUManagerConfig.DEFAULT_MIN_FREQ_MHZ)
                    max_allowed_freqs.append(CPUManagerConfig.DEFAULT_MAX_FREQ_MHZ)
                    continue

                try:
                    with open(min_freq_file) as min_file:
                        min_freq_mhz = int(min_file.read()) / CPUManagerConfig.KHZ_TO_MHZ_DIVISOR
                        min_allowed_freqs.append(min_freq_mhz)
                except (IOError, ValueError) as e:
                    self.logger.warning(f"Error reading min frequency for thread {i}: {e}")
                    min_allowed_freqs.append(CPUManagerConfig.DEFAULT_MIN_FREQ_FALLBACK)

                try:
                    with open(max_freq_file) as max_file:
                        max_freq_mhz = int(max_file.read()) / CPUManagerConfig.KHZ_TO_MHZ_DIVISOR
                        max_allowed_freqs.append(max_freq_mhz)
                except (IOError, ValueError) as e:
                    self.logger.warning(f"Error reading max frequency for thread {i}: {e}")
                    max_allowed_freqs.append(CPUManagerConfig.DEFAULT_MAX_FREQ_MHZ)

            if not min_allowed_freqs or not max_allowed_freqs:
                self.logger.warning("No valid CPU frequency files found, using defaults")
                return ([CPUManagerConfig.DEFAULT_MIN_FREQ_MHZ] * self.cpu_file_search.thread_count, 
                       [CPUManagerConfig.DEFAULT_MAX_FREQ_MHZ] * self.cpu_file_search.thread_count)

            return min_allowed_freqs, max_allowed_freqs

        except Exception as e:
            self.logger.error(f"Error getting CPU frequencies: {e}")
            return ([CPUManagerConfig.DEFAULT_MIN_FREQ_MHZ] * self.cpu_file_search.thread_count, 
                   [CPUManagerConfig.DEFAULT_MAX_FREQ_MHZ] * self.cpu_file_search.thread_count)

    def get_allowed_tdp_values(self):
        # First, check the CPU type
        cpu_type = self.cpu_file_search.cpu_type

        # If CPU type is not Intel, return None without logging an error
        if cpu_type != "Intel":
            self.logger.info("TDP is only supported on Intel CPUs, not logging as error.")
            return None

        # Get the allowed TDP values for Intel CPUs
        max_tdp_file = self.cpu_file_search.intel_tdp_files['max_tdp']
        if not max_tdp_file or not os.path.exists(max_tdp_file):
            self.logger.info("Intel Max TDP file not found. This is expected on non-Intel systems.")
            return None

        try:
            with open(max_tdp_file, 'r') as f:
                max_tdp_value_uw = int(f.read().strip())
                max_tdp_value_w = max_tdp_value_uw / CPUManagerConfig.MICROWATTS_TO_WATTS
                return max_tdp_value_w
        except ValueError as e:
            self.logger.error(f"Error reading TDP values: {e}")
            return None

    def read_cpu_speeds(self):
        # Read the current CPU speeds from the appropriate system files
        speeds = []  # List to store the CPU speeds
        for i in range(self.cpu_file_search.thread_count):
            speed_file = self.cpu_file_search.cpu_files['speed_files'].get(i)
            if speed_file and os.path.exists(speed_file):
                with open(speed_file, 'r') as file:
                    speed_str = file.read().strip()
                    if speed_str:
                        speed = int(speed_str) / CPUManagerConfig.KHZ_TO_MHZ_DIVISOR
                        speeds.append((i, speed))
        return speeds

    def update_clock_labels(self, speeds):
        # Update the clock speed labels in the GUI
        has_valid_speeds = bool(speeds)
        
        for i, speed in speeds:
            if i in self.clock_labels and self.clock_labels[i] is not None:
                label = self.clock_labels[i]
                # Show/hide label based on whether we have valid speeds
                label.set_visible(has_valid_speeds and speed > 0)
                
                if has_valid_speeds and speed > 0:
                    if self.global_state.display_ghz:
                        display_speed = speed / 1000
                        unit = "GHz"
                        label.set_text(f"{display_speed:.2f} {unit}")
                    else:
                        display_speed = speed
                        unit = "MHz"
                        label.set_text(f"{display_speed:.0f} {unit}")
            else:
                if i not in self.clock_labels:
                    self.logger.warning(f"No clock label found for thread {i}")
        
        # Also handle threads that don't have speed data
        for i in range(self.cpu_file_search.thread_count):
            if i in self.clock_labels and self.clock_labels[i] is not None:
                thread_has_speed = any(thread_i == i for thread_i, _ in speeds)
                if not thread_has_speed:
                    self.clock_labels[i].set_visible(False)

    def update_average_speed(self, speeds):
        # Update the average clock speed label in the GUI
        if speeds and self.avg_clock_label is not None:
            average_speed = sum(speed for _, speed in speeds) / len(speeds)
            # Show the label and update text
            self.avg_clock_label.set_visible(True)
            if self.global_state.display_ghz:
                display_speed = average_speed / 1000
                unit = "GHz"
                self.avg_clock_label.set_text(f"{display_speed:.2f} {unit}")
            else:
                display_speed = average_speed
                unit = "MHz"
                self.avg_clock_label.set_text(f"{display_speed:.0f} {unit}")
        else:
            # Hide the label when no speeds are available
            if self.avg_clock_label is not None:
                self.avg_clock_label.set_visible(False)
            if not speeds:
                self.logger.warning("No valid CPU clock speeds found")

    def update_clock_speeds(self):
        # Update the clock speeds of all CPU threads
        try:
            speeds = self.read_cpu_speeds()
            if speeds:
                self.update_clock_labels(speeds)
                self.update_average_speed(speeds)
            else:
                self.logger.warning("No CPU speeds available to update")
        except Exception as e:
            self.logger.error(f"Error updating CPU clock speeds: {e}")

    def read_stat_file(self):
        # Read the CPU statistics from the stat file
        stat_file_path = self.cpu_file_search.proc_files['stat']
        if not stat_file_path:
            self.logger.error("Stat file not found.")
            return None

        cpu_stats = []  # List to store the CPU statistics
        with open(stat_file_path, 'r') as file:
            for line in file:
                if line.startswith('cpu'):
                    fields = line.split()
                    if len(fields) >= 5:
                        cpu_stats.append((fields[0], int(fields[1]), int(fields[2]), int(fields[3]), int(fields[4])))

        return cpu_stats

    def calculate_load(self, prev_stat, curr_stat):
        # Calculate the CPU load based on previous and current statistics
        def calc_load(data):
            loads = {}  # Dictionary to store the load percentages for each CPU
            (cpu_id, prev_user, prev_nice, prev_system, prev_idle), \
            (_, curr_user, curr_nice, curr_system, curr_idle) = data

            total_diff = (curr_user + curr_nice + curr_system + curr_idle) - \
                         (prev_user + prev_nice + prev_system + prev_idle)
            idle_diff = curr_idle - prev_idle

            # Return a load value of 0 if there is no difference, implying no load change
            if total_diff:
                return (cpu_id, CPUManagerConfig.PERCENTAGE_MULTIPLIER * (total_diff - idle_diff) / total_diff)
            else:
                return (cpu_id, 0.0)

        # Use map to apply calc_load function across the zipped lists of previous and current stats
        loads = map(calc_load, zip(prev_stat, curr_stat))

        # Convert the map result to a dictionary
        return dict(loads)

    def update_cpu_load(self):
        # Update the CPU load for all threads
        try:
            curr_stat = self.read_stat_file()  # Read the current CPU statistics
            if not curr_stat:
                return

            # Calculate the load based on the previous and current statistics
            loads = self.calculate_load(self.prev_stat, curr_stat)
            if loads and loads != self.prev_loads:
                self.update_load_history(loads)
                self.update_load_gui(loads)
                self.prev_loads = loads

            # Update the previous statistics
            self.prev_stat = curr_stat
        except Exception as e:
            self.logger.error(f"Error updating CPU load: {e}")

    def update_load_history(self, loads):
        for cpu_id, load in loads.items():
            if cpu_id.startswith('cpu') and cpu_id != 'cpu':
                thread_index = int(cpu_id[3:])
                if thread_index in self.cpu_load_history:
                    self.cpu_load_history[thread_index].pop(0)
                    self.cpu_load_history[thread_index].append(load)

    def update_load_gui(self, loads):
        try:
            total_load = 0
            count = 0
            for cpu_id, load in loads.items():
                if cpu_id.startswith('cpu') and cpu_id != 'cpu':
                    thread_index = int(cpu_id[3:])
                    if thread_index in self.cpu_graphs:
                        self.cpu_graphs[thread_index].update(load / 100)
                    
                    if thread_index in self.usage_labels:
                        self.usage_labels[thread_index].set_text(f"{load:.1f}%")
                    
                    total_load += load
                    count += 1

            if count > 0:
                avg_load = total_load / count
                if self.avg_usage_graph:
                    self.avg_usage_graph.update(avg_load / 100)
                
                if self.avg_usage_label:
                    self.avg_usage_label.set_text(f"{avg_load:.1f}%")
        except Exception as e:
            self.logger.error(f"Error updating load GUI: {e}")

    def read_and_parse_temperature(self):
        # Read and parse the CPU package temperature
        temp_str = self._read_file_safely(self.cpu_file_search.package_temp_file)
        if temp_str and temp_str.isdigit():
            temp_celsius = int(temp_str) / CPUManagerConfig.TEMP_MILLIDEGREES_TO_CELSIUS
            return temp_str, temp_celsius
        elif temp_str and not temp_str.isdigit():
            self.logger.error("Temperature reading is not a valid number.")
        elif not self.cpu_file_search.package_temp_file:
            self.logger.info("No package temperature file found. This is common on ARM or some virtual environments.")
        return None, None

    def read_package_temperature(self):
        # Read the CPU package temperature and update the GUI
        try:
            temp_str, temp_celsius = self.read_and_parse_temperature()
            if temp_celsius is not None:
                temp_text = f"{int(temp_celsius)} °C"
                # Use conditional label creation if monitor tab manager is available
                if self.monitor_tab_manager:
                    self.monitor_tab_manager.create_temp_label_if_needed(temp_text)
                elif hasattr(self, 'package_temp_label') and self.package_temp_label is not None:
                    # Fallback to old method if monitor tab manager not available
                    self.package_temp_label.set_text(temp_text)
                return temp_celsius
            else:
                # Don't show anything if temperature is unavailable (conditional creation will handle this)
                if self.monitor_tab_manager:
                    self.monitor_tab_manager.create_temp_label_if_needed(None)
                elif hasattr(self, 'package_temp_label') and self.package_temp_label is not None:
                    self.package_temp_label.set_visible(False)
        except Exception as e:
            self.logger.error(f"Error reading package temperature: {e}")
        return None

    def update_throttle(self):
        # Update the thermal throttle status in the GUI
        try:
            self.is_throttling = False  # Reset the throttling flag initially

            if self.cpu_file_search.cpu_type == "Intel":
                # Intel specific throttle file check
                for i in range(self.cpu_file_search.thread_count):
                    package_throttle_time_file = self.cpu_file_search.cpu_files.get('package_throttle_time_files', {}).get(i)

                    if package_throttle_time_file and os.path.exists(package_throttle_time_file):
                        with open(package_throttle_time_file, 'r') as file:
                            current_throttle_time = int(file.read().strip())

                        if self.prev_package_throttle_time[i] is not None:
                            if current_throttle_time > self.prev_package_throttle_time[i]:
                                self.is_throttling = True  # Set throttling flag if throttle time has increased

                        self.prev_package_throttle_time[i] = current_throttle_time  # Update previous throttle time

            # Use conditional label creation if monitor tab manager is available
            if self.monitor_tab_manager:
                self.monitor_tab_manager.create_thermal_status_label_if_needed(self.is_throttling)
            elif hasattr(self, 'thermal_throttle_label') and self.thermal_throttle_label:
                # Fallback to old method if monitor tab manager not available
                if self.is_throttling:
                    self.thermal_throttle_label.set_markup('<span foreground="red">Throttling</span>')
                    self.thermal_throttle_label.set_visible(True)
                else:
                    self.thermal_throttle_label.set_visible(False)

        except Exception as e:
            self.logger.error(f"Error updating throttle widget: {e}")

    def read_and_get_governor(self):
        # Read the current CPU governor from the system file
        governor_file_path = self.cpu_file_search.cpu_files['governor_files'].get(0)
        return self._read_file_safely(governor_file_path)

    def get_current_governor(self):
        # Get the current CPU governor and update the GUI
        try:
            current_governor = self.read_and_get_governor()
            if current_governor:
                # Use conditional label creation if monitor tab manager is available
                if self.monitor_tab_manager:
                    self.monitor_tab_manager.create_governor_label_if_needed(current_governor)
                elif hasattr(self, 'current_governor_label') and self.current_governor_label is not None:
                    # Fallback to old method if monitor tab manager not available
                    self.current_governor_label.set_label(f"Current Governor: {current_governor}")
            else:
                # Don't show anything if governor is unavailable (conditional creation will handle this)
                if self.monitor_tab_manager:
                    self.monitor_tab_manager.create_governor_label_if_needed(None)
                elif hasattr(self, 'current_governor_label') and self.current_governor_label is not None:
                    self.current_governor_label.set_visible(False)
                self.logger.error("Governor file path not found or could not read the governor for thread 0")
        except Exception as e:
            self.logger.error(f"Error updating CPU governor: {e}")

    def update_governor_dropdown(self):
        # Update the governor drop down with available governors
        try:
            # Gather all unique governors from available governor files
            self.global_state.unique_governors.clear()
            self.logger.info(f"Searching for governor files across {self.cpu_file_search.thread_count} threads")
            
            for i in range(self.cpu_file_search.thread_count):
                available_governors_file = self.cpu_file_search.cpu_files['available_governors_files'].get(i)
                self.logger.info(f"Thread {i}: Governor file path: {available_governors_file}")
                
                if available_governors_file and os.path.exists(available_governors_file):
                    try:
                        with open(available_governors_file, 'r') as file:
                            governors = file.read().strip().split()
                            self.logger.info(f"Thread {i}: Found governors: {governors}")
                            self.global_state.unique_governors.update(governors)
                    except Exception as e:
                        self.logger.error(f"Error reading available governors from {available_governors_file}: {e}")
                else:
                    self.logger.warning(f"Thread {i}: Governor file not found or doesn't exist: {available_governors_file}")

            self.logger.info(f"Total unique governors found: {self.global_state.unique_governors}")
            
            # Create the list of governors with the placeholder at the beginning
            governors_list = ["Select Governor"] + sorted(self.global_state.unique_governors)

            # Update the Gtk.StringList model for the dropdown
            if hasattr(self, 'governor_dropdown') and self.governor_dropdown:
                self.logger.info(f"Updating dropdown with governors: {governors_list}")
                try:
                    # Create new StringList and populate it
                    new_store = self.widget_factory.create_string_list()
                    for governor in governors_list:
                        new_store.append(governor)
                        self.logger.info(f"Added governor to dropdown: {governor}")
                    
                    # Set the model and selection
                    self.governor_dropdown.set_model(new_store)
                    self.governor_dropdown.set_selected(0)
                    
                    # Make sure the dropdown is sensitive (not greyed out)
                    self.governor_dropdown.set_sensitive(True)
                    
                    self.logger.info(f"Governor dropdown updated successfully with {len(governors_list)} items")
                except Exception as e:
                    self.logger.error(f"Error updating dropdown model: {e}")
            else:
                self.logger.error(f"Governor dropdown not available: hasattr={hasattr(self, 'governor_dropdown')}, dropdown={getattr(self, 'governor_dropdown', None)}")
        except Exception as e:
            self.logger.error("Failed to update governor dropdown: %s", e)

    def is_boost_supported(self):
        """Check if CPU boost is supported and functional on this system"""
        try:
            # Check Intel boost path
            if self.cpu_file_search.cpu_type == "Intel" and self.cpu_file_search.intel_boost_path and os.path.exists(self.cpu_file_search.intel_boost_path):
                return self._test_boost_functionality(self.cpu_file_search.intel_boost_path)
            
            # Check generic boost files
            for boost_file in self.cpu_file_search.cpu_files['boost_files'].values():
                if os.path.exists(boost_file):
                    return self._test_boost_functionality(boost_file)
                    
            self.logger.info("No valid boost control files found - boost not supported")
            return False
        except Exception as e:
            self.logger.error(f"Error checking boost support: {e}")
            return False

    def _test_boost_functionality(self, boost_file):
        """Test if boost file is actually functional (not just present)"""
        try:
            # Read current value
            with open(boost_file, 'r') as f:
                current_value = f.read().strip()
            
            # Check if boost frequencies are available (indicates real boost support)
            boost_freq_file = boost_file.replace('boost', 'scaling_boost_frequencies')
            if os.path.exists(boost_freq_file):
                with open(boost_freq_file, 'r') as f:
                    boost_freqs = f.read().strip()
                    if not boost_freqs:
                        self.logger.info(f"Boost file exists but no boost frequencies available - boost not functional")
                        return False
            
            # For ARM64 systems, boost files often exist but don't work
            # Try a simple test write (if current value is 0, we could try writing 0 again)
            try:
                with open(boost_file, 'w') as f:
                    f.write(current_value)  # Write the same value back
                self.logger.info(f"Boost functionality test passed for {boost_file}")
                return True
            except (OSError, IOError, PermissionError):
                self.logger.info(f"Boost file exists but is not writable - boost not functional: {boost_file}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error testing boost functionality for {boost_file}: {e}")
            return False

    def find_boost_type(self):
        # Determine which boost files are correct for your CPU type
        if self.cpu_file_search.cpu_type == "Intel" and self.cpu_file_search.intel_boost_path and os.path.exists(self.cpu_file_search.intel_boost_path):
            return self.read_boost_file(self.cpu_file_search.intel_boost_path, intel=True)
        else:
            for boost_file in self.cpu_file_search.cpu_files['boost_files'].values():
                if os.path.exists(boost_file):
                    return self.read_boost_file(boost_file)
            self.logger.info("No valid boost control files found.")
            if hasattr(self, 'boost_checkbutton') and self.boost_checkbutton:
                self.boost_checkbutton.hide()
            return None

    def read_boost_file(self, file_path, intel=False):
        # Read the boost file to determine the current boost status
        try:
            with open(file_path, 'r') as file:
                content = file.read().strip()
                if content in ['0', '1']:
                    return content == ('0' if intel else '1')
                else:
                    self.logger.error(f"Unexpected content in boost file at {file_path}: {content}")
                    return False
        except IOError as e:
            self.logger.info(f"Boost file not accessible at {file_path}: {e}")
            return False

    def update_boost_checkbutton(self):
        # Update the boost checkbutton status in the GUI
        try:
            current_status = self.find_boost_type()
            if current_status is None:
                if self.boost_checkbutton:
                    self.boost_checkbutton.set_visible(False)
            else:
                if self.boost_checkbutton:
                    self.boost_checkbutton.set_visible(True)
                    if self.boost_checkbutton.get_active() != current_status:
                        self.boost_checkbutton.handler_block_by_func(self.toggle_boost)
                        self.boost_checkbutton.set_active(current_status)
                        self.boost_checkbutton.handler_unblock_by_func(self.toggle_boost)
        except Exception as e:
            self.logger.error(f"Error updating boost checkbutton status: {e}")

    def apply_cpu_clock_speed_limits(self, widget=None):
        try:
            self._set_apply_min_max_sensitivity(False)
            command_list = []
            any_active_checkbutton = False

            for i in range(self.cpu_file_search.thread_count):
                widgets = self._retrieve_widgets_for_thread(i)
                if not all(widgets):
                    continue

                min_scale, max_scale, checkbutton = widgets
                if checkbutton.get_active():
                    any_active_checkbutton = True
                    speeds = self._validate_and_get_speeds(min_scale, max_scale, i)
                    if not all(speeds):
                        continue

                    min_speed, max_speed = speeds
                    self.logger.info(f"Applying clock speed for thread {i}")
                    commands = self._get_frequency_commands(min_speed, max_speed, i)
                    if all(commands):
                        command_list.extend(commands)
                    else:
                        self.logger.error(f"Failed to get frequency commands for thread {i}")
                else:
                    self.logger.info(f"Skipping clock speed for thread {i} as checkbutton is not active")

            self._execute_speed_limit_commands(command_list, any_active_checkbutton)

        except Exception as e:
            self.logger.error(f"Error applying CPU clock speed limits: {e}")
            self._set_apply_min_max_sensitivity(True)

    def _set_apply_min_max_sensitivity(self, sensitive):
        """Set sensitivity of apply min/max button"""
        self._set_widget_sensitivity(self.apply_max_min_button, sensitive)

    def _retrieve_widgets_for_thread(self, i):
        """Retrieve GUI widgets for a specific thread"""
        try:
            min_scale = self.min_scales[i]
            max_scale = self.max_scales[i]
            checkbutton = self.cpu_max_min_checkbuttons[i]
            return min_scale, max_scale, checkbutton
        except KeyError:
            self.logger.error(f"Scale or checkbutton widget for thread {i} not found.")
            return None, None, None

    def _validate_and_get_speeds(self, min_scale, max_scale, i):
        """Validate and get speed values from scales"""
        try:
            min_speed = int(min_scale.get_value())
            max_speed = int(max_scale.get_value())
            if not (0 <= min_speed <= max_speed <= CPUManagerConfig.MAX_SPEED_LIMIT):
                self.logger.error(f"Invalid input: Please enter valid CPU speed limits for thread {i}.")
                return None, None
            return min_speed, max_speed
        except ValueError:
            self.logger.error(f"Invalid input: CPU speeds must be a number for thread {i}.")
            return None, None

    def _get_frequency_commands(self, min_speed, max_speed, i):
        """Generate frequency setting commands for a thread"""
        min_frequency_in_khz = min_speed * CPUManagerConfig.KHZ_TO_MHZ_DIVISOR
        max_frequency_in_khz = max_speed * CPUManagerConfig.KHZ_TO_MHZ_DIVISOR

        max_file = self.cpu_file_search.cpu_files['scaling_max_files'].get(i)
        min_file = self.cpu_file_search.cpu_files['scaling_min_files'].get(i)

        if max_file and min_file:
            max_command = f'echo {max_frequency_in_khz} | tee {max_file} > /dev/null'
            min_command = f'echo {min_frequency_in_khz} | tee {min_file} > /dev/null'
            return max_command, min_command
        return None, None

    def _execute_speed_limit_commands(self, command_list, any_active_checkbutton):
        """Execute the speed limit commands"""
        if command_list:
            full_command = ' && '.join(command_list)
            self.privileged_actions.run_pkexec_command(
                full_command, 
                success_callback=self._speed_limit_success_callback, 
                failure_callback=self._speed_limit_failure_callback
            )
        else:
            if not any_active_checkbutton:
                self._set_apply_min_max_sensitivity(True)
                self.show_speed_limits_info_window("You need at least one thread enabled to apply the speed limits.")
            else:
                self.logger.info("No valid commands generated to apply clock speed limits.")
                self._set_apply_min_max_sensitivity(True)

    def _speed_limit_success_callback(self):
        """Handle successful execution of speed limit commands"""
        self.logger.info("Successfully applied CPU clock speed limits.")
        self._set_apply_min_max_sensitivity(True)
        
        settings_to_save = {
            "min_speeds": {i: self.min_scales[i].get_value() for i in self.min_scales if self.min_scales[i].get_value() > 0},
            "max_speeds": {i: self.max_scales[i].get_value() for i in self.max_scales if self.max_scales[i].get_value() > 0},
            "checked_threads": {i: self.cpu_max_min_checkbuttons[i].get_active() for i in self.cpu_max_min_checkbuttons}
        }
        self._save_applied_settings(settings_to_save)

    def _speed_limit_failure_callback(self, error_message):
        """Handle failed execution of speed limit commands"""
        self._set_apply_min_max_sensitivity(True)
        if error_message == 'canceled':
            self.logger.info("User canceled the min / max frequency pkexec prompt.")
        else:
            self.logger.error(f"Failed to apply CPU clock speed limits: {error_message}")

    def show_speed_limits_info_window(self, message):
        # Show the information dialog for the speed limits info
        try:
            speed_limits_info_window = self.widget_factory.create_window("Information", None, 300, 50)

            speed_limits_info_box = self.widget_factory.create_box(speed_limits_info_window)

            speed_limits_info_label = self.widget_factory.create_label(
                speed_limits_info_box,
                message,
                margin_start=10, margin_end=10, margin_top=10)

            def on_destroy(widget):
                speed_limits_info_window.close()

            speed_limits_info_button = self.widget_factory.create_button(
                speed_limits_info_box, "OK", margin_start=131, margin_end=131, margin_bottom=10)
            speed_limits_info_button.connect("clicked", on_destroy)

            speed_limits_info_window.connect("close-request", on_destroy)

            speed_limits_info_window.present()
        except Exception as e:
            self.logger.error(f"Error showing speed limits info dialog: {e}")

    def set_cpu_governor(self, dropdown, param):
        # Handle the change of CPU governor from the drop down and set it
        try:
            self._set_widget_sensitivity(self.governor_dropdown, False)
            
            selected_governor = self._get_dropdown_selection(dropdown)
            if selected_governor == "Select Governor" or selected_governor is None:
                return   # Do nothing if placeholder or no selection is made

            if selected_governor not in self.valid_governors:
                self.logger.error(f"Invalid CPU governor selected: {selected_governor}")
                self._set_widget_sensitivity(self.governor_dropdown, True)
                GLib.idle_add(lambda: dropdown.set_selected(0))
                return

            self.logger.info(f"Setting CPU governor to: {selected_governor}")
            command_list = self._get_governor_command_list(selected_governor)

            if command_list:
                full_command = self._create_command_list(command_list)
                if full_command:
                    self.privileged_actions.run_pkexec_command(
                        full_command, 
                        success_callback=lambda: self._governor_success_callback(selected_governor, dropdown), 
                        failure_callback=lambda error: self._governor_failure_callback(error, dropdown)
                    )
                else:
                    self.logger.error("Failed to create command list for governor change.")
                    self._set_widget_sensitivity(self.governor_dropdown, True)
            else:
                self.logger.error("No CPU governor files found to apply governor change.")
                self._set_widget_sensitivity(self.governor_dropdown, True)

        except Exception as e:
            self.logger.error(f"An error occurred while handling CPU governor change: {e}")
            self._set_widget_sensitivity(self.governor_dropdown, True)

    def _get_governor_command_list(self, governor):
        """Generate command list to set governor for all threads"""
        command_list = []
        for i in range(self.cpu_file_search.thread_count):
            governor_file = self.cpu_file_search.cpu_files['governor_files'].get(i)
            if governor_file:
                command_list.append(f'echo "{governor}" | tee {governor_file} > /dev/null')
        return command_list

    def _governor_success_callback(self, governor, dropdown):
        """Handle successful governor change"""
        self.logger.info(f"Successfully set governor to {governor}")
        self._set_widget_sensitivity(self.governor_dropdown, True)
        self._save_applied_settings({"governor": governor})

    def _governor_failure_callback(self, error, dropdown):
        """Handle failed governor change"""
        if error == 'canceled':
            self.logger.info("User canceled the governor change pkexec prompt.")
            GLib.idle_add(lambda: dropdown.set_selected(0))
        else:
            self.logger.error(f"Failed to set CPU governor: {error}")
        self._set_widget_sensitivity(self.governor_dropdown, True)

    def toggle_boost(self, widget=None):
        # Toggle the CPU boost clock on or off
        try:
            self.stop_control_tasks()  # Stop the control tasks while the method is running
            current_status = self.find_boost_type()  # Get the current boost status
            is_enabled = not current_status  # Determine the new boost status

            def set_toggle_boost_sensitivity():
                self.boost_checkbutton.set_sensitive(False)

            def get_command_list():
                # Generate the command list to toggle boost
                command_list = []
                if self.cpu_file_search.cpu_type == "Intel" and self.cpu_file_search.intel_boost_path:
                    # For Intel CPUs, set the boost value based on the new status
                    value = '0' if is_enabled else '1'
                    command_list.append(f'echo {value} | sudo tee {self.cpu_file_search.intel_boost_path} > /dev/null')
                else:
                    # For non-Intel CPUs, toggle the boost for each thread
                    for i in range(self.cpu_file_search.thread_count):
                        boost_file = self.cpu_file_search.cpu_files['boost_files'].get(i)
                        if boost_file:
                            value = '1' if is_enabled else '0'
                            command_list.append(f'echo {value} | sudo tee {boost_file} > /dev/null')
                return command_list

            def success_callback():
                # Handle successful execution of pkexec command
                self.logger.info("CPU boost toggled successfully.")
                self.global_state.boost_enabled = is_enabled  # Update the global state
                self.schedule_control_tasks()  # Restart the control tasks
                self.boost_checkbutton.set_sensitive(True)
                self.update_boost_checkbutton()  # Update the checkbutton state
                try:
                    # Update applied settings
                    self.settings_applier.applied_settings["boost"] = is_enabled
                    self.settings_applier.save_settings()
                except Exception as e:
                    self.logger.error(f"Error saving the applied boost setting: {e}")

            def failure_callback(error_message):
                # Handle failures from pkexec command
                if error_message == 'canceled':
                    self.logger.info("User canceled the CPU boost pkexec prompt.")
                else:
                    self.logger.error("Failed to toggle CPU boost: " + error_message)
                self.schedule_control_tasks()
                self.boost_checkbutton.set_sensitive(True)
                self.update_boost_checkbutton()

            set_toggle_boost_sensitivity()

            command_list = get_command_list()

            if command_list:
                # If there are commands to execute, run them with pkexec
                full_command = ' && '.join(command_list)
                self.privileged_actions.run_pkexec_command(full_command, success_callback=success_callback, failure_callback=failure_callback)
            else:
                self.logger.error("No commands generated to toggle CPU boost.")
                self.schedule_control_tasks()
                self.boost_checkbutton.set_sensitive(True)
                self.update_boost_checkbutton()
        except Exception as e:
            self.logger.error(f"Error toggling CPU boost: {e}")
            self.schedule_control_tasks()
            self.boost_checkbutton.set_sensitive(True)
            self.update_boost_checkbutton()

    def set_intel_tdp(self, widget=None):
        # Set the TDP (Thermal Design Power) for Intel CPUs
        try:
            def set_tdp_sensitivity():
                self.apply_tdp_button.set_sensitive(False)

            def validate_cpu_type():
                # Validate the CPU type
                if self.cpu_file_search.cpu_type != "Intel":
                    self.logger.error("TDP control is only supported for Intel CPUs.")
                    return False
                return True

            def get_tdp_file():
                # Retrieve the TDP control file path
                tdp_file = self.cpu_file_search.intel_tdp_files['tdp']
                if not tdp_file or not os.path.exists(tdp_file):
                    self.logger.error("Intel TDP control file not found.")
                    return None
                return tdp_file

            def create_tdp_command(tdp_file):
                # Create the command to set the TDP value
                tdp_value_watts = self.tdp_scale.get_value()
                tdp_value_microwatts = int(tdp_value_watts * CPUManagerConfig.MICROWATTS_TO_WATTS)
                command = f'echo {tdp_value_microwatts} | sudo tee {tdp_file} > /dev/null'
                return command, tdp_value_microwatts

            def success_callback():
                # Handle successful execution of pkexec command
                self.logger.info(f"Successfully set TDP.")
                self.apply_tdp_button.set_sensitive(True)
                try:
                    self.settings_applier.applied_settings["tdp"] = tdp_value_microwatts
                    self.settings_applier.save_settings()
                except Exception as e:
                    self.logger.error(f"Error saving the applied Intel TDP setting: {e}")

            def failure_callback(error_message):
                # Handle failures from pkexec command
                if error_message == 'canceled':
                    self.logger.info("User canceled the TDP pkexec prompt.")
                else:
                    self.logger.error(f"Failed to set TDP for Intel CPU: {error_message}")
                self.apply_tdp_button.set_sensitive(True)

            if not validate_cpu_type():
                return False

            tdp_file = get_tdp_file()
            if not tdp_file:
                return False

            set_tdp_sensitivity()

            command, tdp_value_microwatts = create_tdp_command(tdp_file)
            self.privileged_actions.run_pkexec_command(command, success_callback=success_callback, failure_callback=failure_callback)
            return True

        except Exception as e:
            self.logger.error(f"Error setting Intel TDP: {e}")
            self.apply_tdp_button.set_sensitive(True)
            return False

    def set_ryzen_tdp(self, widget=None):
        # Set the TDP (Thermal Design Power) for AMD Ryzen CPUs
        try:
            def set_tdp_sensitivity():
                self.apply_tdp_button.set_sensitive(False)

            def validate_cpu_type():
                # Validate the CPU type
                if self.cpu_file_search.cpu_type != "Other":
                    self.logger.error("TDP control with ryzen_smu is only supported for AMD Ryzen CPUs.")
                    return False
                return True

            def create_tdp_command():
                # Create the command to set the TDP value
                tdp_value_watts = self.tdp_scale.get_value()
                tdp_value_milliwatts = int(tdp_value_watts * CPUManagerConfig.WATTS_TO_MILLIWATTS)
                command = f"printf '%0*x' 48 {tdp_value_milliwatts} | fold -w 2 | tac | tr -d '\\n' | xxd -r -p | sudo tee /sys/kernel/ryzen_smu_drv/smu_args && printf '\\x53' | sudo tee /sys/kernel/ryzen_smu_drv/rsmu_cmd"
                return command, tdp_value_milliwatts

            def success_callback():
                # Handle successful execution of pkexec command
                self.logger.info(f"Successfully set TDP")
                self.apply_tdp_button.set_sensitive(True)
                try:
                    self.settings_applier.applied_settings["tdp"] = tdp_value_milliwatts
                    self.settings_applier.save_settings()
                except Exception as e:
                    self.logger.error(f"Error saving the applied AMD Ryzen TDP setting: {e}")

            def failure_callback(error_message):
                # Handle failures from pkexec command
                if error_message == 'canceled':
                    self.logger.info("User canceled the TDP pkexec prompt.")
                else:
                    self.logger.error(f"Failed to set TDP for Ryzen CPU: {error_message}")
                self.apply_tdp_button.set_sensitive(True)

            if not validate_cpu_type():
                return False

            if not self.global_state.is_ryzen_smu_installed():
                self.logger.error("ryzen_smu is not installed.")
                return False

            set_tdp_sensitivity()

            command, tdp_value_milliwatts = create_tdp_command()
            self.privileged_actions.run_pkexec_command(command, success_callback=success_callback, failure_callback=failure_callback)
            return True

        except Exception as e:
            self.logger.error(f"Error setting Ryzen TDP: {e}")
            self.apply_tdp_button.set_sensitive(True)
            return False

    def set_pbo_curve_offset(self, widget=None):
        try:
            def set_pbo_sensitivity():
                self.apply_pbo_button.set_sensitive(False)

            def validate_cpu_type():
                # Validate the CPU type
                if self.cpu_file_search.cpu_type != "Other":
                    self.logger.error("PBO curve setting is only supported for AMD Ryzen CPUs.")
                    return False
                return True

            def create_pbo_command(offset_value):
                # Create the command to set the PBO curve offset value for all cores
                commands = []
                physical_cores = self.parse_cpu_info(self.cpu_file_search.proc_files['cpuinfo'])[2]

                # Convert the positive offset_value to a negative offset
                offset_value = -offset_value

                # Convert offset_value to a 16-bit two's complement representation
                if offset_value < 0:
                    offset_value = (1 << CPUManagerConfig.BINARY_SHIFT_16) + offset_value

                for core_id in range(physical_cores):
                    # Calculate smu_args_value for each core
                    smu_args_value = ((core_id & 8) << 5 | core_id & 7) << 20 | (offset_value & CPUManagerConfig.TWO_COMPLEMENT_MASK)
                    commands.append(f"echo {smu_args_value} | sudo tee /sys/kernel/ryzen_smu_drv/smu_args > /dev/null")
                    commands.append(f"echo '0x35' | sudo tee /sys/kernel/ryzen_smu_drv/mp1_smu_cmd > /dev/null")
                return " && ".join(commands)

            def success_callback():
                self.logger.info(f"Successfully set PBO curve offset using scale value.")
                self.apply_pbo_button.set_sensitive(True)
                try:
                    # Update applied_settings with the PBO offset value
                    self.settings_applier.applied_settings["pbo_offset"] = offset_value
                    self.settings_applier.save_settings()
                except Exception as e:
                    self.logger.error(f"Error saving the applied PBO offset setting: {e}")

            def failure_callback(error_message):
                # Handle failures from pkexec command
                if error_message == 'canceled':
                    self.logger.info("User canceled the PBO curve setting pkexec prompt.")
                else:
                    self.logger.error(f"Failed to set PBO curve offset: {error_message}")
                self.apply_pbo_button.set_sensitive(True)

            if not validate_cpu_type():
                return False

            if not self.global_state.is_ryzen_smu_installed():
                self.logger.error("ryzen_smu is not installed.")
                return False

            set_pbo_sensitivity()

            offset_value = int(self.pbo_curve_scale.get_value())
            command = create_pbo_command(offset_value)
            self.privileged_actions.run_pkexec_command(command, success_callback=success_callback, failure_callback=failure_callback)
            return True

        except Exception as e:
            self.logger.error(f"Error setting PBO curve offset: {e}")
            self.apply_pbo_button.set_sensitive(True)
            return False

    def set_energy_perf_bias(self, dropdown, param):
        try:
            def set_epb_sensitivity():
                self.epb_dropdown.set_sensitive(False)

            def get_selected_bias():
                # Retrieve the selected EPB from the drop down
                selected = dropdown.get_selected()
                model = dropdown.get_model()
                if selected >= 0:
                    return model.get_string(selected)
                return None

            def get_command_list(bias_value):
                # Generate the command list to set the EPB
                command_list = []
                epb_files = self.cpu_file_search.cpu_files['epb_files']
                for i in range(self.cpu_file_search.thread_count):
                    bias_file = epb_files.get(i)
                    if bias_file:
                        command_list.append(f'echo "{bias_value}" | sudo tee {bias_file} > /dev/null')
                return command_list

            def success_callback():
                # Handle successful execution of pkexec command
                self.logger.info(f"Successfully set Intel EPB to {selected_bias}")
                self.epb_dropdown.set_sensitive(True)
                try:
                    self.settings_applier.applied_settings["epb"] = selected_bias
                    self.settings_applier.save_settings()
                except Exception as e:
                    self.logger.error(f"Error saving the applied Intel EPB setting: {e}")

            def failure_callback(error):
                # Handle failures from pkexec command
                if error == 'canceled':
                    self.logger.info("User canceled the Intel EPB change pkexec prompt.")
                    GLib.idle_add(lambda: dropdown.set_selected(0))
                else:
                    self.logger.error(f"Failed to set Intel EPB: {error}")
                self.epb_dropdown.set_sensitive(True)

            selected_bias = get_selected_bias()
            if selected_bias == "Select Energy Performance Bias" or selected_bias is None:
                return  # Do nothing if placeholder or no selection is made

            set_epb_sensitivity()

            bias_value = int(selected_bias.split()[0])
            valid_bias_values = frozenset([0, 4, 6, 8, 15])

            if bias_value in valid_bias_values:
                self.logger.info(f"Setting Intel EPB to: {selected_bias}")
                command_list = get_command_list(bias_value)

                if command_list:
                    # If there are commands to execute, run them with pkexec
                    full_command = ' && '.join(command_list)
                    self.privileged_actions.run_pkexec_command(full_command, success_callback=success_callback, failure_callback=failure_callback)
                else:
                    self.logger.error("No Intel EPB files found to apply the bias value.")
                    self.epb_dropdown.set_sensitive(True)
            else:
                self.logger.error(f"Invalid Intel EPB value selected: {selected_bias}")
                GLib.idle_add(lambda: dropdown.set_selected(0))
                self.epb_dropdown.set_sensitive(True)

        except Exception as e:
            self.epb_dropdown.set_sensitive(True)
            self.logger.error(f"An error occurred while handling Intel EPB change: {e}")
