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
from gi.repository import GLib
from typing import Dict, Callable, Optional

class TaskScheduler:
    """Generic task scheduler for system monitoring tasks"""
    
    def __init__(self, logger):
        self.logger = logger
        self.task_ids: Dict[str, Optional[int]] = {}
        self.task_callbacks: Dict[str, Callable] = {}
        
    def schedule_task(self, task_name: str, callback: Callable, interval_ms: int = 1000) -> None:
        """Schedule a periodic task with the given interval"""
        try:
            # Stop existing task if running
            self.stop_task(task_name)
            
            # Store callback for the run method
            self.task_callbacks[task_name] = callback
            
            # Schedule new task
            self.task_ids[task_name] = GLib.timeout_add(interval_ms, self._run_task, task_name)
            self.logger.info(f"Scheduled {task_name} task with {interval_ms}ms interval")
            
        except Exception as e:
            self.logger.error(f"Error scheduling {task_name} task: {e}")
    
    def stop_task(self, task_name: str) -> None:
        """Stop a scheduled task"""
        try:
            task_id = self.task_ids.get(task_name)
            if task_id:
                GLib.source_remove(task_id)
                self.task_ids[task_name] = None
                self.logger.info(f"Stopped {task_name} task")
                
        except Exception as e:
            self.logger.error(f"Error stopping {task_name} task: {e}")
    
    def _run_task(self, task_name: str) -> bool:
        """Execute a scheduled task"""
        try:
            callback = self.task_callbacks.get(task_name)
            if callback:
                callback()
            
            # Continue scheduling if task is still active
            return self.task_ids.get(task_name) is not None
            
        except Exception as e:
            self.logger.error(f"Error running {task_name} task: {e}")
            return False
    
    def stop_all_tasks(self) -> None:
        """Stop all scheduled tasks"""
        for task_name in list(self.task_ids.keys()):
            self.stop_task(task_name)
    
    def is_task_running(self, task_name: str) -> bool:
        """Check if a task is currently running"""
        return self.task_ids.get(task_name) is not None
    
    def get_running_tasks(self) -> list:
        """Get list of currently running task names"""
        return [name for name, task_id in self.task_ids.items() if task_id is not None]