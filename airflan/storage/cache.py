"""
AirFlan Storage Module - Cache Manager

This module provides result caching functionality.
"""

from typing import Any, Dict, Optional

from ..core.task import Task


class CacheManager:
    """
    In-memory cache for task results
    
    Supports caching task results to avoid re-execution of
    expensive operations. Can be extended to support Redis,
    file-based caching, etc.
    """
    
    def __init__(self, enabled: bool = True):
        """
        Initialize cache manager
        
        Args:
            enabled: Whether caching is enabled
        """
        self.enabled = enabled
        self._cache: Dict[str, Any] = {}
    
    def get(self, task: Task) -> Optional[Any]:
        """
        Get cached result for task
        
        Args:
            task: Task to check cache for
            
        Returns:
            Cached result or None if not found
        """
        if not self.enabled or not task.cache_result or not task.cache_key:
            return None
        return self._cache.get(task.cache_key)
    
    def set(self, task: Task, result: Any) -> None:
        """
        Cache result for task
        
        Args:
            task: Task to cache result for
            result: Result to cache
        """
        if self.enabled and task.cache_result and task.cache_key:
            self._cache[task.cache_key] = result
    
    def clear(self) -> None:
        """Clear all cached results"""
        self._cache.clear()
    
    def size(self) -> int:
        """Get number of cached items"""
        return len(self._cache)
    
    def __repr__(self) -> str:
        """String representation"""
        return f"CacheManager(size={self.size()}, enabled={self.enabled})"
