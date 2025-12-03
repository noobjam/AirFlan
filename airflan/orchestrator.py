"""
AirFlan - Workflow Orchestrator

Main orchestrator that coordinates all workflow components.
This is a refactored, modular version that delegates to specialized modules.
"""

import json
import subprocess
import threading
import time
import webbrowser
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from .core import (
    Task, TaskResult, TaskStatus, WorkflowContext,
    WorkflowScheduler, SequentialExecutor, ParallelExecutor
)
from .storage import CacheManager, StateManager


class Colors:
    """ANSI Colors for Terminal Branding"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class WorkflowOrchestrator:
    """
    Main workflow orchestrator with modular architecture
    
    Manages task definition, execution, and monitoring with clean
    separation of concerns.
    """
    
    def __init__(
        self,
        name: str = 'workflow',
        log_dir: Optional[str] = None,
        max_parallel: int = 4,
        enable_cache: bool = True,
        executor = None
    ):
        """
        Initialize workflow orchestrator
        
        Args:
            name: Workflow name
            log_dir: Directory for logs (creates timestamped file)
            max_parallel: Max concurrent tasks for parallel execution
            enable_cache: Enable result caching
            executor: Custom executor (defaults to ParallelExecutor)
        """
        self.name = name
        self.tasks: Dict[str, Task] = {}
        self.results: Dict[str, TaskResult] = {}
        self._results_lock = threading.Lock()
        
        # Core components
        self.context = WorkflowContext()
        self.cache = CacheManager(enabled=enable_cache)
        self.executor = executor or ParallelExecutor(max_workers=max_parallel)
        
        # State management
        self._project_root = Path.cwd()
        self._state_file = self._project_root / "workflow_state.json"
        self._log_file = self._project_root / "workflow_logs.txt"
        self.state_manager = StateManager(self._state_file, self._log_file)
        
        # Execution history
        self._execution_history: List[Dict] = []
        
        # Setup logging
        self.logger = self._setup_logging(log_dir)

    def _print_banner(self):
        """Print professional ASCII banner"""
        banner = f"""
{Colors.CYAN}{Colors.BOLD}
    ___    _       ______ __            
   /   |  (_)_____/ ____// /____ _ ____ 
  / /| | / // ___/ /_   / // __ `// __ \\
 / ___ |/ // /  / __/  / // /_/ // / / /
/_/  |_/_//_/  /_/    /_/ \\__,_//_/ /_/ 
                                        
