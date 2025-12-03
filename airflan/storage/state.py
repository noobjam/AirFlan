"""
AirFlan Monitoring Module - State Manager

This module handles workflow state persistence for UI integration.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

from ..core.task import Task, TaskResult


class StateManager:
    """
    Manages workflow state persistence for real-time UI updates
    
    Writes workflow state to JSON file that can be consumed by
    the Streamlit UI or other monitoring tools.
    """
    
    def __init__(self, state_file: Path, log_file: Path):
        """
        Initialize state manager
        
        Args:
            state_file: Path to state JSON file
            log_file: Path to log file
        """
        self.state_file = state_file
        self.log_file = log_file
        
        # Initialize empty files
        self._init_files()
    
    def _init_files(self) -> None:
        """Initialize empty state and log files"""
        try:
            self.state_file.write_text(json.dumps({}))
            self.log_file.write_text("")
        except Exception as e:
            logger.warning(f"Failed to initialize state files: {e}")
    
    def update_state(
        self,
        workflow_name: str,
        tasks: Dict[str, Task],
        results: Dict[str, TaskResult]
    ) -> None:
        """
        Update workflow state file
        
        Args:
            workflow_name: Name of the workflow
            tasks: Dictionary of tasks
            results: Dictionary of task results
        """
        try:
            state = {
                "name": workflow_name,
                "timestamp": datetime.now().isoformat(),
                "tasks": {
                    name: {"depends_on": task.depends_on}
                    for name, task in tasks.items()
                },
                "results": {}
            }
            
            # Add task statuses
            for name in tasks.keys():
                if name in results:
                    result = results[name]
                    state["results"][name] = {
                        "status": result.status.value,
                        "execution_time": result.execution_time,
                    }
                else:
                    state["results"][name] = {
                        "status": "pending",
                        "execution_time": 0
                    }
            
            # Write to file
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
            
            logger.debug(f"State updated: {self.state_file}")
            
        except Exception as e:
            logger.error(f"Failed to update state: {e}")
    
    def load_state(self) -> Optional[Dict]:
        """
        Load workflow state from file
        
        Returns:
            State dictionary or None if not found
        """
        try:
            if self.state_file.exists():
                return json.loads(self.state_file.read_text())
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
        return None
