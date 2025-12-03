"""
AirFlan Core Module - Task Executor

This module provides different execution strategies for running tasks:
- Sequential execution (one at a time)
- Parallel execution (concurrent using threads)
"""

import threading
import time
import traceback
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable, Dict, List, Optional

from loguru import logger

from .context import WorkflowContext
from .task import Task, TaskResult, TaskStatus


class BaseExecutor(ABC):
    """Abstract base class for task executors"""
    
    @abstractmethod
    def execute_tasks(
        self, 
        tasks: List[Task], 
        context: WorkflowContext,
        check_deps: Callable[[Task], bool],
        check_condition: Callable[[Task], bool],
        results: Dict[str, TaskResult],
        results_lock: threading.Lock,
        on_update: Optional[Callable] = None
    ) -> Dict[str, TaskResult]:
        """
        Execute a list of tasks
        
        Args:
            tasks: List of tasks to execute
            context: Shared workflow context
            check_deps: Function to check if dependencies are satisfied
            check_condition: Function to check task condition
            results: Dictionary to store results (shared across tasks)
            results_lock: Lock for thread-safe results updates
            on_update: Callback to trigger state update
            
        Returns:
            Dictionary mapping task names to TaskResult objects
        """
        pass


class SequentialExecutor(BaseExecutor):
    """Execute tasks one at a time in order"""
    
    def __init__(self, cache_enabled: bool = True):
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, any] = {}
    
    def execute_tasks(
        self, 
        tasks: List[Task], 
        context: WorkflowContext,
        check_deps: Callable[[Task], bool],
        check_condition: Callable[[Task], bool],
        results: Dict[str, TaskResult],
        results_lock: threading.Lock,
        on_update: Optional[Callable] = None
    ) -> Dict[str, TaskResult]:
        """Execute tasks sequentially"""
        for task in tasks:
            self._execute_single_task(
                task, context, check_deps, check_condition, 
                results, results_lock, on_update
            )
        return results
    
    def _execute_single_task(
        self,
        task: Task,
        context: WorkflowContext,
        check_deps: Callable[[Task], bool],
        check_condition: Callable[[Task], bool],
        results: Dict[str, TaskResult],
        results_lock: threading.Lock,
        on_update: Optional[Callable] = None
    ) -> None:
        """Execute a single task with all checks"""
        # Check condition
        if not check_condition(task):
            logger.info(f"⊘ Skipping {task.name} - condition not met")
            with results_lock:
                results[task.name] = TaskResult(status=TaskStatus.SKIPPED)
            return
        
        # Check dependencies
        if not check_deps(task):
            logger.warning(f"⊘ Skipping {task.name} - dependencies failed")
            with results_lock:
                results[task.name] = TaskResult(status=TaskStatus.SKIPPED)
            return
        
        # Mark as running
        with results_lock:
            results[task.name] = TaskResult(
                status=TaskStatus.RUNNING,
                start_time=datetime.now().isoformat()
            )
        
        # Trigger update for RUNNING state
        if on_update:
            on_update()
        
        # Execute task
        result = self._execute_task(task, context)
        
        with results_lock:
            results[task.name] = result
            
        # Trigger update for COMPLETED/FAILED state
        if on_update:
            on_update()
        
        # Store result in context
        context.set(f"result_{task.name}", result.output)
        
        # Stop workflow if critical task failed
        if result.status == TaskStatus.FAILED and not task.skip_on_failure:
            raise Exception(f"Critical task {task.name} failed. Stopping workflow.")
    
    def _execute_task(self, task: Task, context: WorkflowContext) -> TaskResult:
        """Execute a task with retries and timeout"""
        # Check cache
        cached = self._get_cached_result(task)
        if cached is not None:
            logger.info(f"Using cached result for {task.name}")
            return TaskResult(
                status=TaskStatus.COMPLETED,
                output=cached,
                execution_time=0,
                start_time=datetime.now().isoformat(),
                end_time=datetime.now().isoformat()
            )
        
        attempts = 0
        max_attempts = task.retry_count + 1
        
        while attempts < max_attempts:
            attempts += 1
            start_time = datetime.now()
            
            try:
                logger.info(
                    f"Running task: {task.name} "
                    f"(attempt {attempts}/{max_attempts}, priority: {task.priority})"
                )
                
                # Prepare kwargs with context injection
                task_kwargs = task.kwargs.copy()
                if 'context' in task.func.__code__.co_varnames:
                    task_kwargs['context'] = context
                
                # Execute with timeout
                result = self._execute_with_timeout(
                    task.func, task.timeout, task.args, task_kwargs
                )
                
                end_time = datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                
                # Cache result
                self._cache_result(task, result)
                
                # Success callback
                if task.on_success:
                    try:
                        task.on_success(result)
                    except Exception as e:
                        logger.warning(f"on_success callback failed: {e}")
                
                logger.info(f"Task {task.name} completed in {execution_time:.2f}s")
                
                return TaskResult(
                    status=TaskStatus.COMPLETED,
                    output=result,
                    execution_time=execution_time,
                    start_time=start_time.isoformat(),
                    end_time=end_time.isoformat(),
                    attempt_count=attempts
                )
            
            except TimeoutError as e:
                logger.error(f"Task {task.name} timed out: {str(e)}")
                return TaskResult(
                    status=TaskStatus.TIMEOUT,
                    error=e,
                    error_trace=traceback.format_exc(),
                    execution_time=(datetime.now() - start_time).total_seconds(),
                    start_time=start_time.isoformat(),
                    end_time=datetime.now().isoformat(),
                    attempt_count=attempts
                )
            
            except Exception as e:
                end_time = datetime.now()
                execution_time = (end_time - start_time).total_seconds()
                
                logger.error(
                    f"✗ Task {task.name} failed (attempt {attempts}/{max_attempts}): {str(e)}"
                )
                logger.debug(f"Traceback: {traceback.format_exc()}")
                
                # Retry callback
                if attempts < max_attempts:
                    if task.on_retry:
                        try:
                            task.on_retry(attempts)
                        except Exception as cb_e:
                            logger.warning(f"on_retry callback failed: {cb_e}")
                    
                    logger.info(f"Retrying in {task.retry_delay}s...")
                    time.sleep(task.retry_delay)
                else:
                    # Failure callback
                    if task.on_failure:
                        try:
                            task.on_failure(e)
                        except Exception as cb_e:
                            logger.warning(f"on_failure callback failed: {cb_e}")
                    
                    return TaskResult(
                        status=TaskStatus.FAILED,
                        error=e,
                        error_trace=traceback.format_exc(),
                        execution_time=execution_time,
                        start_time=start_time.isoformat(),
                        end_time=end_time.isoformat(),
                        attempt_count=attempts
                    )
        
        # Fallback (should never reach here)
        return TaskResult(
            status=TaskStatus.FAILED,
            error=Exception("Task execution completed without returning a result"),
            execution_time=0.0,
            start_time=datetime.now().isoformat(),
            end_time=datetime.now().isoformat(),
            attempt_count=attempts
        )
    
    def _execute_with_timeout(
        self, 
        func: Callable, 
        timeout: Optional[float],
        args: tuple, 
        kwargs: dict
    ):
        """Execute function with optional timeout"""
        if timeout is None:
            return func(*args, **kwargs)
        
        result = [None]
        exception = [None]
        
        def target():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            raise TimeoutError(f"Task exceeded timeout of {timeout} seconds")
        if exception[0]:
            raise exception[0]
        return result[0]
    
    def _get_cached_result(self, task: Task) -> Optional[any]:
        """Get cached result if available"""
        if not self.cache_enabled or not task.cache_result or not task.cache_key:
            return None
        return self._cache.get(task.cache_key)
    
    def _cache_result(self, task: Task, result: any) -> None:
        """Cache task result"""
        if self.cache_enabled and task.cache_result and task.cache_key:
            self._cache[task.cache_key] = result


class ParallelExecutor(SequentialExecutor):
    """Execute tasks in parallel using thread pool"""
    
    def __init__(self, max_workers: int = 4, cache_enabled: bool = True):
        super().__init__(cache_enabled)
        self.max_workers = max_workers
    
    def execute_tasks(
        self, 
        tasks: List[Task], 
        context: WorkflowContext,
        check_deps: Callable[[Task], bool],
        check_condition: Callable[[Task], bool],
        results: Dict[str, TaskResult],
        results_lock: threading.Lock,
        on_update: Optional[Callable] = None
    ) -> Dict[str, TaskResult]:
        """Execute tasks in parallel using thread pool"""
        if len(tasks) == 1:
            # Single task - use sequential execution
            return super().execute_tasks(
                tasks, context, check_deps, check_condition, results, results_lock, on_update
            )
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self._execute_single_task,
                    task, context, check_deps, check_condition, 
                    results, results_lock, on_update
                ): task
                for task in tasks
            }
            
            for future in as_completed(futures):
                task = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Parallel execution error for {task.name}: {e}")
        
        return results
