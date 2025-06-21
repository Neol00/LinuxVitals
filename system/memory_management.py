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
from typing import Optional, Dict, List, Tuple, Any
from gi.repository import Gtk, GLib

class MemoryManagerConfig:
    DEFAULT_UPDATE_INTERVAL = 1.0
    BYTES_TO_MB = 1024 * 1024
    BYTES_TO_GB = 1024 * 1024 * 1024
    MEMORY_HISTORY_SIZE = 60
    PERCENTAGE_MULTIPLIER = 100

class MemoryManager:
    def __init__(self, logger, config_manager=None):
        self.logger = logger
        self.config_manager = config_manager
        self.memory_history = [0] * MemoryManagerConfig.MEMORY_HISTORY_SIZE
        self.swap_history = [0] * MemoryManagerConfig.MEMORY_HISTORY_SIZE
        
        # Memory information
        self.total_memory = 0
        self.available_memory = 0
        self.used_memory = 0
        self.memory_percentage = 0
        
        # Swap information
        self.total_swap = 0
        self.used_swap = 0
        self.swap_percentage = 0
        
        # GUI components (will be set by main app)
        self.memory_graph = None
        self.swap_graph = None
        self.memory_usage_label = None
        self.swap_usage_label = None
        self.memory_details_label = None
        self.swap_details_label = None

    def read_memory_info(self) -> Dict[str, int]:
        """Read memory information from /proc/meminfo"""
        try:
            memory_info = {}
            with open('/proc/meminfo', 'r') as file:
                for line in file:
                    if line.startswith('MemTotal:'):
                        memory_info['total'] = int(line.split()[1]) * 1024  # Convert from KB to bytes
                    elif line.startswith('MemAvailable:'):
                        memory_info['available'] = int(line.split()[1]) * 1024
                    elif line.startswith('MemFree:'):
                        memory_info['free'] = int(line.split()[1]) * 1024
                    elif line.startswith('Buffers:'):
                        memory_info['buffers'] = int(line.split()[1]) * 1024
                    elif line.startswith('Cached:'):
                        memory_info['cached'] = int(line.split()[1]) * 1024
                    elif line.startswith('SwapTotal:'):
                        memory_info['swap_total'] = int(line.split()[1]) * 1024
                    elif line.startswith('SwapFree:'):
                        memory_info['swap_free'] = int(line.split()[1]) * 1024
            
            # Calculate used memory
            if 'total' in memory_info and 'available' in memory_info:
                memory_info['used'] = memory_info['total'] - memory_info['available']
            
            # Calculate used swap
            if 'swap_total' in memory_info and 'swap_free' in memory_info:
                memory_info['swap_used'] = memory_info['swap_total'] - memory_info['swap_free']
            
            return memory_info
            
        except Exception as e:
            self.logger.error(f"Error reading memory info: {e}")
            return {}

    def update_memory_info(self):
        """Update memory information and history"""
        try:
            memory_info = self.read_memory_info()
            
            if memory_info:
                # Update memory values
                self.total_memory = memory_info.get('total', 0)
                self.available_memory = memory_info.get('available', 0)
                self.used_memory = memory_info.get('used', 0)
                
                # Calculate memory percentage
                if self.total_memory > 0:
                    self.memory_percentage = (self.used_memory / self.total_memory) * 100
                else:
                    self.memory_percentage = 0
                
                # Update swap values
                self.total_swap = memory_info.get('swap_total', 0)
                self.used_swap = memory_info.get('swap_used', 0)
                
                # Calculate swap percentage
                if self.total_swap > 0:
                    self.swap_percentage = (self.used_swap / self.total_swap) * 100
                else:
                    self.swap_percentage = 0
                
                # Update history
                self.memory_history.pop(0)
                self.memory_history.append(self.memory_percentage / 100)
                
                self.swap_history.pop(0)
                self.swap_history.append(self.swap_percentage / 100)
                
        except Exception as e:
            self.logger.error(f"Error updating memory info: {e}")

    def update_memory_gui(self):
        """Update memory GUI components"""
        try:
            if self.memory_graph:
                self.memory_graph.update(self.memory_percentage / 100)
            
            if self.swap_graph:
                self.swap_graph.update(self.swap_percentage / 100)
            
            if self.memory_usage_label:
                self.memory_usage_label.set_text(f"{self.memory_percentage:.1f}%")
            
            if self.swap_usage_label:
                self.swap_usage_label.set_text(f"{self.swap_percentage:.1f}%")
            
            if self.memory_details_label:
                used_gb = self.used_memory / MemoryManagerConfig.BYTES_TO_GB
                total_gb = self.total_memory / MemoryManagerConfig.BYTES_TO_GB
                available_gb = self.available_memory / MemoryManagerConfig.BYTES_TO_GB
                
                details_text = f"Used: {used_gb:.1f} GB / {total_gb:.1f} GB\nAvailable: {available_gb:.1f} GB"
                self.memory_details_label.set_text(details_text)
            
            # Update separate swap details label
            if self.swap_details_label:
                if self.total_swap > 0:
                    swap_used_gb = self.used_swap / MemoryManagerConfig.BYTES_TO_GB
                    swap_total_gb = self.total_swap / MemoryManagerConfig.BYTES_TO_GB
                    self.swap_details_label.set_text(f"Swap: {swap_used_gb:.1f} GB / {swap_total_gb:.1f} GB")
                else:
                    self.swap_details_label.set_text("Swap: Not available")
                
        except Exception as e:
            self.logger.error(f"Error updating memory GUI: {e}")

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

    def get_memory_summary(self) -> str:
        """Get a summary string of memory usage"""
        try:
            used_gb = self.used_memory / MemoryManagerConfig.BYTES_TO_GB
            total_gb = self.total_memory / MemoryManagerConfig.BYTES_TO_GB
            return f"Memory: {used_gb:.1f} GB / {total_gb:.1f} GB ({self.memory_percentage:.1f}%)"
        except:
            return "Memory: N/A"

