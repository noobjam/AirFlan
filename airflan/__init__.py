"""
AirFlan - Modern Workflow Orchestrator

A modular, production-ready workflow orchestration library with:
- DAG-based task scheduling
- Parallel and sequential execution
- Retry logic and timeout handling
- Result caching
- Real-time UI monitoring
- Extensible architecture

Example:
    >>> from airflan import WorkflowOrchestrator, WorkflowContext
    >>> 
    >>> wf = WorkflowOrchestrator(name="my_workflow")
    >>> 
    >>> @wf.task(name="task1")
    >>> def my_task():
    >>>     return "Hello, AirFlan!"
    >>> 
    >>> results = wf.run(parallel=True)
"""

__version__ = "2.0.0"

from .orchestrator import WorkflowOrchestrator
from .core import (
    Task,
    TaskResult,
    TaskStatus,
    WorkflowContext,
    WorkflowScheduler,
    SequentialExecutor,
    ParallelExecutor,
)
from .storage import CacheManager, StateManager

__all__ = [
    'WorkflowOrchestrator',
    'WorkflowContext',
    'Task',
    'TaskResult',
    'TaskStatus',
    'WorkflowScheduler',
    'SequentialExecutor',
    'ParallelExecutor',
    'CacheManager',
    'StateManager',
]
