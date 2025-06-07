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
from gi.repository import Gtk, Gdk
import cairo

class CPUGraphArea(Gtk.DrawingArea):
    def __init__(self, cpu_id):
        super().__init__()
        self.cpu_id = cpu_id
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
            
            # Choose colors based on theme
            if is_light:  # Light theme
                graph_color = (0.2, 0.4, 0.8)
                tint_color = (0.2, 0.4, 0.8, 0.2)
                outline_color = (0.6, 0.6, 0.6)
            else:  # Dark theme
                graph_color = (0.4, 0.7, 1.0)
                tint_color = (0.4, 0.7, 1.0, 0.2)
                outline_color = (0.4, 0.4, 0.4)
                
            return {
                'background': bg_rgb,
                'graph': graph_color,
                'tint': tint_color,
                'outline': outline_color
            }
            
        except Exception:
            # Fallback to original colors if theme detection fails
            return {
                'background': (0.188, 0.196, 0.235),
                'graph': (0.322, 0.580, 0.886),
                'tint': (0.2, 0.4, 0.8, 0.2),
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