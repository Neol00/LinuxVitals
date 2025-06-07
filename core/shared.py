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

import subprocess

class GlobalState:
    def __init__(self, config_manager, logger):
        # References to instances
        self.config_manager = config_manager
        self.logger = logger

        # Minimum and maximum scale values for CPU frequency adjustment
        self.SCALE_MIN = int(config_manager.get_setting('Settings', 'clock_scale_minimum', 1))
        self.SCALE_MAX = int(config_manager.get_setting('Settings', 'clock_scale_maximum', 6000))

        # Minimum and maximum scale values for TDP adjustment
        self.TDP_SCALE_MIN = int(config_manager.get_setting('Settings', 'tdp_scale_minimum', 1))
        self.TDP_SCALE_MAX = int(config_manager.get_setting('Settings', 'tdp_scale_maximum', 400))

        # Minimum and maximum scale values for PBO offset adjustment
        self.PBO_SCALE_MIN = int(config_manager.get_setting('Settings', 'pbo_scale_minimum', 0))
        self.PBO_SCALE_MAX = int(config_manager.get_setting('Settings', 'pbo_scale_maximum', 30))

        # Set to hold unique CPU governors
        self.unique_governors = set()

        # State of the CPU boost feature
        self.boost_enabled = None

        # Flags to control the scaling limits and synchronization
        self.disable_scale_limits = False
        self.sync_scales = False

        # Flag to control the MHz to GHz toggle
        self.display_ghz = False

        # Flag to ignore the Apply On Boot checkbutton toggle
        self.ignore_boot_checkbutton_toggle = False

        # Flag to remember the Apply On Boot checkbutton previous toggle
        self.previous_boot_checkbutton_state = False

        # Maximum TDP value
        self.max_tdp_value = None

    def is_ryzen_smu_installed(self):
        # Check if the ryzen_smu module is installed using DKMS
        try:
            result = subprocess.run(["dkms", "status", "ryzen_smu"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return "installed" in result.stdout.decode()
        except FileNotFoundError:
            # dkms command not found, which is expected on non-dkms systems like ARM
            self.logger.info("dkms command not found, assuming ryzen_smu is not installed")
            return False
        except Exception as e:
            self.logger.error(f"Error checking ryzen_smu installation: {e}")
            return False

    def save_settings(self):
        # Save the current settings to the configuration file
        try:
            if not self.config_manager.get_setting('Settings', 'clock_scale_minimum'):
                self.config_manager.set_setting('Settings', 'clock_scale_minimum', str(self.SCALE_MIN))
            if not self.config_manager.get_setting('Settings', 'clock_scale_maximum'):
                self.config_manager.set_setting('Settings', 'clock_scale_maximum', str(self.SCALE_MAX))
            if not self.config_manager.get_setting('Settings', 'tdp_scale_minimum'):
                self.config_manager.set_setting('Settings', 'tdp_scale_minimum', str(self.TDP_SCALE_MIN))
            if not self.config_manager.get_setting('Settings', 'tdp_scale_maximum'):
                self.config_manager.set_setting('Settings', 'tdp_scale_maximum', str(self.TDP_SCALE_MAX))
            if not self.config_manager.get_setting('Settings', 'pbo_scale_minimum'):
                self.config_manager.set_setting('Settings', 'pbo_scale_minimum', str(self.PBO_SCALE_MIN))
            if not self.config_manager.get_setting('Settings', 'pbo_scale_maximum'):
                self.config_manager.set_setting('Settings', 'pbo_scale_maximum', str(self.PBO_SCALE_MAX))
            if not self.config_manager.get_setting('Settings', 'logging_level'):
                self.config_manager.set_setting('Settings', 'logging_level', 'WARNING')

            self.logger.info("Default settings saved successfully.")
        except Exception as e:
            self.logger.error(f"Error saving default settings: {e}")

class GuiComponents:
    def __init__(self, logger):
        # Initialize the logger
        self.logger = logger

        # Dictionary to store GUI components
        self.components = {}

    def add_widget(self, name, widget):
        # Add a widget to the components dictionary
        self.components[name] = widget
        self.logger.info(f"Added widget: {name}")

    def __getitem__(self, key):
        # Retrieve a widget from the components dictionary
        return self.components.get(key)

    def __setitem__(self, key, value):
        # Set a widget in the components dictionary
        self.components[key] = value
        self.logger.info(f"Set widget: {key}")

    def __delitem__(self, key):
        # Delete a widget from the components dictionary
        if key in self.components:
            del self.components[key]
            self.logger.info(f"Deleted widget: {key}")
