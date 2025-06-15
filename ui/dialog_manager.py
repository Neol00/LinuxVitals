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

class DialogManager:
    """Manages all dialog creation and display"""
    
    def __init__(self, logger, widget_factory, icon_path=None):
        self.logger = logger
        self.widget_factory = widget_factory
        self.icon_path = icon_path
    
    def show_about_dialog(self, parent_window=None):
        """Show the about dialog with application information"""
        try:
            # Create about window
            about_window = self.widget_factory.create_window("About", parent_window, 350, 205)
            
            def on_destroy(widget):
                about_window.close()
            
            about_window.connect("close-request", on_destroy)
            
            # Create content
            about_box = self.widget_factory.create_box(about_window)
            about_notebook = self.widget_factory.create_notebook(about_box)
            
            # About Tab
            self._create_about_tab(about_notebook)
            
            # Credits Tab
            self._create_credits_tab(about_notebook)
            
            about_window.present()
            
        except Exception as e:
            self.logger.error(f"Error showing about dialog: {e}")
    
    def _create_about_tab(self, notebook):
        """Create the About tab content"""
        try:
            about_tab = self.widget_factory.create_about_tab(notebook, "About")
            about_grid = self.widget_factory.create_grid()
            about_fixed = self.widget_factory.create_fixed()
            about_tab.append(about_grid)
            about_grid.attach(about_fixed, 0, 0, 1, 1)
            
            # Application icon
            if self.icon_path:
                icon = self.widget_factory.create_image(file_path=self.icon_path)
                icon.set_size_request(128, 128)
                about_fixed.put(icon, 0, 10)
            
            # Application info
            self.widget_factory.create_label(
                about_fixed,
                markup="<b>LinuxVitals</b>\n\n"
                       "CPU Monitoring and Control Application for Linux\n\n"
                       "Version 1.0",
                x=120, y=30)
                
        except Exception as e:
            self.logger.error(f"Error creating about tab: {e}")
    
    def _create_credits_tab(self, notebook):
        """Create the Credits tab content"""
        try:
            credits_tab = self.widget_factory.create_about_tab(notebook, "Credits")
            credits_grid = self.widget_factory.create_grid()
            credits_fixed = self.widget_factory.create_fixed()
            credits_tab.append(credits_grid)
            credits_grid.attach(credits_fixed, 0, 0, 1, 1)
            
            # Credits information
            self.widget_factory.create_label(
                credits_fixed,
                markup="Main developer: Noel Ejemyr\n\n"
                       "This application is licensed under the <a href='https://www.gnu.org/licenses/gpl-3.0.html'>GNU General Public License v3</a>.\n\n"
                       "This application uses <a href='https://www.gtk.org/'>GTK</a> for its graphical interface.\n\n"
                       "This application uses <a href='https://github.com/leogx9r/ryzen_smu'>ryzen_smu</a> for controlling Ryzen CPUs.",
                x=10, y=10)
                
        except Exception as e:
            self.logger.error(f"Error creating credits tab: {e}")
    
    def show_more_options_popover(self, parent_button, on_settings_clicked, on_about_clicked):
        """Show the more options popover menu"""
        try:
            more_popover = self.widget_factory.create_popover(position=Gtk.PositionType.TOP)
            more_box = self.widget_factory.create_box(more_popover)
            
            settings_button = self.widget_factory.create_button(
                more_box, "Settings", on_settings_clicked, 
                margin_start=5, margin_end=5, margin_bottom=5)
            
            about_button = self.widget_factory.create_button(
                more_box, "About", on_about_clicked, 
                margin_start=5, margin_end=5)
            
            more_popover.set_parent(parent_button)
            more_popover.popup()
            
        except Exception as e:
            self.logger.error(f"Error showing more options popover: {e}")
    
    def show_error_dialog(self, parent_window, title, message):
        """Show an error dialog"""
        try:
            dialog = self.widget_factory.create_message_dialog(
                transient_for=parent_window,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=title,
                secondary_text=message
            )
            
            def on_response(dialog, response):
                dialog.destroy()
            
            dialog.connect("response", on_response)
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error showing error dialog: {e}")
    
    def show_confirmation_dialog(self, parent_window, title, message, on_confirm):
        """Show a confirmation dialog"""
        try:
            dialog = self.widget_factory.create_message_dialog(
                transient_for=parent_window,
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=title,
                secondary_text=message
            )
            
            def on_response(dialog, response):
                if response == Gtk.ResponseType.YES:
                    on_confirm()
                dialog.destroy()
            
            dialog.connect("response", on_response)
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error showing confirmation dialog: {e}")
    
    def show_mount_properties_dialog(self, parent_window, mount_info):
        """Show mount properties dialog"""
        try:
            dialog = self.widget_factory.create_dialog(title=f"Mount Properties - {mount_info.get('device', 'Unknown')}")
            dialog.set_transient_for(parent_window)
            dialog.set_default_size(400, 300)
            
            content_area = dialog.get_content_area()
            
            # Create property labels
            properties = [
                ("Device", mount_info.get('device', 'N/A')),
                ("Mount Point", mount_info.get('mountpoint', 'N/A')),
                ("Filesystem", mount_info.get('fstype', 'N/A')),
                ("Options", mount_info.get('options', 'N/A')),
                ("Total Size", mount_info.get('total_size', 'N/A')),
                ("Used Space", mount_info.get('used_space', 'N/A')),
                ("Free Space", mount_info.get('free_space', 'N/A')),
                ("Usage", mount_info.get('usage_percent', 'N/A'))
            ]
            
            grid = self.widget_factory.create_grid()
            grid.set_row_spacing(5)
            grid.set_column_spacing(10)
            grid.set_margin_start(10)
            grid.set_margin_end(10)
            grid.set_margin_top(10)
            grid.set_margin_bottom(10)
            
            for i, (label_text, value_text) in enumerate(properties):
                label = self.widget_factory.create_label(None, f"{label_text}:")
                label.set_halign(Gtk.Align.START)
                grid.attach(label, 0, i, 1, 1)
                
                value_label = self.widget_factory.create_label(None, str(value_text))
                value_label.set_halign(Gtk.Align.START)
                value_label.set_selectable(True)
                grid.attach(value_label, 1, i, 1, 1)
            
            content_area.append(grid)
            
            # Add close button
            dialog.add_button("Close", Gtk.ResponseType.CLOSE)
            dialog.connect("response", lambda d, r: d.destroy())
            
            dialog.present()
            
        except Exception as e:
            self.logger.error(f"Error showing mount properties dialog: {e}")