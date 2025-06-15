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
import signal
import subprocess
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gdk
from core.config_setup import ConfigManager
from core.log_setup import LogSetup
from core.shared import GlobalState, GuiComponents
from ui.create_widgets import WidgetFactory
from utils.cpu_file_search import CPUFileSearch
from core.privileged_actions import PrivilegedActions
from core.apply_settings import SettingsApplier
from ui.settings_window_setup import SettingsWindow
from system.cpu_management import CPUManager
from system.memory_management import MemoryManager
from system.disk_management import DiskManager
from system.process_management import ProcessManager
from system.mounts_management import MountsManager
from system.services_management import ServicesManager
from core.scale_management import ScaleManager
from ui.css_setup import CssManager
from core.task_scheduler import TaskScheduler
from ui.monitor_tab_setup import MonitorTabManager
from system.hardware_detector import HardwareDetector
from ui.dialog_manager import DialogManager

class LinuxVitalsApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.LinuxVitals")

        # Set up paths
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.icon_path = os.path.join(self.script_dir, "icon", "LinuxVitals-Icon.png")

        # Initialize core components
        self._init_core_components()
        
        # Initialize managers
        self._init_managers()
        
        # Initialize UI components
        self._init_ui_components()
        
        # Detect hardware capabilities
        self.hardware_detector.detect_all_capabilities()
        self.is_tdp_installed()

    def _init_core_components(self):
        """Initialize core application components"""
        self.config_manager = ConfigManager()
        self.log_setup = LogSetup(self.config_manager)
        self.logger = self.log_setup.logger
        self.global_state = GlobalState(self.config_manager, self.logger)
        self.gui_components = GuiComponents(self.logger)
        self.widget_factory = WidgetFactory(self.logger, self.global_state)
        self.cpu_file_search = CPUFileSearch(self.logger)
        self.privileged_actions = PrivilegedActions(self.logger)

    def _init_managers(self):
        """Initialize all management components"""
        self.settings_applier = SettingsApplier(
            self.logger, self.global_state, self.gui_components, self.widget_factory,
            self.cpu_file_search, self.privileged_actions, self.config_manager)
        
        self.cpu_manager = CPUManager(
            self.config_manager, self.logger, self.global_state, self.gui_components,
            self.widget_factory, self.cpu_file_search, self.privileged_actions, self.settings_applier)
        
        self.memory_manager = MemoryManager(self.logger)
        self.disk_manager = DiskManager(self.logger)
        self.process_manager = ProcessManager(self.logger, self.config_manager, self.privileged_actions, self.widget_factory)
        self.process_manager.initialize_cpu_tracking()  # Initialize CPU tracking for accurate percentages
        self.mounts_manager = MountsManager(self.logger, self.widget_factory)
        self.services_manager = ServicesManager(self.logger, self.widget_factory)
        
        self.scale_manager = ScaleManager(
            self.config_manager, self.logger, self.global_state, self.gui_components,
            self.widget_factory, self.cpu_file_search, self.cpu_manager)
        
        self.css_manager = CssManager(self.config_manager, self.logger, self.widget_factory)

    def _init_ui_components(self):
        """Initialize UI-related components"""
        self.settings_window = SettingsWindow(
            self.config_manager, self.logger, self.global_state, self.gui_components,
            self.widget_factory, self.settings_applier, self.cpu_manager, 
            self.scale_manager, self.process_manager, self)

        self.task_scheduler = TaskScheduler(self.logger)
        
        self.hardware_detector = HardwareDetector(self.logger, self.cpu_file_search)
        
        self.dialog_manager = DialogManager(self.logger, self.widget_factory, self.icon_path)
        
        self.monitor_tab_manager = MonitorTabManager(
            self.logger, self.widget_factory, self.cpu_manager,
            self.memory_manager, self.disk_manager)
        
        # Pass monitor tab manager to CPU manager for conditional label creation
        self.cpu_manager.set_monitor_tab_manager(self.monitor_tab_manager)

    def do_activate(self):
        """Application activation - create and show main window"""
        try:
            self.setup_main_window()
            self.create_main_interface()
            self.setup_initial_state()
            self.window.present()
            
            # Start with monitor tab active
            self.on_tab_switch(None, None, 0)
            
        except Exception as e:
            self.logger.error(f"Error during application activation: {e}")

    def setup_main_window(self):
        """Set up the main application window"""
        try:
            self.window = self.widget_factory.create_application_window(application=self)
            self.window.set_title("LinuxVitals")
            
            # Make window reference available to widget factory for dialogs
            self.widget_factory.main_window = self.window
            
            # Apply saved window size if enabled
            self.apply_saved_window_size()
            
            # Set application icon
            if os.path.exists(self.icon_path):
                self.window.set_icon_name("LinuxVitals")
                
            # Connect window size change signal
            self.window.connect("notify::default-width", self.on_window_size_changed)
            self.window.connect("notify::default-height", self.on_window_size_changed)
                
        except Exception as e:
            self.logger.error(f"Error setting up main window: {e}")

    def create_main_interface(self):
        """Create the main application interface"""
        try:
            # Main container
            self.main_box = self.widget_factory.create_vertical_box()
            self.window.set_child(self.main_box)
            
            # Create content area
            self.content_box = self.widget_factory.create_vertical_box(hexpand=True, vexpand=True)
            self.main_box.append(self.content_box)
            
            # Create navigation and content
            self.create_navigation()
            self.create_content_area()
            self.create_menu_button()
            
        except Exception as e:
            self.logger.error(f"Error creating main interface: {e}")

    def create_navigation(self):
        """Create the navigation sidebar"""
        try:
            # Horizontal box for navigation and content
            nav_content_box = self.widget_factory.create_horizontal_box(hexpand=True, vexpand=True)
            self.content_box.append(nav_content_box)
            
            # Navigation sidebar
            nav_frame = self.widget_factory.create_frame()
            nav_frame.set_size_request(200, -1)
            nav_content_box.append(nav_frame)
            
            # Navigation list
            self.navigation_listbox = self.widget_factory.create_listbox()
            self.navigation_listbox.get_style_context().add_class('navigation-sidebar')
            nav_frame.set_child(self.navigation_listbox)
            
            # Tab information
            self.tabs_info = [
                ("Monitor", "computer-symbolic"),
                ("Processes", "applications-system-symbolic"),
                ("Mounts", "drive-harddisk-symbolic"),
                ("Services", "preferences-system-symbolic")
            ]
            
            # Add control tab if hardware supports it
            if self.hardware_detector.show_control_tab:
                self.tabs_info.insert(1, ("Control", "preferences-other-symbolic"))
            
            # Create navigation items
            for tab_name, icon_name in self.tabs_info:
                row = self.widget_factory.create_listbox_row()
                content_box = self.widget_factory.create_horizontal_box(
                    spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
                
                # Add icon
                try:
                    icon = self.widget_factory.create_image(icon_name, icon_size=Gtk.IconSize.NORMAL)
                except:
                    icon = self.widget_factory.create_image("application-default-symbolic", icon_size=Gtk.IconSize.NORMAL)
                content_box.append(icon)
                
                # Add label
                label = self.widget_factory.create_label(content_box, text=tab_name)
                label.set_halign(Gtk.Align.START)
                
                row.set_child(content_box)
                self.navigation_listbox.append(row)
            
            # Set default selection
            self.navigation_listbox.select_row(self.navigation_listbox.get_row_at_index(0))
            self.navigation_listbox.connect("row-selected", self.on_navigation_selected)
            
        except Exception as e:
            self.logger.error(f"Error creating navigation: {e}")

    def create_content_area(self):
        """Create the main content area with stack for different tabs"""
        try:
            # Content stack
            self.content_stack = self.widget_factory.create_stack(hexpand=True, vexpand=True)
            
            # Create scrolled windows for each tab
            self.monitor_scrolled = self.widget_factory.create_scrolled_window(
                policy=(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC),
                hexpand=True, vexpand=True)
            
            self.processes_scrolled = self.widget_factory.create_scrolled_window(
                policy=(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC),
                hexpand=True, vexpand=True)
            
            self.mounts_scrolled = self.widget_factory.create_scrolled_window(
                policy=(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC),
                hexpand=True, vexpand=True)
            
            self.services_scrolled = self.widget_factory.create_scrolled_window(
                policy=(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC),
                hexpand=True, vexpand=True)
            
            # Create content boxes
            self.monitor_box = self.widget_factory.create_vertical_box(
                margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
            self.monitor_scrolled.set_child(self.monitor_box)
            
            # Create grids for other tabs
            self.processes_grid = self.widget_factory.create_grid()
            self.processes_scrolled.set_child(self.processes_grid)
            
            self.mounts_grid = self.widget_factory.create_grid()
            self.mounts_scrolled.set_child(self.mounts_grid)
            
            self.services_grid = self.widget_factory.create_grid()
            self.services_scrolled.set_child(self.services_grid)
            
            # Add to stack
            self.content_stack.add_named(self.monitor_scrolled, "monitor")
            self.content_stack.add_named(self.processes_scrolled, "processes")
            self.content_stack.add_named(self.mounts_scrolled, "mounts")
            self.content_stack.add_named(self.services_scrolled, "services")
            
            # Add control tab if supported
            if self.hardware_detector.show_control_tab:
                self.control_scrolled = self.widget_factory.create_scrolled_window(
                    policy=(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC),
                    hexpand=True, vexpand=True)
                self.control_box = self.widget_factory.create_vertical_box(
                    margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
                self.control_scrolled.set_child(self.control_box)
                self.content_stack.add_named(self.control_scrolled, "control")
            
            # Add stack to main content
            nav_content_box = self.content_box.get_first_child()
            nav_content_box.append(self.content_stack)
            
        except Exception as e:
            self.logger.error(f"Error creating content area: {e}")

    def create_menu_button(self):
        """Create the menu button"""
        try:
            # Header for content area with menu button
            content_header = self.widget_factory.create_horizontal_box(
                margin_start=10, margin_end=10, margin_top=5, margin_bottom=5)
            
            # Spacer to push menu button to the right
            spacer = self.widget_factory.create_horizontal_box(hexpand=True)
            content_header.append(spacer)
            
            # Menu button
            self.more_button = self.widget_factory.create_button(
                content_header, "", self.show_more_options)
            self.more_button.set_icon_name("open-menu-symbolic")
            
            # Insert header at top of content area
            self.content_box.prepend(content_header)
            
        except Exception as e:
            self.logger.error(f"Error creating menu button: {e}")

    def setup_initial_state(self):
        """Set up the initial application state"""
        try:
            # Initialize theme preference from GNOME settings
            self.setup_theme_preference()
            
            # Create widgets for each tab
            self.create_tab_widgets()
            
            # Add widgets to GUI components
            self.add_widgets_to_gui_components()
            
            # Apply CSS styling
            self.css_manager.apply_custom_styles()
            
            # Initialize dark mode checkbutton state to match current theme
            self.settings_window.init_dark_mode_setting()
            
        except Exception as e:
            self.logger.error(f"Error setting up initial state: {e}")
    
    def setup_theme_preference(self):
        """Setup theme preference based on GNOME settings"""
        try:
            self.logger.info("Setting up theme preference...")
            
            # Get the default GTK settings
            settings = Gtk.Settings.get_default()
            if not settings:
                self.logger.error("Failed to get GTK settings")
                return
                
            # Check if we have a user override in config  
            user_preference = self.config_manager.get_setting("UI", "prefer_dark_theme", None)
            
            if user_preference is not None:
                # User has explicitly set a preference, use that
                prefer_dark = user_preference.lower() == 'true'
                self.logger.info(f"Using user theme preference: dark={prefer_dark}")
            else:
                # Try to detect system preference first
                prefer_dark = self._detect_system_theme_preference()
                if prefer_dark is None:
                    # No system preference detected, default to dark theme since user prefers it
                    prefer_dark = True
                    self.logger.info("No system preference detected, defaulting to dark theme")
                else:
                    self.logger.info(f"Detected system theme preference: dark={prefer_dark}")
            
            # Apply the theme preference
            current_value = settings.get_property("gtk-application-prefer-dark-theme")
            self.logger.info(f"Current GTK dark theme setting: {current_value}")
            
            settings.set_property("gtk-application-prefer-dark-theme", prefer_dark)
            
            # Verify the setting was applied
            new_value = settings.get_property("gtk-application-prefer-dark-theme")
            self.logger.info(f"Applied theme preference: dark={prefer_dark}, verified: {new_value}")
            
            # Force a style refresh (GTK4 handles this automatically)
            
        except Exception as e:
            self.logger.error(f"Error setting up theme preference: {e}")
            
    def _detect_system_theme_preference(self):
        """Detect system theme preference using multiple methods"""
        try:
            # Method 1: Try GTK_THEME environment variable
            gtk_theme = os.environ.get('GTK_THEME', '')
            if 'dark' in gtk_theme.lower():
                return True
            elif gtk_theme and 'light' in gtk_theme.lower():
                return False
                
            # Method 2: Try reading gsettings if available
            try:
                import subprocess
                result = subprocess.run(['gsettings', 'get', 'org.gnome.desktop.interface', 'color-scheme'], 
                                      capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    color_scheme = result.stdout.strip().strip("'\"")
                    if 'dark' in color_scheme.lower():
                        return True
                    elif 'light' in color_scheme.lower():
                        return False
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                pass
                
            # Method 3: Check for common dark theme indicators
            theme_indicators = [
                os.environ.get('DESKTOP_SESSION', ''),
                os.environ.get('XDG_CURRENT_DESKTOP', ''),
                os.environ.get('QT_STYLE_OVERRIDE', '')
            ]
            
            for indicator in theme_indicators:
                if indicator and 'dark' in indicator.lower():
                    return True
                    
        except Exception as e:
            self.logger.warning(f"Error detecting system theme: {e}")
            
        return None  # Could not detect

    def apply_saved_window_size(self):
        """Apply saved window size if the feature is enabled"""
        try:
            remember_size = self.config_manager.get_setting("UI", "remember_window_size", "true").lower() == "true"
            
            if remember_size:
                saved_width = int(self.config_manager.get_setting("UI", "window_width", "1200"))
                saved_height = int(self.config_manager.get_setting("UI", "window_height", "700"))
                
                # Ensure reasonable minimum sizes
                width = max(800, saved_width)
                height = max(600, saved_height)
                
                self.window.set_default_size(width, height)
                self.logger.info(f"Applied saved window size: {width}x{height}")
            else:
                # Use default size
                self.window.set_default_size(1200, 700)
                self.logger.info("Using default window size: 1200x700")
                
        except (ValueError, Exception) as e:
            self.logger.warning(f"Error applying saved window size, using defaults: {e}")
            self.window.set_default_size(1200, 700)

    def on_window_size_changed(self, window, param):
        """Handle window size changes and save if enabled"""
        try:
            remember_size = self.config_manager.get_setting("UI", "remember_window_size", "true").lower() == "true"
            
            if remember_size:
                width, height = window.get_default_size()
                if width > 0 and height > 0:
                    self.config_manager.set_setting("UI", "window_width", str(width))
                    self.config_manager.set_setting("UI", "window_height", str(height))
                    self.logger.info(f"Saved window size: {width}x{height}")
                    
        except Exception as e:
            self.logger.warning(f"Error saving window size: {e}")

    def create_tab_widgets(self):
        """Create widgets for all tabs"""
        try:
            # Monitor tab
            self.monitor_tab_manager.create_monitor_widgets(self.monitor_box)
            self.clock_labels = self.monitor_tab_manager.clock_labels
            self.usage_labels = self.monitor_tab_manager.usage_labels
            self.cpu_graphs = self.monitor_tab_manager.cpu_graphs
            self.avg_usage_graph = self.monitor_tab_manager.avg_usage_graph
            self.avg_clock_label = self.monitor_tab_manager.avg_clock_label
            self.avg_usage_label = self.monitor_tab_manager.avg_usage_label
            self.package_temp_label = self.monitor_tab_manager.package_temp_label
            self.current_governor_label = self.monitor_tab_manager.current_governor_label
            self.thermal_throttle_label = self.monitor_tab_manager.thermal_throttle_label
            
            # Processes tab
            self.create_processes_widgets()
            
            # Mounts tab
            self.create_mounts_widgets()
            
            # Services tab
            self.create_services_widgets()
            
            # Control tab (if supported)
            if self.hardware_detector.show_control_tab and hasattr(self, 'control_box'):
                self.create_control_widgets()
                
        except Exception as e:
            self.logger.error(f"Error creating tab widgets: {e}")

    def create_processes_widgets(self):
        """Create widgets for the processes tab"""
        try:
            # Process menu bar (at top)
            self.create_process_menu_bar()
            
            # Process tree view (below menu bar)
            process_tree = self.process_manager.create_process_tree_view()
            if process_tree:
                self.processes_grid.attach(process_tree, 0, 1, 1, 1)
                
        except Exception as e:
            self.logger.error(f"Error creating processes widgets: {e}")

    def create_process_menu_bar(self):
        """Create the process management menu bar"""
        try:
            menu_bar = self.widget_factory.create_horizontal_box(spacing=5, margin_start=5, margin_top=5)
            
            # Process action buttons
            self.end_button = self.widget_factory.create_button(menu_bar, "End", self.end_selected_process)
            self.kill_button = self.widget_factory.create_button(menu_bar, "Kill", self.kill_selected_process)
            self.stop_button = self.widget_factory.create_button(menu_bar, "Stop", self.stop_selected_process)
            self.continue_button = self.widget_factory.create_button(menu_bar, "Continue", self.continue_selected_process)
            self.restart_button = self.widget_factory.create_button(menu_bar, "Restart", self.restart_selected_process)
            self.properties_button = self.widget_factory.create_button(menu_bar, "Properties", self.show_selected_process_properties)
            
            self.processes_grid.attach(menu_bar, 0, 0, 1, 1)
            
        except Exception as e:
            self.logger.error(f"Error creating process menu bar: {e}")

    def create_mounts_widgets(self):
        """Create widgets for the mounts tab"""
        try:
            # Mounts tree view
            mounts_tree = self.mounts_manager.create_mounts_tree_view()
            if mounts_tree:
                self.mounts_grid.attach(mounts_tree, 0, 0, 1, 1)
                
        except Exception as e:
            self.logger.error(f"Error creating mounts widgets: {e}")

    def create_services_widgets(self):
        """Create widgets for the services tab"""
        try:
            # Services tree view
            services_tree = self.services_manager.create_services_tree_view()
            if services_tree:
                self.services_grid.attach(services_tree, 0, 0, 1, 1)
                
                # Services filter controls
                self.create_services_filter_controls()
                
        except Exception as e:
            self.logger.error(f"Error creating services widgets: {e}")

    def create_services_filter_controls(self):
        """Create filter controls for services"""
        try:
            filter_box = self.widget_factory.create_horizontal_box(spacing=10, margin_start=5, margin_top=5)
            
            # Filter checkboxes
            self.systemd_check = self.widget_factory.create_checkbutton(filter_box, "Systemd Services", True)
            self.autostart_check = self.widget_factory.create_checkbutton(filter_box, "Autostart Applications", True)
            self.running_only_check = self.widget_factory.create_checkbutton(filter_box, "Running Only", False)
            
            # Connect signals
            self.systemd_check.connect("toggled", self.on_filter_changed)
            self.autostart_check.connect("toggled", self.on_filter_changed)
            self.running_only_check.connect("toggled", self.on_filter_changed)
            
            self.services_grid.attach(filter_box, 0, 1, 1, 1)
            
        except Exception as e:
            self.logger.error(f"Error creating services filter controls: {e}")

    def create_control_widgets(self):
        """Create widgets for the control tab"""
        try:
            # Create CPU frequency control section
            self.create_frequency_control_section()
            
            # Create CPU governor control section
            self.create_governor_control_section()
            
            # Create CPU boost control section (only if boost is supported)
            if self.cpu_manager.is_boost_supported():
                self.create_boost_control_section()
            
            # Create TDP control section (Intel/AMD)
            self.create_tdp_control_section()
            
            # Create PBO control section (AMD)
            self.create_pbo_control_section()
            
            # Create EPB control section (Intel)
            self.create_epb_control_section()
            
        except Exception as e:
            self.logger.error(f"Error creating control widgets: {e}")

    def create_frequency_control_section(self):
        """Create CPU frequency control widgets using scale manager"""
        try:
            # Frequency control frame
            freq_frame = self.widget_factory.create_frame()
            freq_frame.set_label("CPU Frequency Control")
            self.control_box.append(freq_frame)
            
            freq_box = self.widget_factory.create_vertical_box(margin_start=10, margin_end=10, margin_top=10, margin_bottom=10, spacing=10)
            freq_frame.set_child(freq_box)
            
            # Select all threads control
            select_all_box = self.widget_factory.create_horizontal_box(spacing=10)
            freq_box.append(select_all_box)
            
            self.select_all_threads_checkbutton = self.widget_factory.create_checkbutton(
                select_all_box, "Select All Threads", True, self.on_select_all_threads_toggled)
            
            # Apply button in the same row
            self.apply_max_min_button = self.widget_factory.create_button(
                select_all_box, "Apply Frequency Limits", self.cpu_manager.apply_cpu_clock_speed_limits)
            self.apply_max_min_button.set_hexpand(False)
            
            # Create a flow box for thread controls (similar to monitor tab)
            threads_flow = self.widget_factory.create_flowbox(
                valign=Gtk.Align.START,
                max_children_per_line=3,  # 3 threads per row for better space usage
                min_children_per_line=1,
                row_spacing=10,
                column_spacing=10,
                homogeneous=True,
                selection_mode=Gtk.SelectionMode.NONE)
            freq_box.append(threads_flow)
            
            # Initialize storage
            self.cpu_max_min_checkbuttons = {}
            self.min_scales = {}
            self.max_scales = {}
            self.min_freq_labels = {}  # Store min frequency labels
            self.max_freq_labels = {}  # Store max frequency labels
            
            # Get cached frequency limits from scale manager
            min_freqs, max_freqs = self.scale_manager._cached_freqs or ([1000] * self.cpu_file_search.thread_count, [3000] * self.cpu_file_search.thread_count)
            
            # Create thread control boxes
            for i in range(self.cpu_file_search.thread_count):
                # Create frame for each thread
                thread_frame = self.widget_factory.create_frame()
                thread_frame.set_size_request(200, 180)  # Slightly larger to accommodate labels
                threads_flow.append(thread_frame)
                
                thread_box = self.widget_factory.create_vertical_box(margin_start=8, margin_end=8, margin_top=5, margin_bottom=5, spacing=8)
                thread_frame.set_child(thread_box)
                
                # Thread header with enable checkbox
                header_box = self.widget_factory.create_horizontal_box()
                thread_box.append(header_box)
                
                self.cpu_max_min_checkbuttons[i] = self.widget_factory.create_checkbutton(
                    header_box, f"CPU {i}", True)
                self.cpu_max_min_checkbuttons[i].get_style_context().add_class('small-label')
                
                # Connect signal to sync with "Select All Threads" checkbox
                self.cpu_max_min_checkbuttons[i].connect("toggled", self.on_individual_thread_toggled)
                
                # Get frequency limits for this thread
                min_freq = min_freqs[i] if i < len(min_freqs) else 1000
                max_freq = max_freqs[i] if i < len(max_freqs) else 3000
                
                # Min frequency section
                min_section = self.widget_factory.create_vertical_box(spacing=2)
                thread_box.append(min_section)
                
                min_header = self.widget_factory.create_horizontal_box()
                min_section.append(min_header)
                
                min_title = self.widget_factory.create_label(min_header, "Minimum:")
                min_title.set_halign(Gtk.Align.START)
                min_title.get_style_context().add_class('small-label')
                
                # Spacer to push frequency label to the right
                min_spacer = self.widget_factory.create_horizontal_box(hexpand=True)
                min_header.append(min_spacer)
                
                # Create label with proper MHz/GHz display
                if self.global_state.display_ghz:
                    min_freq_label = self.widget_factory.create_label(min_header, f"{min_freq/1000:.2f} GHz")
                else:
                    min_freq_label = self.widget_factory.create_label(min_header, f"{min_freq:.0f} MHz")
                min_freq_label.set_halign(Gtk.Align.END)
                min_freq_label.get_style_context().add_class('small-label')
                min_freq_label.set_name(f"min_freq_label_{i}")  # Add name for later reference
                self.min_freq_labels[i] = min_freq_label  # Store reference
                
                # Min frequency scale - create without dynamic label
                adjustment = self.widget_factory.create_adjustment(lower=min_freq, upper=max_freq, step_increment=1)
                scale = self.widget_factory.create_scale_widget(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
                scale.set_draw_value(False)
                scale.set_name(f"cpu_min_scale_{i}")
                scale.set_value(min_freq)
                scale.set_size_request(180, 30)  # Compact scale
                scale.connect("value-changed", self.scale_manager.update_min_max_labels)
                min_section.append(scale)
                self.min_scales[i] = scale
                
                # Connect to update frequency label with MHz/GHz support
                def make_min_freq_updater(label, global_state):
                    def update_min_freq_label(scale):
                        value = scale.get_value()
                        if global_state.display_ghz:
                            label.set_text(f"{value/1000:.2f} GHz")
                        else:
                            label.set_text(f"{value:.0f} MHz")
                    return update_min_freq_label
                scale.connect("value-changed", make_min_freq_updater(min_freq_label, self.global_state))
                
                # Add some spacing between min and max sections
                spacer = self.widget_factory.create_vertical_box()
                spacer.set_size_request(-1, 10)  # 10px vertical space
                thread_box.append(spacer)
                
                # Max frequency section
                max_section = self.widget_factory.create_vertical_box(spacing=2)
                thread_box.append(max_section)
                
                max_header = self.widget_factory.create_horizontal_box()
                max_section.append(max_header)
                
                max_title = self.widget_factory.create_label(max_header, "Maximum:")
                max_title.set_halign(Gtk.Align.START)
                max_title.get_style_context().add_class('small-label')
                
                # Spacer to push frequency label to the right
                max_spacer = self.widget_factory.create_horizontal_box(hexpand=True)
                max_header.append(max_spacer)
                
                # Create label with proper MHz/GHz display
                if self.global_state.display_ghz:
                    max_freq_label = self.widget_factory.create_label(max_header, f"{max_freq/1000:.2f} GHz")
                else:
                    max_freq_label = self.widget_factory.create_label(max_header, f"{max_freq:.0f} MHz")
                max_freq_label.set_halign(Gtk.Align.END)
                max_freq_label.get_style_context().add_class('small-label')
                max_freq_label.set_name(f"max_freq_label_{i}")  # Add name for later reference
                self.max_freq_labels[i] = max_freq_label  # Store reference
                
                # Max frequency scale - create without dynamic label
                adjustment = self.widget_factory.create_adjustment(lower=min_freq, upper=max_freq, step_increment=1)
                scale = self.widget_factory.create_scale_widget(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
                scale.set_draw_value(False)
                scale.set_name(f"cpu_max_scale_{i}")
                scale.set_value(max_freq)
                scale.set_size_request(180, 30)  # Compact scale
                scale.connect("value-changed", self.scale_manager.update_min_max_labels)
                max_section.append(scale)
                self.max_scales[i] = scale
                
                # Connect to update frequency label with MHz/GHz support
                def make_max_freq_updater(label, global_state):
                    def update_max_freq_label(scale):
                        value = scale.get_value()
                        if global_state.display_ghz:
                            label.set_text(f"{value/1000:.2f} GHz")
                        else:
                            label.set_text(f"{value:.0f} MHz")
                    return update_max_freq_label
                scale.connect("value-changed", make_max_freq_updater(max_freq_label, self.global_state))
            
        except Exception as e:
            self.logger.error(f"Error creating frequency control section: {e}")

    def on_select_all_threads_toggled(self, checkbutton):
        """Handle select all threads checkbox toggle"""
        try:
            select_all = checkbutton.get_active()
            # Temporarily block individual thread signals to avoid infinite loop
            for i in range(self.cpu_file_search.thread_count):
                if i in self.cpu_max_min_checkbuttons:
                    self.cpu_max_min_checkbuttons[i].handler_block_by_func(self.on_individual_thread_toggled)
                    self.cpu_max_min_checkbuttons[i].set_active(select_all)
                    self.cpu_max_min_checkbuttons[i].handler_unblock_by_func(self.on_individual_thread_toggled)
        except Exception as e:
            self.logger.error(f"Error toggling select all threads: {e}")

    def on_individual_thread_toggled(self, checkbutton):
        """Handle individual thread checkbox toggle - sync with Select All checkbox"""
        try:
            # Check if all individual thread checkboxes are active
            all_active = True
            for i in range(self.cpu_file_search.thread_count):
                if i in self.cpu_max_min_checkbuttons:
                    if not self.cpu_max_min_checkbuttons[i].get_active():
                        all_active = False
                        break
            
            # Update "Select All Threads" checkbox to match
            # Block the signal to avoid infinite loop
            self.select_all_threads_checkbutton.handler_block_by_func(self.on_select_all_threads_toggled)
            self.select_all_threads_checkbutton.set_active(all_active)
            self.select_all_threads_checkbutton.handler_unblock_by_func(self.on_select_all_threads_toggled)
            
        except Exception as e:
            self.logger.error(f"Error syncing individual thread toggle: {e}")

    def create_governor_control_section(self):
        """Create CPU governor control widgets"""
        try:
            # Governor control frame
            gov_frame = self.widget_factory.create_frame()
            gov_frame.set_label("CPU Governor Control")
            self.control_box.append(gov_frame)
            
            gov_box = self.widget_factory.create_vertical_box(margin_start=10, margin_end=10, margin_top=10, margin_bottom=10, spacing=10)
            gov_frame.set_child(gov_box)
            
            # Governor dropdown
            gov_label = self.widget_factory.create_label(gov_box, "Select CPU Governor:")
            
            # Create dropdown with placeholder
            governors_list = ["Select Governor"]
            self.governor_dropdown = self.widget_factory.create_dropdown(gov_box, governors_list, self.cpu_manager.set_cpu_governor)
            
            # Assign dropdown to CPU manager before updating
            self.cpu_manager.governor_dropdown = self.governor_dropdown
            
            # Update with available governors - schedule it to run after the UI is fully created
            GLib.idle_add(self.cpu_manager.update_governor_dropdown)
            
        except Exception as e:
            self.logger.error(f"Error creating governor control section: {e}")

    def create_boost_control_section(self):
        """Create CPU boost control widgets"""
        try:
            # Boost control frame
            boost_frame = self.widget_factory.create_frame()
            boost_frame.set_label("CPU Boost Control")
            self.control_box.append(boost_frame)
            
            boost_box = self.widget_factory.create_vertical_box(margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
            boost_frame.set_child(boost_box)
            
            # Boost checkbox
            self.boost_checkbutton = self.widget_factory.create_checkbutton(boost_box, "Enable CPU Boost", False)
            self.boost_checkbutton.connect("toggled", self.cpu_manager.toggle_boost)
            
        except Exception as e:
            self.logger.error(f"Error creating boost control section: {e}")

    def create_tdp_control_section(self):
        """Create TDP control widgets"""
        try:
            # Check if TDP control is available
            if self.cpu_file_search.cpu_type == "Intel":
                max_tdp = self.cpu_manager.get_allowed_tdp_values()
                if max_tdp:
                    self.create_intel_tdp_widgets(max_tdp)
            elif self.cpu_file_search.cpu_type == "Other" and self.global_state.is_ryzen_smu_installed():
                self.create_amd_tdp_widgets()
                
        except Exception as e:
            self.logger.error(f"Error creating TDP control section: {e}")

    def create_intel_tdp_widgets(self, max_tdp):
        """Create Intel TDP control widgets"""
        try:
            # Intel TDP control frame
            tdp_frame = self.widget_factory.create_frame()
            tdp_frame.set_label("Intel TDP Control")
            self.control_box.append(tdp_frame)
            
            tdp_box = self.widget_factory.create_vertical_box(margin_start=10, margin_end=10, margin_top=10, margin_bottom=10, spacing=10)
            tdp_frame.set_child(tdp_box)
            
            # TDP scale
            tdp_label = self.widget_factory.create_label(tdp_box, f"TDP: {max_tdp:.1f} W")
            self.tdp_scale = self.widget_factory.create_scale(tdp_box, None, 5.0, max_tdp)
            
            # Update label on value change and set initial value
            if self.tdp_scale:
                self.tdp_scale.set_value(max_tdp)
                def update_tdp_label(scale):
                    tdp_label.set_text(f"TDP: {scale.get_value():.1f} W")
                self.tdp_scale.connect("value-changed", update_tdp_label)
            
            # Apply button
            self.apply_tdp_button = self.widget_factory.create_button(tdp_box, "Apply TDP", self.cpu_manager.set_intel_tdp)
            
        except Exception as e:
            self.logger.error(f"Error creating Intel TDP widgets: {e}")

    def create_amd_tdp_widgets(self):
        """Create AMD TDP control widgets"""
        try:
            # AMD TDP control frame
            tdp_frame = self.widget_factory.create_frame()
            tdp_frame.set_label("AMD Ryzen TDP Control")
            self.control_box.append(tdp_frame)
            
            tdp_box = self.widget_factory.create_vertical_box(margin_start=10, margin_end=10, margin_top=10, margin_bottom=10, spacing=10)
            tdp_frame.set_child(tdp_box)
            
            # TDP scale (common range for AMD)
            tdp_label = self.widget_factory.create_label(tdp_box, "TDP: 65.0 W")
            self.tdp_scale = self.widget_factory.create_scale(tdp_box, None, 15.0, 200.0)
            
            # Update label on value change and set initial value
            if self.tdp_scale:
                self.tdp_scale.set_value(65.0)
                def update_tdp_label(scale):
                    tdp_label.set_text(f"TDP: {scale.get_value():.1f} W")
                self.tdp_scale.connect("value-changed", update_tdp_label)
            
            # Apply button
            self.apply_tdp_button = self.widget_factory.create_button(tdp_box, "Apply TDP", self.cpu_manager.set_ryzen_tdp)
            
        except Exception as e:
            self.logger.error(f"Error creating AMD TDP widgets: {e}")

    def create_pbo_control_section(self):
        """Create PBO curve control widgets (AMD only)"""
        try:
            if self.cpu_file_search.cpu_type == "Other" and self.global_state.is_ryzen_smu_installed():
                # PBO control frame
                pbo_frame = self.widget_factory.create_frame()
                pbo_frame.set_label("AMD PBO Curve Optimizer")
                self.control_box.append(pbo_frame)
                
                pbo_box = self.widget_factory.create_vertical_box(margin_start=10, margin_end=10, margin_top=10, margin_bottom=10, spacing=10)
                pbo_frame.set_child(pbo_box)
                
                # PBO curve offset scale
                pbo_label = self.widget_factory.create_label(pbo_box, "Curve Offset: 0")
                self.pbo_curve_scale = self.widget_factory.create_scale(pbo_box, None, -30, 30, Negative=True)
                
                # Update label on value change and set initial value
                if self.pbo_curve_scale:
                    self.pbo_curve_scale.set_value(0)
                    def update_pbo_label(scale):
                        pbo_label.set_text(f"Curve Offset: {int(scale.get_value())}")
                    self.pbo_curve_scale.connect("value-changed", update_pbo_label)
                
                # Apply button
                self.apply_pbo_button = self.widget_factory.create_button(pbo_box, "Apply PBO Offset", self.cpu_manager.set_pbo_curve_offset)
                
        except Exception as e:
            self.logger.error(f"Error creating PBO control section: {e}")

    def create_epb_control_section(self):
        """Create Energy Performance Bias control widgets (Intel only)"""
        try:
            if self.cpu_file_search.cpu_type == "Intel":
                # EPB control frame
                epb_frame = self.widget_factory.create_frame()
                epb_frame.set_label("Intel Energy Performance Bias")
                self.control_box.append(epb_frame)
                
                epb_box = self.widget_factory.create_vertical_box(margin_start=10, margin_end=10, margin_top=10, margin_bottom=10, spacing=10)
                epb_frame.set_child(epb_box)
                
                # EPB dropdown
                epb_label = self.widget_factory.create_label(epb_box, "Select Energy Performance Bias:")
                
                epb_options = [
                    "Select Energy Performance Bias",
                    "0 - Maximum Performance",
                    "4 - Balanced Performance",
                    "6 - Normal",
                    "8 - Balanced Power Save",
                    "15 - Maximum Power Save"
                ]
                
                self.epb_dropdown = self.widget_factory.create_dropdown(epb_box, epb_options, self.cpu_manager.set_energy_perf_bias)
                
        except Exception as e:
            self.logger.error(f"Error creating EPB control section: {e}")

    # Event Handlers
    def on_navigation_selected(self, listbox, row):
        """Handle navigation selection change"""
        try:
            if row is None:
                return
            page_num = row.get_index()
            self.on_tab_switch(None, None, page_num)
        except Exception as e:
            self.logger.error(f"Error handling navigation selection: {e}")

    def on_tab_switch(self, notebook, page, page_num):
        """Handle tab switching and start/stop appropriate tasks"""
        try:
            tab_name = self.tabs_info[page_num][0] if page_num < len(self.tabs_info) else None
            
            # Stop all tasks first
            self.task_scheduler.stop_all_tasks()
            self.cpu_manager.stop_monitor_tasks()
            self.cpu_manager.stop_control_tasks()
            
            # Start appropriate tasks based on selected tab
            if tab_name == "Monitor":
                if self.content_stack and hasattr(self.content_stack, 'set_visible_child_name'):
                    self.content_stack.set_visible_child_name("monitor")
                self.cpu_manager.schedule_monitor_tasks()
                self.schedule_memory_tasks()
                self.schedule_disk_tasks()
                # Immediate update for monitor tab
                self.memory_manager.update_memory_info()
                self.memory_manager.update_memory_gui()
                self.disk_manager.update_disk_stats()
                self.disk_manager.update_disk_gui()
            elif tab_name == "Control":
                if self.content_stack and hasattr(self.content_stack, 'set_visible_child_name'):
                    self.content_stack.set_visible_child_name("control")
                self.cpu_manager.schedule_control_tasks()
            elif tab_name == "Processes":
                if self.content_stack and hasattr(self.content_stack, 'set_visible_child_name'):
                    self.content_stack.set_visible_child_name("processes")
                # Immediate update for processes
                self.process_manager.update_processes()
                self.schedule_process_tasks()
            elif tab_name == "Mounts":
                if self.content_stack and hasattr(self.content_stack, 'set_visible_child_name'):
                    self.content_stack.set_visible_child_name("mounts")
                # Immediate update for mounts
                self.mounts_manager.update_mounts()
                self.schedule_mounts_tasks()
            elif tab_name == "Services":
                if self.content_stack and hasattr(self.content_stack, 'set_visible_child_name'):
                    self.content_stack.set_visible_child_name("services")
                # Immediate update for services
                self.services_manager.update_services()
                self.schedule_services_tasks()
                
        except Exception as e:
            self.logger.error(f"Error switching tabs: {e}")

    # Task Scheduling Methods (using TaskScheduler)
    def schedule_memory_tasks(self):
        """Schedule memory monitoring tasks"""
        def memory_callback():
            self.memory_manager.update_memory_info()
            self.memory_manager.update_memory_gui()
        self.task_scheduler.schedule_task("memory", memory_callback, 1000)

    def schedule_disk_tasks(self):
        """Schedule disk monitoring tasks"""
        def disk_callback():
            self.disk_manager.update_disk_stats()
            self.disk_manager.update_disk_gui()
        self.task_scheduler.schedule_task("disk", disk_callback, 1000)

    def schedule_process_tasks(self):
        """Schedule process monitoring tasks"""
        def process_callback():
            self.process_manager.update_processes()
        self.task_scheduler.schedule_task("process", process_callback, 
                                         self.process_manager.get_update_interval_ms())

    def schedule_mounts_tasks(self):
        """Schedule mounts monitoring tasks"""
        def mounts_callback():
            self.mounts_manager.update_mounts()
        self.task_scheduler.schedule_task("mounts", mounts_callback, 10000)

    def schedule_services_tasks(self):
        """Schedule services monitoring tasks"""
        def services_callback():
            self.services_manager.update_services()
        self.task_scheduler.schedule_task("services", services_callback, 15000)

    # Process Management Event Handlers
    def end_selected_process(self, widget):
        """End the selected process with SIGTERM"""
        selected_pid = self.process_manager.get_selected_process_pid()
        self.process_manager.execute_process_action('end', selected_pid)

    def kill_selected_process(self, widget):
        """Kill the selected process with SIGKILL"""
        selected_pid = self.process_manager.get_selected_process_pid()
        self.process_manager.execute_process_action('kill', selected_pid)

    def stop_selected_process(self, widget):
        """Stop the selected process with SIGSTOP"""
        selected_pid = self.process_manager.get_selected_process_pid()
        self.process_manager.execute_process_action('stop', selected_pid)

    def continue_selected_process(self, widget):
        """Continue the selected process with SIGCONT"""
        selected_pid = self.process_manager.get_selected_process_pid()
        self.process_manager.execute_process_action('continue', selected_pid)

    def restart_selected_process(self, widget):
        """Restart the selected process"""
        selected_pid = self.process_manager.get_selected_process_pid()
        self.process_manager.execute_process_action('restart', selected_pid)

    def show_selected_process_properties(self, widget):
        """Show properties of the selected process"""
        selected_pid = self.process_manager.get_selected_process_pid()
        self.process_manager.execute_process_action('properties', selected_pid)

    # Filter and Menu Event Handlers
    def on_filter_changed(self, widget):
        """Handle services filter changes"""
        try:
            show_systemd = self.systemd_check.get_active()
            show_autostart = self.autostart_check.get_active()
            show_only_running = self.running_only_check.get_active()
            self.services_manager.set_filter_options(show_systemd, show_autostart, show_only_running)
        except Exception as e:
            self.logger.error(f"Error changing filter: {e}")

    def show_more_options(self, widget):
        """Show the more options popover"""
        self.dialog_manager.show_more_options_popover(
            self.more_button,
            self.settings_window.open_settings_window,
            lambda w: self.dialog_manager.show_about_dialog(self.window))

    # Utility Methods
    def add_widgets_to_gui_components(self):
        """Add created widgets to the shared GUI components dictionary"""
        try:
            # Add main components
            self.gui_components.add_widget("main_window", self.window)
            self.gui_components.add_widget("content_stack", self.content_stack)
            
            # Add manager references
            if hasattr(self, 'clock_labels'):
                self.gui_components.add_widget("clock_labels", self.clock_labels)
            if hasattr(self, 'usage_labels'):
                self.gui_components.add_widget("usage_labels", self.usage_labels)
            if hasattr(self, 'cpu_graphs'):
                self.gui_components.add_widget("cpu_graphs", self.cpu_graphs)
            if hasattr(self, 'avg_usage_graph'):
                self.gui_components.add_widget("avg_usage_graph", self.avg_usage_graph)
            if hasattr(self, 'avg_clock_label'):
                self.gui_components.add_widget("avg_clock_label", self.avg_clock_label)
            if hasattr(self, 'avg_usage_label'):
                self.gui_components.add_widget("avg_usage_label", self.avg_usage_label)
            if hasattr(self, 'package_temp_label'):
                self.gui_components.add_widget("package_temp_label", self.package_temp_label)
            if hasattr(self, 'current_governor_label'):
                self.gui_components.add_widget("current_governor_label", self.current_governor_label)
            if hasattr(self, 'thermal_throttle_label'):
                self.gui_components.add_widget("thermal_throttle_label", self.thermal_throttle_label)
            
            # Add control tab widgets if they exist
            if hasattr(self, 'cpu_max_min_checkbuttons'):
                self.gui_components.add_widget("cpu_max_min_checkbuttons", self.cpu_max_min_checkbuttons)
            if hasattr(self, 'min_scales'):
                self.gui_components.add_widget("cpu_min_scales", self.min_scales)
            if hasattr(self, 'max_scales'):
                self.gui_components.add_widget("cpu_max_scales", self.max_scales)
            if hasattr(self, 'apply_max_min_button'):
                self.gui_components.add_widget("apply_max_min_button", self.apply_max_min_button)
            if hasattr(self, 'governor_dropdown'):
                self.gui_components.add_widget("governor_dropdown", self.governor_dropdown)
            if hasattr(self, 'boost_checkbutton'):
                self.gui_components.add_widget("boost_checkbutton", self.boost_checkbutton)
            if hasattr(self, 'tdp_scale'):
                self.gui_components.add_widget("tdp_scale", self.tdp_scale)
            if hasattr(self, 'apply_tdp_button'):
                self.gui_components.add_widget("apply_tdp_button", self.apply_tdp_button)
            if hasattr(self, 'pbo_curve_scale'):
                self.gui_components.add_widget("pbo_curve_scale", self.pbo_curve_scale)
            if hasattr(self, 'apply_pbo_button'):
                self.gui_components.add_widget("apply_pbo_button", self.apply_pbo_button)
            if hasattr(self, 'epb_dropdown'):
                self.gui_components.add_widget("epb_dropdown", self.epb_dropdown)
                
            # Set up CPU manager GUI components now that widgets are added
            self.cpu_manager.setup_gui_components()
            
            # Set up scale manager GUI components if control tab exists
            if hasattr(self, 'min_scales') and hasattr(self, 'max_scales'):
                self.scale_manager.setup_gui_components()
                
        except Exception as e:
            self.logger.error(f"Error adding widgets to GUI components: {e}")

    def is_tdp_installed(self):
        """Check if TDP control is available"""
        try:
            # Check for AMD RyzenAdj
            if self._check_command_available("ryzenadj"):
                self.logger.info("AMD RyzenAdj TDP control detected")
                return True
            
            # Check for Intel undervolt tools
            if self._check_command_available("intel-undervolt"):
                self.logger.info("Intel Undervolt TDP control detected")
                return True
            
            # Check for MSR access (required for most TDP tools)
            if os.path.exists("/dev/cpu/0/msr"):
                self.logger.info("MSR access available for TDP control")
                return True
            
            # Check for RAPL (Running Average Power Limit) interface
            rapl_paths = [
                "/sys/class/powercap/intel-rapl",
                "/sys/devices/virtual/powercap/intel-rapl"
            ]
            
            for rapl_path in rapl_paths:
                if os.path.exists(rapl_path):
                    # Check if we have writeable RAPL controls
                    for item in os.listdir(rapl_path):
                        item_path = os.path.join(rapl_path, item)
                        if os.path.isdir(item_path):
                            power_limit_file = os.path.join(item_path, "constraint_0_power_limit_uw")
                            if os.path.exists(power_limit_file) and os.access(power_limit_file, os.W_OK):
                                self.logger.info("RAPL TDP control interface detected")
                                return True
            
            # Check for AMD P-State driver which supports some TDP features
            amd_pstate_path = "/sys/devices/system/cpu/amd_pstate"
            if os.path.exists(amd_pstate_path):
                self.logger.info("AMD P-State driver detected (limited TDP support)")
                return True
            
            self.logger.info("No TDP control mechanisms detected")
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking TDP availability: {e}")
            return False
    
    def _check_command_available(self, command):
        """Check if a command is available in PATH"""
        try:
            result = subprocess.run(
                ["which", command], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def update_frequency_display_units(self):
        """Update all frequency labels when MHz/GHz preference changes"""
        try:
            # Update min frequency labels
            for i, label in self.min_freq_labels.items():
                if i in self.min_scales:
                    value = self.min_scales[i].get_value()
                    if self.global_state.display_ghz:
                        label.set_text(f"{value/1000:.2f} GHz")
                    else:
                        label.set_text(f"{value:.0f} MHz")
            
            # Update max frequency labels
            for i, label in self.max_freq_labels.items():
                if i in self.max_scales:
                    value = self.max_scales[i].get_value()
                    if self.global_state.display_ghz:
                        label.set_text(f"{value/1000:.2f} GHz")
                    else:
                        label.set_text(f"{value:.0f} MHz")
                        
        except Exception as e:
            self.logger.error(f"Error updating frequency display units: {e}")

def main():
    """Main application entry point"""
    app = LinuxVitalsApp()
    return app.run()

if __name__ == "__main__":
    main()