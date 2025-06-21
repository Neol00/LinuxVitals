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
from threading import Thread
from gi.repository import GLib

class PrivilegedActions:
    def __init__(self, logger):
        # Initialize the logger
        self.logger = logger

    # Run commands with elevated privileges using pkexec
    def run_pkexec_command(self, command, cwd=None, success_callback=None, failure_callback=None):
        def run_command():
            try:
                # Build pkexec command
                if isinstance(command, list):
                    # For list commands, use pkexec with the command directly
                    pkexec_cmd = ['pkexec'] + command
                else:
                    # For string commands, use sh -c
                    pkexec_cmd = ['pkexec', 'sh', '-c', command]
                
                # Execute the command with elevated privileges using pkexec
                if cwd:
                    # For cwd, we need to use sh -c in all cases
                    if isinstance(command, list):
                        command_str = ' '.join(command)
                    else:
                        command_str = command
                    pkexec_cmd = ['pkexec', 'sh', '-c', f'cd {cwd} && {command_str}']
                
                self.logger.info(f"Executing pkexec command: {pkexec_cmd}")
                subprocess.run(pkexec_cmd, check=True)
                if success_callback:
                    GLib.idle_add(success_callback)
            except subprocess.CalledProcessError as e:
                # Check if the error is due to user cancellation or other pkexec specific issues
                if e.returncode == 126:  # Command is found but cannot be executed
                    self.logger.info("Command canceled")
                    if failure_callback:
                        GLib.idle_add(failure_callback, 'canceled')
                elif e.returncode == 127:  # Command not found
                    self.logger.error("Command not found")
                    if failure_callback:
                        GLib.idle_add(failure_callback, 'not_found')
                else:
                    self.logger.error(f"pkexec command failed with error: {e}")
                    if failure_callback:
                        GLib.idle_add(failure_callback, f"subprocess_error: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error running pkexec command: {e}")
                if failure_callback:
                    GLib.idle_add(failure_callback, f"unexpected_error: {e}")

        Thread(target=run_command).start()
