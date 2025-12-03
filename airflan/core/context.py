"""
AirFlan Core Module - Workflow Context

This module provides thread-safe shared state management for workflows.
"""

import threading
from typing import Any, Dict


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
    
    def __init__(self):
        """Initialize empty context with thread lock"""
        self._data: Dict[str, Any] = {}
        self._lock = threading.Lock()

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
    
    def __repr__(self) -> str:
        """String representation of context"""
        with self._lock:
            return f"WorkflowContext({len(self._data)} items)"
