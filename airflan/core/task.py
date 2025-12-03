"""
AirFlan Core Module - Task Definitions

This module contains the core task-related data models:
- TaskStatus: Enumeration of task states
- TaskResult: Result of task execution with metadata
- Task: Task definition with configuration
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class TaskStatus(Enum):
    """Enumeration of possible task execution states"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # Fixed typo from "skiped"
    TIMEOUT = "timeout"


@dataclass
class TaskResult:
    """
    Result of a task execution with metadata
    
    Attributes:
        status: Current execution status
        output: Task output/return value
        error: Exception if task failed
        error_trace: Full error traceback for debugging
        execution_time: Total execution time in seconds
        start_time: ISO format timestamp when task started
        end_time: ISO format timestamp when task finished
        attempt_count: Number of execution attempts (including retries)
    """
    status: TaskStatus
    output: Any = None
    error: Optional[Exception] = None
    error_trace: Optional[str] = None
    execution_time: float = 0.0
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    attempt_count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'status': self.status.value,
            'output': str(self.output) if self.output else None,
            'error': str(self.error) if self.error else None,
            'error_trace': self.error_trace,
            'execution_time': self.execution_time,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'attempt_count': self.attempt_count
        }


@dataclass
class Task:
    """
    Task definition with configuration and callbacks
    
    Attributes:
        name: Unique task identifier
        func: Callable function to execute
        depends_on: List of task names this task depends on
        order: Execution order within same dependency level (lower first)
        priority: Task priority (higher first)
        retry_count: Maximum number of retry attempts on failure
        retry_delay: Delay between retries in seconds
        skip_on_failure: Continue workflow even if this task fails
        timeout: Maximum execution time in seconds
        condition: Pre-execution condition check function
        args: Positional arguments to pass to func
        kwargs: Keyword arguments to pass to func
        on_success: Callback invoked on successful completion
        on_failure: Callback invoked on failure
        on_retry: Callback invoked on retry attempt
        cache_result: Whether to cache the task result
        cache_key: Key for caching (auto-generated if not provided)
    """
    name: str
    func: Callable
    depends_on: List[str] = field(default_factory=list)
    order: int = 0
    priority: int = 0
    retry_count: int = 0
    retry_delay: float = 1.0
    skip_on_failure: bool = False
    timeout: Optional[float] = None
    condition: Optional[Callable] = None
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    on_success: Optional[Callable] = None
    on_failure: Optional[Callable] = None
    on_retry: Optional[Callable] = None
    cache_result: bool = False
    cache_key: Optional[str] = None
