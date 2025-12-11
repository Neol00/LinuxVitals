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

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

class MonitorTabManager:
    """Manages the monitor tab creation and layout"""
    
    def __init__(self, logger, widget_factory, cpu_manager, memory_manager, disk_manager):
        self.logger = logger
        self.widget_factory = widget_factory
        self.cpu_manager = cpu_manager
        self.memory_manager = memory_manager
        self.disk_manager = disk_manager
        
        # Widget storage
        self.clock_labels = {}
        self.usage_labels = {}
        self.cpu_graphs = {}
        self.avg_usage_graph = None
        self.avg_clock_label = None
        self.avg_usage_label = None
        self.package_temp_label = None
        self.current_governor_label = None
        self.thermal_throttle_label = None
        
    def create_monitor_widgets(self, monitor_box):
        """Create all widgets for the monitor tab"""
        try:
            # Get CPU information
            cpu_info = self.cpu_manager.get_cpu_info()

            # CPU Model Name at the top
            if "Model Name" in cpu_info:
                model_name = cpu_info["Model Name"]
                model_label = self.widget_factory.create_label(
                    monitor_box, text=model_name)
                model_label.set_justify(Gtk.Justification.CENTER)
                model_label.set_wrap(True)
                model_label.set_halign(Gtk.Align.CENTER)
                model_label.add_css_class('medium-label')
                model_label.set_margin_bottom(10)

            # Create CPU graphs section
            self._create_cpu_graphs_section(monitor_box, cpu_info)
            
            # Create system info section
            self._create_system_info_section(monitor_box, cpu_info)
            
            # Create memory graphs section
            self._create_memory_graphs_section(monitor_box)
            
            # Create disk graphs section
            self._create_disk_graphs_section(monitor_box)
            
        except Exception as e:
            self.logger.error(f"Error creating monitor widgets: {e}")
    
    def _create_cpu_graphs_section(self, monitor_box, cpu_info):
        """Create the CPU graphs flow box section"""
        try:
            # Create a flow box for CPU graphs that will wrap based on available space
            cpu_graphs_flow = self.widget_factory.create_flowbox(
                valign=Gtk.Align.START,
                max_children_per_line=10,
                min_children_per_line=2,
                row_spacing=10,
                column_spacing=10,
                homogeneous=True,
                selection_mode=Gtk.SelectionMode.NONE)
            monitor_box.append(cpu_graphs_flow)

            # Create individual CPU graphs - one per thread
            threads = cpu_info.get("Virtual Cores (Threads)", cpu_info.get("Threads", self.cpu_manager.cpu_file_search.thread_count))
            
            # Create graphs for each thread
            for i in range(threads):
                # Create frame for CPU graph
                cpu_frame = self.widget_factory.create_frame()
                cpu_frame.set_size_request(120, 90)
                cpu_graphs_flow.append(cpu_frame)
                
                # Create overlay for positioning labels over the graph
                cpu_overlay = self.widget_factory.create_overlay()
                cpu_frame.set_child(cpu_overlay)
                
                # Create CPU graph area
                from widgets.cpu_graph_area import CPUGraphArea
                cpu_graph = CPUGraphArea(i)
                cpu_graph.set_content_width(100)
                cpu_graph.set_content_height(80)
                cpu_overlay.set_child(cpu_graph)
                self.cpu_graphs[i] = cpu_graph  # Use integer index like original
                
                # Create labels box positioned over the graph
                cpu_labels_box = self.widget_factory.create_vertical_box()
                cpu_labels_box.set_valign(Gtk.Align.FILL)
                cpu_labels_box.set_halign(Gtk.Align.FILL)
                
                # Top row for thread label
                top_row = self.widget_factory.create_horizontal_box(
                    margin_start=5, margin_end=5, margin_top=5)
                
                thread_label = self.widget_factory.create_label(top_row, text=f"CPU {i}")
                thread_label.set_halign(Gtk.Align.START)
                thread_label.add_css_class('small-label')
                
                cpu_labels_box.append(top_row)
                
                # Center spacer
                center_spacer = self.widget_factory.create_vertical_box(vexpand=True)
                cpu_labels_box.append(center_spacer)
                
                # Bottom row for usage and clock labels (positioned left and right)
                bottom_row = self.widget_factory.create_horizontal_box(
                    margin_start=5, margin_end=5, margin_bottom=5)
                
                # Clock frequency label (left side)
                clock_label = self.widget_factory.create_label(bottom_row, text="0 MHz")
                clock_label.set_halign(Gtk.Align.START)
                clock_label.add_css_class('small-label')
                self.clock_labels[i] = clock_label  # Use integer index
                
                # Spacer to push usage label to the right
                spacer = self.widget_factory.create_horizontal_box(hexpand=True)
                bottom_row.append(spacer)
                
                # Usage percentage label (right side)
                usage_label = self.widget_factory.create_label(bottom_row, text="0%")
                usage_label.set_halign(Gtk.Align.END)
                usage_label.add_css_class('medium-header')
                self.usage_labels[i] = usage_label  # Use integer index
                
                cpu_labels_box.append(bottom_row)
                
                # Add labels overlay to graph
                cpu_overlay.add_overlay(cpu_labels_box)
            
            # Create average CPU graph (separate from thread graphs, spans full width)
            avg_cpu_frame = self.widget_factory.create_frame()
            avg_cpu_frame.set_size_request(400, 120)
            monitor_box.append(avg_cpu_frame)
            
            # Create overlay for average graph
            avg_cpu_overlay = self.widget_factory.create_overlay()
            avg_cpu_frame.set_child(avg_cpu_overlay)
            
            # Average CPU graph area
            avg_cpu_graph = CPUGraphArea("avg")
            avg_cpu_graph.set_content_width(400)
            avg_cpu_graph.set_content_height(120)
            avg_cpu_overlay.set_child(avg_cpu_graph)
            self.avg_usage_graph = avg_cpu_graph
            
            # Create labels box for average graph
            avg_labels_box = self.widget_factory.create_vertical_box()
            avg_labels_box.set_valign(Gtk.Align.FILL)
            avg_labels_box.set_halign(Gtk.Align.FILL)
            
            # Top row for average label
            avg_top_row = self.widget_factory.create_horizontal_box(
                margin_start=5, margin_end=5, margin_top=5)
            
            avg_label = self.widget_factory.create_label(avg_top_row, text="Average")
            avg_label.set_halign(Gtk.Align.START)
            avg_label.add_css_class('small-label')
            
            avg_labels_box.append(avg_top_row)
            
            # Center spacer for average
            avg_center_spacer = self.widget_factory.create_vertical_box(vexpand=True)
            avg_labels_box.append(avg_center_spacer)
            
            # Bottom row for average usage and clock labels (positioned left and right)
            avg_bottom_row = self.widget_factory.create_horizontal_box(
                margin_start=5, margin_end=5, margin_bottom=5)
            
            # Average clock frequency label (left side)
            avg_clock_label = self.widget_factory.create_label(avg_bottom_row, text="0 MHz")
            avg_clock_label.set_halign(Gtk.Align.START)
            avg_clock_label.add_css_class('small-label')
            self.avg_clock_label = avg_clock_label
            
            # Spacer to push usage label to the right
            avg_spacer = self.widget_factory.create_horizontal_box(hexpand=True)
            avg_bottom_row.append(avg_spacer)
            
            # Average usage percentage label (right side)
            avg_usage_label = self.widget_factory.create_label(avg_bottom_row, text="0%")
            avg_usage_label.set_halign(Gtk.Align.END)
            avg_usage_label.add_css_class('medium-header')
            self.avg_usage_label = avg_usage_label
            
            avg_labels_box.append(avg_bottom_row)
            
            # Add labels overlay to average graph
            avg_cpu_overlay.add_overlay(avg_labels_box)
                
        except Exception as e:
            self.logger.error(f"Error creating CPU graphs section: {e}")
    
    def _create_system_info_section(self, monitor_box, cpu_info):
        """Create the system information section"""
        try:
            # CPU Info Grid
            cpu_info_frame = self.widget_factory.create_frame()
            cpu_info_frame.set_label("CPU Information")
            monitor_box.append(cpu_info_frame)
            cpu_info_grid = self.widget_factory.create_grid()
            cpu_info_frame.set_child(cpu_info_grid)

            row = 0
            info_items = [
                ("Architecture", cpu_info.get("Architecture")),
                ("Physical Cores", cpu_info.get("Physical Cores")),
                ("Threads", cpu_info.get("Virtual Cores (Threads)")),
                ("Base Clock", cpu_info.get("Base Clock")),
                ("Max Clock", cpu_info.get("Max Clock")),
                ("Cache Size", cpu_info.get("Cache Size")),
                ("Vendor", cpu_info.get("Vendor"))
            ]

            for label_text, value in info_items:
                # Only show items that have valid data (not None, "Unknown", "N/A", or empty)
                if value and value not in ["Unknown", "N/A", "", "0"]:
                    # Convert to string if it's a number
                    value_text = str(value) if not isinstance(value, str) else value
                    
                    label = self.widget_factory.create_label(
                        cpu_info_grid, text=f"{label_text}:", x=0, y=row)
                    label.set_halign(Gtk.Align.START)
                    label.add_css_class('small-label')

                    value_label = self.widget_factory.create_label(
                        cpu_info_grid, text=value_text, x=1, y=row)
                    value_label.set_halign(Gtk.Align.START)
                    value_label.add_css_class('small-label')
                    row += 1
            
            # Initialize dynamic label references (will be created conditionally)
            self.package_temp_label = None
            self.current_governor_label = None
            self.thermal_throttle_label = None
            
            # Store grid and row info for dynamic updates
            self.cpu_info_grid = cpu_info_grid
            self.current_grid_row = row
                
        except Exception as e:
            self.logger.error(f"Error creating system info section: {e}")
    
    def create_temp_label_if_needed(self, temp_value):
        """Create temperature label only if temp value is valid"""
        if temp_value and temp_value not in ["N/A", "Unknown", "", "0°C", "0"]:
            if not self.package_temp_label:
                temp_label = self.widget_factory.create_label(
                    self.cpu_info_grid, text="Temperature:", x=0, y=self.current_grid_row)
                temp_label.set_halign(Gtk.Align.START)
                temp_label.add_css_class('small-label')
                
                self.package_temp_label = self.widget_factory.create_label(
                    self.cpu_info_grid, text=temp_value, x=1, y=self.current_grid_row)
                self.package_temp_label.set_halign(Gtk.Align.START)
                self.package_temp_label.add_css_class('small-label')
                self.current_grid_row += 1
            else:
                self.package_temp_label.set_text(temp_value)
        elif self.package_temp_label:
            # Hide if temp becomes invalid
            self.package_temp_label.set_visible(False)
    
    def create_governor_label_if_needed(self, governor_value):
        """Create governor label only if governor value is valid"""
        if governor_value and governor_value not in ["Unknown", "N/A", "", "none"]:
            if not self.current_governor_label:
                governor_label = self.widget_factory.create_label(
                    self.cpu_info_grid, text="Governor:", x=0, y=self.current_grid_row)
                governor_label.set_halign(Gtk.Align.START)
                governor_label.add_css_class('small-label')
                
                self.current_governor_label = self.widget_factory.create_label(
                    self.cpu_info_grid, text=governor_value, x=1, y=self.current_grid_row)
                self.current_governor_label.set_halign(Gtk.Align.START)
                self.current_governor_label.add_css_class('small-label')
                self.current_grid_row += 1
            else:
                self.current_governor_label.set_text(governor_value)
                self.current_governor_label.set_visible(True)
        elif self.current_governor_label:
            # Hide if governor becomes invalid
            self.current_governor_label.set_visible(False)
    
    def create_thermal_status_label_if_needed(self, is_throttling):
        """Create thermal status label only if there's actual throttling"""
        if is_throttling:
            if not self.thermal_throttle_label:
                throttle_label = self.widget_factory.create_label(
                    self.cpu_info_grid, text="Thermal Status:", x=0, y=self.current_grid_row)
                throttle_label.set_halign(Gtk.Align.START)
                throttle_label.add_css_class('small-label')
                
                self.thermal_throttle_label = self.widget_factory.create_label(
                    self.cpu_info_grid, text="Throttling", x=1, y=self.current_grid_row)
                self.thermal_throttle_label.set_halign(Gtk.Align.START)
                self.thermal_throttle_label.add_css_class('small-label')
                self.thermal_throttle_label.set_markup('<span foreground="red">Throttling</span>')
                self.current_grid_row += 1
            else:
                self.thermal_throttle_label.set_markup('<span foreground="red">Throttling</span>')
                self.thermal_throttle_label.set_visible(True)
        elif self.thermal_throttle_label:
            # Hide when not throttling
            self.thermal_throttle_label.set_visible(False)
    
    def _create_memory_graphs_section(self, monitor_box):
        """Create the memory monitoring section"""
        try:
            # Memory section header
            memory_header = self.widget_factory.create_label(monitor_box, text="System Memory")
            memory_header.add_css_class('medium-header')
            memory_header.set_margin_top(20)
            memory_header.set_margin_bottom(10)
            memory_header.set_halign(Gtk.Align.START)
            
            # Create a box for memory graphs that can stack responsively
            memory_graphs_box = self.widget_factory.create_horizontal_box(spacing=20, homogeneous=False)
            monitor_box.append(memory_graphs_box)

            # Memory usage graph
            memory_frame = self.widget_factory.create_frame()
            memory_frame.set_size_request(280, 120)
            memory_frame.set_hexpand(True)  # Allow expansion when swap is hidden
            memory_graphs_box.append(memory_frame)
            
            # Create overlay for memory graph
            memory_overlay = self.widget_factory.create_overlay()
            memory_frame.set_child(memory_overlay)
            
            # Create memory graph
            from system.memory_management import MemoryGraphArea
            memory_graph = MemoryGraphArea("memory")
            memory_graph.set_content_width(280)
            memory_graph.set_content_height(120)
            memory_overlay.set_child(memory_graph)
            
            # Store reference for updates
            self.memory_manager.memory_graph = memory_graph
            
            # Memory labels overlay
            memory_labels_box = self.widget_factory.create_vertical_box()
            memory_labels_box.set_valign(Gtk.Align.FILL)
            memory_labels_box.set_halign(Gtk.Align.FILL)
            
            # Top row for memory
            memory_top_row = self.widget_factory.create_horizontal_box(
                margin_start=5, margin_end=5, margin_top=5)
            
            memory_header = self.widget_factory.create_label(memory_top_row, text="Memory")
            memory_header.set_halign(Gtk.Align.START)
            memory_header.add_css_class('medium-header')
            
            memory_spacer = self.widget_factory.create_horizontal_box(hexpand=True)
            memory_top_row.append(memory_spacer)
            
            memory_usage_label = self.widget_factory.create_label(memory_top_row, text="0.0%")
            memory_usage_label.set_halign(Gtk.Align.END)
            memory_usage_label.add_css_class('thick-header')
            self.memory_manager.memory_usage_label = memory_usage_label
            
            memory_labels_box.append(memory_top_row)
            
            # Bottom spacer for memory
            memory_bottom_spacer = self.widget_factory.create_vertical_box(vexpand=True)
            memory_labels_box.append(memory_bottom_spacer)
            
            # Bottom row for memory details
            memory_bottom_row = self.widget_factory.create_horizontal_box(
                margin_start=5, margin_bottom=5)
            
            memory_details_label = self.widget_factory.create_label(memory_bottom_row, text="Memory: 0.0 GB / 0.0 GB")
            memory_details_label.set_halign(Gtk.Align.START)
            memory_details_label.add_css_class('medium-label')
            self.memory_manager.memory_details_label = memory_details_label
            
            memory_labels_box.append(memory_bottom_row)
            memory_overlay.add_overlay(memory_labels_box)
            
            # Swap usage graph
            swap_frame = self.widget_factory.create_frame()
            swap_frame.set_size_request(280, 120)
            memory_graphs_box.append(swap_frame)

            # Create overlay for swap graph
            swap_overlay = self.widget_factory.create_overlay()
            swap_frame.set_child(swap_overlay)

            # Create swap graph
            swap_graph = MemoryGraphArea("swap")
            swap_graph.set_content_width(280)
            swap_graph.set_content_height(120)
            swap_overlay.set_child(swap_graph)

            # Store references for updates
            self.memory_manager.swap_graph = swap_graph
            self.memory_manager.swap_frame = swap_frame  # Store frame reference for hiding/showing
            
            # Swap labels overlay
            swap_labels_box = self.widget_factory.create_vertical_box()
            swap_labels_box.set_valign(Gtk.Align.FILL)
            swap_labels_box.set_halign(Gtk.Align.FILL)
            
            # Top row for swap
            swap_top_row = self.widget_factory.create_horizontal_box(
                margin_start=5, margin_end=5, margin_top=5)
            
            swap_header = self.widget_factory.create_label(swap_top_row, text="Swap")
            swap_header.set_halign(Gtk.Align.START)
            swap_header.add_css_class('medium-header')
            
            swap_spacer = self.widget_factory.create_horizontal_box(hexpand=True)
            swap_top_row.append(swap_spacer)
            
            swap_usage_label = self.widget_factory.create_label(swap_top_row, text="0.0%")
            swap_usage_label.set_halign(Gtk.Align.END)
            swap_usage_label.add_css_class('thick-header')
            self.memory_manager.swap_usage_label = swap_usage_label
            
            swap_labels_box.append(swap_top_row)
            
            # Bottom spacer for swap
            swap_bottom_spacer = self.widget_factory.create_vertical_box(vexpand=True)
            swap_labels_box.append(swap_bottom_spacer)
            
            # Bottom row for swap details
            swap_bottom_row = self.widget_factory.create_horizontal_box(
                margin_start=5, margin_bottom=5)
            
            swap_details_label = self.widget_factory.create_label(swap_bottom_row, text="Swap: 0.0 GB / 0.0 GB")
            swap_details_label.set_halign(Gtk.Align.START)
            swap_details_label.add_css_class('medium-label')
            self.memory_manager.swap_details_label = swap_details_label
            
            swap_labels_box.append(swap_bottom_row)
            swap_overlay.add_overlay(swap_labels_box)
                
        except Exception as e:
            self.logger.error(f"Error creating memory graphs section: {e}")
    
    def _create_disk_graphs_section(self, monitor_box):
        """Create the disk monitoring section with individual graphs per disk"""
        try:
            # Disk section header  
            disk_header = self.widget_factory.create_label(monitor_box, text="Disk Usage")
            disk_header.add_css_class('medium-header')
            disk_header.set_margin_top(20)
            disk_header.set_margin_bottom(10)
            disk_header.set_halign(Gtk.Align.START)
            
            # Initialize disk manager's graph storage if not already done
            if not hasattr(self.disk_manager, 'disk_graphs'):
                self.disk_manager.disk_graphs = {}
            if not hasattr(self.disk_manager, 'disk_usage_labels'):
                self.disk_manager.disk_usage_labels = {}
            if not hasattr(self.disk_manager, 'disk_details_labels'):
                self.disk_manager.disk_details_labels = {}
            
            # Discover disks first to know what we're working with
            self.disk_manager.discover_disks()
            
            self.logger.info(f"Creating disk graphs for {len(self.disk_manager.disks)} discovered disks: {list(self.disk_manager.disks.keys())}")
            
            # Create a graph for each discovered disk
            for device_name, disk_info in self.disk_manager.disks.items():
                self.logger.info(f"Creating disk graph for {device_name}")
                self._create_single_disk_graph(monitor_box, device_name, disk_info)
                
        except Exception as e:
            self.logger.error(f"Error creating disk graphs section: {e}")
    
    def _create_single_disk_graph(self, monitor_box, device_name, disk_info):
        """Create a single disk graph for the specified device"""
        try:
            from system.disk_management import DiskGraphArea
            
            # Create disk graph frame
            disk_frame = self.widget_factory.create_frame()
            disk_frame.set_size_request(400, 120)
            monitor_box.append(disk_frame)
            
            # Create overlay for disk graph
            disk_overlay = self.widget_factory.create_overlay()
            disk_frame.set_child(disk_overlay)
            
            # Create disk graph area
            disk_graph = DiskGraphArea(disk_info)
            disk_graph.set_content_width(400)
            disk_graph.set_content_height(120)
            disk_overlay.set_child(disk_graph)
            
            # Store reference for updates
            self.disk_manager.disk_graphs[device_name] = disk_graph
            
            # Disk labels overlay
            disk_labels_box = self.widget_factory.create_vertical_box()
            disk_labels_box.set_valign(Gtk.Align.FILL)
            disk_labels_box.set_halign(Gtk.Align.FILL)
            
            # Top row for disk
            disk_top_row = self.widget_factory.create_horizontal_box(
                margin_start=5, margin_end=5, margin_top=5)
            
            # Display device name and model
            disk_title = f"{device_name} ({disk_info.model})"
            if len(disk_title) > 40:  # Truncate if too long
                disk_title = disk_title[:37] + "..."
            
            disk_header = self.widget_factory.create_label(disk_top_row, text=disk_title)
            disk_header.set_halign(Gtk.Align.START)
            disk_header.add_css_class('medium-header')
            
            disk_spacer = self.widget_factory.create_horizontal_box(hexpand=True)
            disk_top_row.append(disk_spacer)
            
            disk_usage_label = self.widget_factory.create_label(disk_top_row, text="0 B/s")
            disk_usage_label.set_halign(Gtk.Align.END)
            disk_usage_label.add_css_class('thick-header')

            disk_labels_box.append(disk_top_row)

            # Bottom spacer for disk
            disk_bottom_spacer = self.widget_factory.create_vertical_box(vexpand=True)
            disk_labels_box.append(disk_bottom_spacer)

            # Bottom row for disk details
            disk_bottom_row = self.widget_factory.create_horizontal_box(
                margin_start=5, margin_bottom=5)

            disk_details_label = self.widget_factory.create_label(disk_bottom_row, text=f"Size: {disk_info.size} | Read: 0 B/s | Write: 0 B/s")
            disk_details_label.set_halign(Gtk.Align.START)
            disk_details_label.add_css_class('medium-label')
            
            # Store references for updates
            self.disk_manager.disk_usage_labels[device_name] = disk_usage_label
            self.disk_manager.disk_details_labels[device_name] = disk_details_label
            
            disk_labels_box.append(disk_bottom_row)
            disk_overlay.add_overlay(disk_labels_box)
                
        except Exception as e:
            self.logger.error(f"Error creating disk graph for {device_name}: {e}")