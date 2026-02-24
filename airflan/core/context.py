"""
AirFlan Core Module - Workflow Context

This module provides thread-safe shared state management for workflows.
"""

import threading
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..mlops.experiment_tracker import ExperimentTracker


class WorkflowContext:
    """
    Thread-safe key-value store for sharing state between tasks
    
    Provides a simple interface for tasks to share data across
    the workflow execution with automatic thread-safe locking.
    
    Example:
        >>> context = WorkflowContext()
        >>> context.set('user_id', 12345)
        >>> user_id = context.get('user_id')
    """
    
    def __init__(self, experiment_tracker: Optional['ExperimentTracker'] = None):
        """
        Initialize empty context with thread lock
        
        Args:
            experiment_tracker: Optional experiment tracker for logging metrics/params
        """
        self._data: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._experiment_tracker = experiment_tracker

    def set(self, key: str, value: Any) -> None:
        """
        Set a value in the context
        
        Args:
            key: Context key
            value: Value to store
        """
        with self._lock:
            self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the context
        
        Args:
            key: Context key
            default: Default value if key not found
            
        Returns:
            Value for key, or default if not found
        """
        with self._lock:
            return self._data.get(key, default)

    def update(self, data: Dict[str, Any]) -> None:
        """
        Update multiple values at once
        
        Args:
            data: Dictionary of key-value pairs to update
        """
        with self._lock:
            self._data.update(data)

    def to_dict(self) -> Dict[str, Any]:
        """
        Get a copy of all context data
        
        Returns:
            Dictionary copy of context data
        """
        with self._lock:
            return self._data.copy()
    
    def clear(self) -> None:
        """Clear all context data"""
        with self._lock:
            self._data.clear()
    
    def keys(self) -> list:
        """Get all context keys"""
        with self._lock:
            return list(self._data.keys())
    
    def __contains__(self, key: str) -> bool:
        """Check if key exists in context"""
        with self._lock:
            return key in self._data
    
    # ==================== Experiment Tracking ====================
    
    def log_metric(self, name: str, value: float, step: Optional[int] = None) -> None:
        """
        Log a metric to the experiment tracker
        
        Args:
            name: Metric name
            value: Metric value
            step: Optional step number
        """
        if self._experiment_tracker:
            self._experiment_tracker.log_metric(name, value, step)
    
    def log_params(self, params: Dict[str, Any]) -> None:
        """
        Log parameters to the experiment tracker
        
        Args:
            params: Dictionary of parameter names and values
        """
        if self._experiment_tracker:
            self._experiment_tracker.log_params(params)
    
    def log_artifact(self, file_path: str, artifact_name: Optional[str] = None,
                     artifact_type: Optional[str] = None) -> None:
        """
        Log an artifact to the experiment tracker
        
        Args:
            file_path: Path to artifact file
            artifact_name: Optional artifact name
            artifact_type: Optional artifact type
        """
        if self._experiment_tracker:
            self._experiment_tracker.log_artifact(file_path, artifact_name, artifact_type)
    
    def get_experiment_tracker(self) -> Optional['ExperimentTracker']:
        """Get the experiment tracker instance"""
        return self._experiment_tracker
    
    def __repr__(self) -> str:
        """String representation of context"""
        with self._lock:
            return f"WorkflowContext({len(self._data)} items)"