class MemoryGraphArea(Gtk.DrawingArea):
    """Memory usage graph widget similar to CPU graph"""
    def __init__(self, graph_type="memory"):
        super().__init__()
        self.graph_type = graph_type
        self.usage_history = [0] * 60  # Store 60 seconds of history
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
            
            # Choose colors based on theme and graph type
            if is_light:  # Light theme
                if self.graph_type == "memory":
                    graph_color = (0.8, 0.2, 0.2)  # Red for memory
                    tint_color = (0.8, 0.2, 0.2, 0.2)
                else:  # swap
                    graph_color = (0.8, 0.6, 0.2)  # Orange for swap
                    tint_color = (0.8, 0.6, 0.2, 0.2)
                outline_color = (0.6, 0.6, 0.6)
            else:  # Dark theme
                if self.graph_type == "memory":
                    graph_color = (1.0, 0.4, 0.4)  # Light red for memory
                    tint_color = (1.0, 0.4, 0.4, 0.2)
                else:  # swap
                    graph_color = (1.0, 0.8, 0.4)  # Light orange for swap
                    tint_color = (1.0, 0.8, 0.4, 0.2)
                outline_color = (0.4, 0.4, 0.4)
                
            return {
                'background': bg_rgb,
                'graph': graph_color,
                'tint': tint_color,
                'outline': outline_color
            }
            
        except Exception:
            # Fallback to default colors
            if self.graph_type == "memory":
                return {
                    'background': (0.188, 0.196, 0.235),
                    'graph': (0.8, 0.2, 0.2),
                    'tint': (0.8, 0.2, 0.2, 0.2),
                    'outline': (0.3, 0.3, 0.3)
                }
            else:
                return {
                    'background': (0.188, 0.196, 0.235),
                    'graph': (0.8, 0.6, 0.2),
                    'tint': (0.8, 0.6, 0.2, 0.2),
                    'outline': (0.3, 0.3, 0.3)
                }

    def update(self, usage):
        self.usage_history.pop(0)
        self.usage_history.append(usage)
        self.queue_draw()

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

        # Draw tint underneath the graph line
        cr.set_source_rgba(*colors['tint'])
        
        cr.move_to(0, height)
        for i, usage in enumerate(self.usage_history):
            x = i * (width / 59)
            y = height - (usage * height)
            cr.line_to(x, y)
        cr.line_to(width, height)
        cr.close_path()
        cr.fill()

        # Draw graph
        cr.set_source_rgb(*colors['graph'])
        cr.set_line_width(1.5)

        cr.move_to(0, height - (self.usage_history[0] * height))
        for i, usage in enumerate(self.usage_history):
            x = i * (width / 59)
            y = height - (usage * height)
            cr.line_to(x, y)
        cr.stroke()