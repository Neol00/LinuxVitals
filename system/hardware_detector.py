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
import platform

class HardwareDetector:
    """Detects hardware capabilities and system configuration"""
    
    def __init__(self, logger, cpu_file_search=None):
        self.logger = logger
        self.cpu_file_search = cpu_file_search
        
        # Hardware capability flags
        self.is_wsl = False
        self.is_arm64 = False
        self.has_clock_speeds = False
        self.has_temperature = False
        self.show_control_tab = False
        
    def detect_all_capabilities(self):
        """Detect all hardware capabilities"""
        try:
            self.is_wsl = self._detect_wsl()
            self.is_arm64 = self._detect_arm64()
            self.has_clock_speeds = self._has_clock_speed_monitoring()
            self.has_temperature = self._has_temperature_monitoring()
            self.show_control_tab = self._should_show_control_tab()
            
            self.logger.info(f"Hardware detection complete: WSL={self.is_wsl}, ARM64={self.is_arm64}, "
                           f"LinuxVitals={self.has_clock_speeds}, Temp={self.has_temperature}, "
                           f"Control={self.show_control_tab}")
            
        except Exception as e:
            self.logger.error(f"Error during hardware detection: {e}")
    
    def _detect_wsl(self) -> bool:
        """Detect if running in Windows Subsystem for Linux"""
        try:
            # Check for WSL-specific environment variables
            if os.environ.get('WSL_DISTRO_NAME') or os.environ.get('WSL_INTEROP'):
                return True
            
            # Check /proc/version for WSL signature
            try:
                with open('/proc/version', 'r') as f:
                    version_info = f.read().lower()
                    return 'microsoft' in version_info or 'wsl' in version_info
            except:
                pass
            
            # Check for WSL-specific files
            wsl_files = ['/proc/sys/fs/binfmt_misc/WSLInterop', '/run/WSL']
            for wsl_file in wsl_files:
                if os.path.exists(wsl_file):
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error detecting WSL: {e}")
            return False
    
    def _detect_arm64(self) -> bool:
        """Detect ARM64 architecture"""
        try:
            machine = platform.machine().lower()
            return machine in ['aarch64', 'arm64']
        except Exception as e:
            self.logger.error(f"Error detecting ARM64: {e}")
            return False
    
    def _has_cpu_frequency_control(self) -> bool:
        """Check if CPU frequency control is available"""
        try:
            if not self.cpu_file_search:
                return False
            
            # Check for cpufreq scaling files
            scaling_files = [
                '/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor',
                '/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq',
                '/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq'
            ]
            
            return all(os.path.exists(f) for f in scaling_files)
            
        except Exception as e:
            self.logger.error(f"Error checking CPU frequency control: {e}")
            return False
    
    def _has_clock_speed_monitoring(self) -> bool:
        """Check if CPU clock speed monitoring is available"""
        try:
            if self.is_wsl:
                # WSL typically doesn't support real-time frequency monitoring
                return False
            
            # Check for cpuinfo_cur_freq or scaling_cur_freq
            freq_files = [
                '/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_cur_freq',
                '/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq'
            ]
            
            for freq_file in freq_files:
                if os.path.exists(freq_file):
                    try:
                        with open(freq_file, 'r') as f:
                            freq = f.read().strip()
                            if freq.isdigit() and int(freq) > 0:
                                return True
                    except:
                        continue
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking clock speed monitoring: {e}")
            return False
    
    def _has_temperature_monitoring(self) -> bool:
        """Check if temperature monitoring is available"""
        try:
            if self.is_wsl:
                # WSL typically doesn't support temperature monitoring
                return False
            
            # Check for thermal zone files
            thermal_dirs = ['/sys/class/thermal', '/sys/devices/platform']
            
            for thermal_dir in thermal_dirs:
                if not os.path.exists(thermal_dir):
                    continue
                
                try:
                    for item in os.listdir(thermal_dir):
                        item_path = os.path.join(thermal_dir, item)
                        
                        # Check for thermal zone directories
                        if item.startswith('thermal_zone') and os.path.isdir(item_path):
                            temp_file = os.path.join(item_path, 'temp')
                            if os.path.exists(temp_file):
                                try:
                                    with open(temp_file, 'r') as f:
                                        temp = f.read().strip()
                                        if temp.isdigit() and int(temp) > 0:
                                            return True
                                except:
                                    continue
                        
                        # Check for coretemp modules (Intel)
                        if 'coretemp' in item and os.path.isdir(item_path):
                            for subitem in os.listdir(item_path):
                                if subitem.startswith('temp') and subitem.endswith('_input'):
                                    temp_file = os.path.join(item_path, subitem)
                                    if os.path.exists(temp_file):
                                        return True
                        
                        # Check for k10temp modules (AMD)
                        if 'k10temp' in item and os.path.isdir(item_path):
                            temp_file = os.path.join(item_path, 'temp1_input')
                            if os.path.exists(temp_file):
                                return True
                                
                except PermissionError:
                    continue
                except Exception as e:
                    self.logger.info(f"Error checking thermal directory {thermal_dir}: {e}")
                    continue
            
            # Check for CPU temperature in hwmon
            hwmon_dir = '/sys/class/hwmon'
            if os.path.exists(hwmon_dir):
                try:
                    for hwmon_item in os.listdir(hwmon_dir):
                        hwmon_path = os.path.join(hwmon_dir, hwmon_item)
                        if os.path.isdir(hwmon_path):
                            # Check for CPU temperature sensors
                            for temp_file in ['temp1_input', 'temp2_input', 'temp3_input']:
                                temp_path = os.path.join(hwmon_path, temp_file)
                                if os.path.exists(temp_path):
                                    return True
                except:
                    pass
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking temperature monitoring: {e}")
            return False
    
    def _should_show_control_tab(self) -> bool:
        """Determine if the control tab should be shown"""
        try:
            # Don't show control tab in WSL (limited hardware access)
            if self.is_wsl:
                return False
            
            # Check for basic CPU frequency control capabilities
            has_freq_control = self._has_cpu_frequency_control()
            
            # Check for governor control
            governor_file = '/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'
            has_governor_control = os.path.exists(governor_file)
            
            # Check for boost control
            boost_files = [
                '/sys/devices/system/cpu/cpufreq/boost',
                '/sys/devices/system/cpu/intel_pstate/no_turbo'
            ]
            has_boost_control = any(os.path.exists(f) for f in boost_files)
            
            # Show control tab if any control capability exists
            return has_freq_control or has_governor_control or has_boost_control
            
        except Exception as e:
            self.logger.error(f"Error determining control tab visibility: {e}")
            return False
    
    def get_capabilities_summary(self) -> dict:
        """Get a summary of detected capabilities"""
        return {
            'is_wsl': self.is_wsl,
            'is_arm64': self.is_arm64,
            'has_clock_speeds': self.has_clock_speeds,
            'has_temperature': self.has_temperature,
            'show_control_tab': self.show_control_tab
        }