{Colors.ENDC}{Colors.BLUE}Enterprise Workflow Orchestrator v2.0{Colors.ENDC}
{Colors.HEADER}=================================================={Colors.ENDC}
"""
        print(banner)
        time.sleep(0.5)
    
    def _setup_logging(self, log_dir: Optional[str]) -> logger:
        """Configure logging"""
        logger.remove()
        logger.add(
            lambda msg: print(msg, end=""),
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} - {name} - {level} - {message}"
        )
        
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = log_path / f"{self.name}_{timestamp}.log"
            logger.add(
                log_file,
                level="DEBUG",
                format="{time:YYYY-MM-DD HH:mm:ss} - {name} - {level} - [{file.name}:{line}] - {message}",
                rotation="50 MB",
                retention="10 days"
            )
            
            # UI log file
            logger.add(
                self._log_file,
                level="INFO",
                format="{time:HH:mm:ss} | {level:<8} | {message}"
            )
        
        return logger
    
    def task(
        self,
        name: str = None,
        depends_on: List[str] = None,
        order: int = 0,
        priority: int = 0,
        retry_count: int = 0,
        retry_delay: float = 1.0,
        skip_on_failure: bool = False,
        timeout: Optional[float] = None,
        condition: Optional[Callable] = None,
        on_success: Optional[Callable] = None,
        on_failure: Optional[Callable] = None,
        on_retry: Optional[Callable] = None,
        cache_result: bool = False
    ):
        """
        Decorator to register a task
        
        Args:
            name: Task name (defaults to function name)
            depends_on: List of task names this depends on
            order: Execution order within level (lower first)
            priority: Task priority (higher first)
            retry_count: Max retries on failure
            retry_delay: Delay between retries (seconds)
            skip_on_failure: Continue workflow if this fails
            timeout: Max execution time (seconds)
            condition: Pre-execution condition function
            on_success: Success callback
            on_failure: Failure callback
            on_retry: Retry callback
            cache_result: Cache the result
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable):
            task_name = name or func.__name__
            cache_key = f"{task_name}_{id(func)}" if cache_result else None
            
            self.tasks[task_name] = Task(
                name=task_name,
                func=func,
                depends_on=depends_on or [],
                order=order,
                priority=priority,
                retry_count=retry_count,
                retry_delay=retry_delay,
                skip_on_failure=skip_on_failure,
                timeout=timeout,
                condition=condition,
                on_success=on_success,
                on_failure=on_failure,
                on_retry=on_retry,
                cache_result=cache_result,
                cache_key=cache_key
            )
            
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    def add_task(self, func: Callable, name: str = None, **kwargs):
        """Manually add a task"""
        task_name = name or func.__name__
        cache_key = f"{task_name}_{id(func)}" if kwargs.get('cache_result') else None
        
        self.tasks[task_name] = Task(
            name=task_name,
            func=func,
            depends_on=kwargs.get('depends_on', []),
            order=kwargs.get('order', 0),
            priority=kwargs.get('priority', 0),
            retry_count=kwargs.get('retry_count', 0),
            retry_delay=kwargs.get('retry_delay', 1.0),
            skip_on_failure=kwargs.get('skip_on_failure', False),
            timeout=kwargs.get('timeout'),
            condition=kwargs.get('condition'),
            args=kwargs.get('args', ()),
            kwargs=kwargs.get('task_kwargs', {}),
            on_success=kwargs.get('on_success'),
            on_failure=kwargs.get('on_failure'),
            on_retry=kwargs.get('on_retry'),
            cache_result=kwargs.get('cache_result', False),
            cache_key=cache_key
        )
    
    def run(
        self,
        parallel: bool = True,
        dry_run: bool = False,
        enable_ui: bool = True
    ) -> Dict[str, TaskResult]:
        """
        Execute the workflow
        
        Args:
            parallel: Enable parallel execution
            dry_run: Print plan without executing
            enable_ui: Launch Streamlit UI
            
        Returns:
            Dictionary of task results
        """
        self._print_banner()
        
        self.logger.info(f"{'='*70}")
        self.logger.info(f"Starting workflow: {self.name}")
        self.logger.info(f"Parallel execution: {parallel}, Dry run: {dry_run}")
        self.logger.info(f"Total tasks: {len(self.tasks)}")
        
        # Launch UI if enabled
        if enable_ui:
            self._launch_ui()
        
        self.logger.info(f"{'='*70}")
        
        workflow_start = time.time()
        
        try:
            # Create scheduler
            scheduler = WorkflowScheduler(self.tasks)
            
            # Validate dependencies
            errors = scheduler.validate_dependencies()
            if errors:
                for error in errors:
                    self.logger.error(error)
                raise ValueError("Dependency validation failed")
            
            # Build execution graph
            execution_levels = scheduler.build_execution_graph()
            
            if dry_run:
                self._print_execution_plan(execution_levels)
                return {}
            
            # Execute tasks level by level
            for level_idx, level in enumerate(execution_levels):
                self.logger.info(f"\n--- Executing Level {level_idx + 1} ---")
                
                # Sort by priority and order within level
                sorted_tasks = sorted(
                    [self.tasks[name] for name in level],
                    key=lambda t: (-t.priority, t.order)
                )
                
                # Define update callback
                def update_callback():
                    self.state_manager.update_state(self.name, self.tasks, self.results)

                # Choose executor
                if parallel and len(sorted_tasks) > 1:
                    if isinstance(self.executor, ParallelExecutor):
                        self.executor.execute_tasks(
                            sorted_tasks, self.context,
                            self._check_dependencies, self._check_condition,
                            self.results, self._results_lock,
                            on_update=update_callback
                        )
                    else:
                        # Use sequential for custom executors
                        seq_exec = SequentialExecutor(cache_enabled=self.cache.enabled)
                        seq_exec.execute_tasks(
                            sorted_tasks, self.context,
                            self._check_dependencies, self._check_condition,
                            self.results, self._results_lock,
                            on_update=update_callback
                        )
                else:
                    seq_exec = SequentialExecutor(cache_enabled=self.cache.enabled)
                    seq_exec.execute_tasks(
                        sorted_tasks, self.context,
                        self._check_dependencies, self._check_condition,
                        self.results, self._results_lock,
                        on_update=update_callback
                    )
                
                # Update UI state after each level
                self.state_manager.update_state(self.name, self.tasks, self.results)
            
            workflow_time = time.time() - workflow_start
            self.logger.info(f"\n{'='*70}")
            self.logger.info(f"Workflow completed in {workflow_time:.2f}s")
            self.logger.info(f"{'='*70}")
            
            self._print_summary()
            self._save_execution_history(workflow_time)
            
            # Final state update
            self.state_manager.update_state(self.name, self.tasks, self.results)
            self.logger.info("✓ Final state written to workflow_state.json")
            
        except Exception as e:
            self.logger.error(f"Workflow failed: {str(e)}")
            import traceback
            self.logger.debug(traceback.format_exc())
            self._print_summary()
            self.state_manager.update_state(self.name, self.tasks, self.results)
            raise
        finally:
            if enable_ui:
                self.state_manager.update_state(self.name, self.tasks, self.results)
                self.logger.info("💡 Keep browser open to view results. UI will remain accessible.")
        
        return self.results
    
    def _launch_ui(self) -> None:
        """Launch Streamlit UI"""
        import socket
        
        # Initialize state file
        self.state_manager.update_state(self.name, self.tasks, self.results)
        
        def is_port_open(port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(('localhost', port)) != 0
        
        if is_port_open(6969):
            try:
                # UI script is now inside the package
                ui_file = Path(__file__).parent / "ui.py"
                state_file_abs = str(self._state_file.absolute())
                log_file_abs = str(self._log_file.absolute())
                
                subprocess.Popen(
                    ["streamlit", "run", str(ui_file),
                     "--server.port", "6969",
                     "--server.headless", "true",
                     "--", state_file_abs, log_file_abs],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True
                )
                self.logger.info("🚀 Starting Workflow UI...")
                time.sleep(3)
                
                try:
                    webbrowser.open("http://localhost:6969", new=2)
                    self.logger.info("🔗 Workflow UI available at: http://localhost:6969")
                except:
                    self.logger.warning("Could not open browser automatically")
            except FileNotFoundError:
                self.logger.warning("Streamlit not found - UI disabled")
            except Exception as e:
                self.logger.warning(f"Failed to start UI: {e}")
        else:
            self.logger.info("🔗 Workflow UI already running at: http://localhost:6969")
    
    def _check_dependencies(self, task: Task) -> bool:
        """Check if task dependencies are satisfied"""
        for dep in task.depends_on:
            if dep not in self.results:
                return False
            if self.results[dep].status == TaskStatus.FAILED:
                if not self.tasks[dep].skip_on_failure:
                    return False
        return True
    
    def _check_condition(self, task: Task) -> bool:
        """Check if task condition is met"""
        if task.condition is None:
            return True
        try:
            return task.condition(self.context)
        except Exception as e:
            self.logger.warning(f"Condition check failed for {task.name}: {e}")
            return False
    
    def _print_execution_plan(self, levels: List[set[str]]):
        """Print execution plan for dry run"""
        self.logger.info("\n" + "="*70)
        self.logger.info("EXECUTION PLAN (Dry Run)")
        self.logger.info("="*70)
        
        for level_idx, level in enumerate(levels):
            self.logger.info(f"\nLevel {level_idx + 1} (can run in parallel):")
            for task_name in sorted(level):
                task = self.tasks[task_name]
                deps = ", ".join(task.depends_on) if task.depends_on else "None"
                self.logger.info(
                    f"  - {task_name} (priority={task.priority}, depends_on=[{deps}])"
                )
        
        self.logger.info("\n" + "="*70)
    
    def _print_summary(self):
        """Print workflow summary"""
        self.logger.info("\n" + "="*70)
        self.logger.info("WORKFLOW SUMMARY")
        self.logger.info("="*70)
        
        status_counts = {}
        total_time = 0.0
        
        for task_name, result in self.results.items():
            status = result.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
            total_time += result.execution_time
            
            symbol = {
                'completed': '✓',
                'failed': '✗',
                'skipped': '⊘',
                'timeout': '⏱'
            }.get(status, '?')
            
            self.logger.info(
                f"{symbol} {task_name}: {status.upper()} "
                f"({result.execution_time:.2f}s, {result.attempt_count} attempts)"
            )
        
        self.logger.info(f"\nStatus Summary:")
        for status, count in status_counts.items():
            self.logger.info(f"  {status.upper()}: {count}")
        
        self.logger.info(f"\nTotal task execution time: {total_time:.2f}s")
        self.logger.info("="*70)
    
    def _save_execution_history(self, workflow_time: float):
        """Save execution history"""
        history_entry = {
            'workflow_name': self.name,
            'timestamp': datetime.now().isoformat(),
            'workflow_time': workflow_time,
            'tasks': {
                name: result.to_dict()
                for name, result in self.results.items()
            },
            'context': self.context.to_dict()
        }
        self._execution_history.append(history_entry)
    
    # Utility methods
    def get_result(self, task_name: str):
        """Get result for task"""
        if task_name in self.results:
            return self.results[task_name].output
        return None
    
    def get_context(self):
        """Get workflow context"""
        return self.context.to_dict()
    
    def export_history(self, filepath: str):
        """Export execution history to file"""
        with open(filepath, 'w') as f:
            json.dump(self._execution_history, f, indent=2, default=str)
        self.logger.info(f"Execution history exported to {filepath}")
    
    def clear_cache(self):
        """Clear all cached results"""
        self.cache.clear()
        self.logger.info("Cache cleared")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get workflow metrics"""
        if not self.results:
            return {}
        
        completed = sum(1 for r in self.results.values() if r.status == TaskStatus.COMPLETED)
        failed = sum(1 for r in self.results.values() if r.status == TaskStatus.FAILED)
        skipped = sum(1 for r in self.results.values() if r.status == TaskStatus.SKIPPED)
        total_time = sum(r.execution_time for r in self.results.values())
        avg_time = total_time / len(self.results) if self.results else 0
        
        return {
            'total_tasks': len(self.results),
            'completed': completed,
            'failed': failed,
            'skipped': skipped,
            'success_rate': f"{(completed / len(self.results) * 100):.1f}%" if self.results else "0%",
            'total_execution_time': f"{total_time:.2f}s",
            'average_task_time': f"{avg_time:.2f}s"
        }
