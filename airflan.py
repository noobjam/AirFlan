#TODO : stream  the tqdm bars to the UI, truncated logs, and ETA
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import time
from enum import Enum

from dataclasses import dataclass, field, asdict

from functools import wraps
import json
from pathlib import Path



import threading
from typing import Any, Dict, List, Callable, Optional, Set

import traceback

from loguru import logger


class TaskStatus(Enum):

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skiped"
    TIMEOUT = "timeout"


@dataclass
class TaskResult:
    status:TaskStatus
    output:Any =None
    error:Optional[Exception] = None
    error_trace:Optional[str] = None
    execution_time:float = 0.0
    start_time:Optional[str] = None
    end_time:Optional[str] = None
    attempt_count: int = 1

    def to_dict(self):
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
    name:str
    func:Callable
    depends_on : List[str] = field(default_factory=list)
    order:int =0
    priority :int =0
    retry_count:int =0
    retry_delay :float =1.0
    skip_on_failure :bool = False
    timeout:Optional[float] = None
    condition : Optional[Callable] = None
    args:tuple = field(default_factory=tuple)

    kwargs:dict=field(default_factory=dict)


    #callbacks

    on_success :Optional[Callable] = None
    on_failure:Optional[Callable] = None
    on_retry:Optional[Callable] = None

    #cache settings 
    cache_result:bool = False
    cache_key:Optional[str] = None




class WorkflowContext:
    def __init__(self):
        self._data : Dict[str,Any] ={}
        self._lock = threading.Lock()



    def set(self,key:str,value:Any):
        with self._lock:
            self._data[key] = value

    def get(self, key:str, default:Any = None) -> Any:
        with self._lock:
            return self._data.get(key,default)

    def update(self, data: Dict[str, Any]):
        with self._lock:
            self._data.update(data)

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return self._data.copy()


class WorkflowOrchestrator:

    def __init__(self,name:str = 'workflow',log_dir:Optional[str]=None,max_parallel:int=4,enable_cache:bool=True):
        self.name = name
        self.tasks:Dict[str,Task] = {}
        self.results:Dict[str,TaskResult] = {}
        self._results_lock = threading.Lock()  # BUG FIX: Add thread safety
        self.context = WorkflowContext()
        self.max_parallel = max_parallel
        self.enable_cache = enable_cache
        self._cache : Dict[str,Any] = {}
        self._execution_history :List[Dict]=[]

        import os
        self._project_root = Path(os.getcwd())  # Where the test is run from
        self._state_file = self._project_root / "workflow_state.json"
        self._log_file = self._project_root / "workflow_logs.txt"
        
        self.logger = self._setup_logging(log_dir)



    def _setup_logging(self, log_dir: Optional[str]):
        logger.remove()
        logger.add(lambda msg: print(msg, end=""), level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} - {name} - {level} - {message}")
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = log_path / f"{self.name}_{timestamp}.log"
            logger.add(log_file, level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss} - {name} - {level} - [{file.name}:{line}] - {message}", rotation="50 MB", retention="10 days")
            # === UI log file for live dashboard ===
            self._ui_log_file = Path("workflow_logs.txt")
            self._ui_log_file.write_text("")  # Clear old logs
            logger.add(self._ui_log_file, level="INFO", format="{time:HH:mm:ss} | {level:<8} | {message}")

        return logger

    def _update_ui_state(self):
        """Write workflow progress to file for UI"""
        try:
            state = {
                "name": self.name,
                "timestamp": datetime.now().isoformat(),
                "results": {},
                "tasks": {
                    name: {"depends_on": task.depends_on}
                    for name, task in self.tasks.items()
                },
            }
            
            # Add all tasks with their current status
            for name in self.tasks.keys():
                if name in self.results:
                    result = self.results[name]
                    state["results"][name] = {
                        "status": result.status.value,
                        "execution_time": result.execution_time,
                    }
                else:
                    state["results"][name] = {
                        "status": "pending",
                        "execution_time": 0
                    }
            
            # Write to absolute path
            with open(self._state_file, "w") as f:
                json.dump(state, f, indent=2)
            
            self.logger.debug(f"UI state updated: {self._state_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to update UI state: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())

    def run(self, parallel: bool = True, dry_run: bool = False, enable_ui: bool = True) -> Dict[str, TaskResult]:
        
        self.logger.info(f"{'='*70}")
        self.logger.info(f"Starting workflow: {self.name}")
        self.logger.info(f"Parallel execution: {parallel}, Dry run: {dry_run}")
        self.logger.info(f"Total tasks: {len(self.tasks)}")
        
        # === Launch Streamlit UI FIRST if enabled ===
        if enable_ui:
            import subprocess
            import webbrowser
            from pathlib import Path
            
            # Initialize state file BEFORE starting UI
            self._update_ui_state()
            
            # Verify state file was created
            if not Path("workflow_state.json").exists():
                self.logger.error("Failed to create workflow_state.json")
            else:
                self.logger.info(f"✓ State file created: workflow_state.json")
            
            # Check if UI is already running
            import socket
            def is_port_open(port):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    return s.connect_ex(('localhost', port)) != 0
            
            if is_port_open(6969):
                # Start Streamlit as a detached subprocess
                try:
                    ui_file = Path(__file__).parent / "workflow_ui.py"
        
                    # USE ABSOLUTE PATHS - this is the key fix!
                    state_file_abs = str(self._state_file.absolute())
                    log_file_abs = str(self._log_file.absolute())
                    
                    self.logger.info(f"Starting UI with state file: {state_file_abs}")
                    
                    subprocess.Popen(
                        ["streamlit", "run", str(ui_file), 
                        "--server.port", "6969", 
                        "--server.headless", "true",
                        "--", state_file_abs, log_file_abs],  # Pass ABSOLUTE paths here
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        start_new_session=True
                    )
                    self.logger.info("🚀 Starting Workflow UI...")
                    time.sleep(3)
                    
                    # Open browser
                    try:
                        webbrowser.open("http://localhost:6969", new=2)
                        self.logger.info("🔗 Workflow UI available at: http://localhost:6969")
                    except:
                        self.logger.warning("Could not open browser automatically")
                except FileNotFoundError:
                    self.logger.warning("Streamlit not found - UI disabled. Install with: pip install streamlit")
                    enable_ui = False
                except Exception as e:
                    self.logger.warning(f"Failed to start UI: {e}")
                    enable_ui = False
            else:
                self.logger.info("🔗 Workflow UI already running at: http://localhost:6969")
        
        self.logger.info(f"{'='*70}")
        
        workflow_start = time.time()
        
        try:
            # Build execution graph
            execution_levels = self._build_execution_graph()
            
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
                
                if parallel and len(sorted_tasks) > 1:
                    self._execute_parallel(sorted_tasks)
                else:
                    self._execute_sequential(sorted_tasks)
            
            workflow_time = time.time() - workflow_start
            self.logger.info(f"\n{'='*70}")
            self.logger.info(f"Workflow completed in {workflow_time:.2f}s")
            self.logger.info(f"{'='*70}")
            
            self._print_summary()
            self._save_execution_history(workflow_time)
            
            # Final state update
            self._update_ui_state()
            self.logger.info("✓ Final state written to workflow_state.json")
            
        except Exception as e:
            self.logger.error(f"Workflow failed: {str(e)}")
            self.logger.debug(traceback.format_exc())
            self._print_summary()
            self._update_ui_state()  # Update UI even on failure
            raise
        finally:
            # Final state update for UI
            if enable_ui:
                self._update_ui_state()
                self.logger.info("💡 Keep browser open to view results. UI will remain accessible.")
        
        return self.results


        
    

    def task(self,name:str=None,depends_on:List[str]=None,
             order:int = 0,priority:int=0,retry_count:int=0,
             retry_delay:float = 1.0,skip_on_failure:bool=False,
             timeout:Optional[float] = None,condition:Optional[Callable] = None,
             on_success:Optional[Callable] = None,on_failure:Optional[Callable] = None,
             on_retry:Optional[Callable] = None,cache_result:bool = False
             ):
        def decorator(func:Callable):
            task_name = name or func.__name__
            cache_key = f"{task_name}_{id(func)}" if cache_result else None

            self.tasks[task_name] = Task(

                name=task_name,
                func=func,
                depends_on=depends_on or [],
                order = order,
                priority=priority,
                retry_count=retry_count,
                retry_delay=retry_delay,
                skip_on_failure=skip_on_failure,
                timeout=timeout,
                condition = condition, 
                on_success=on_success,
                on_failure=on_failure,
                on_retry=on_retry,
                cache_result=cache_result,
                cache_key=cache_key
            )
            @wraps(func)
            def wrapper(*args,**kwargs):
                return func(*args,**kwargs)
            return wrapper
        return decorator
    def add_task(self, func: Callable, name: str = None, **kwargs):
        """Manually add a task with configuration"""
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

    def _check_dependencies(self, task:Task) ->bool:
        for dep in task.depends_on:
            if dep not in self.results:
                return False
            if self.results[dep].status == TaskStatus.FAILED:
                if not self.tasks[dep].skip_on_failure:
                    return False
                
        return True
    
    def _check_condition(self, task:Task)->bool:
        if task.condition is None:
            return True
        
        try:
            return task.condition(self.context)
        
        except Exception as e:
            self.logger.warning(f"condtion check failed for {task.name}: {e}")

            return False
        

    def _get_cached_result(self, task:Task) ->Optional[Any]:
        if not self.enable_cache or not task.cache_result or not task.cache_key:
            return None
        return self._cache.get(task.cache_key)

    def _cache_result(self, task: Task, result: Any):
        if self.enable_cache and task.cache_result and task.cache_key:
            self._cache[task.cache_key] = result


    def _execute_with_timeout(self,func:Callable,timeout:Optional[float],args:tuple,kwargs:dict ):
        if timeout is None:
            return func(*args,**kwargs)

        result = [None]
        exception = [None]


        def target():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                exception[0] = e

        thread = threading.Thread(target = target)
        thread.daemon = True
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            raise TimeoutError(f"task exceeded timeout of {timeout} seconds")
        if exception[0]:
            raise exception[0]
        return result[0]

    def _execute_task(self,task:Task)->TaskResult:
        cached = self._get_cached_result(task)
        if cached is not None :
            self.logger.info(f"using cached result for {task.name}")
            return TaskResult(
                status=TaskStatus.COMPLETED,
                output = cached,
                execution_time=0,
                start_time=datetime.now().isoformat(),
                end_time=datetime.now().isoformat()
            )

        attempts = 0
        max_attempts = task.retry_count + 1

        while attempts < max_attempts:
            attempts+=1
            start_time=datetime.now()

            try:
                self.logger.info(
                    f"running task : {task.name}"
                    f"(attempt {attempts}/{max_attempts}, priority : {task.priority})"
                )

                # BUG FIX: Dedent execution logic - was incorrectly nested
                task_kwargs = task.kwargs.copy()
                if 'context' in task.func.__code__.co_varnames:
                    task_kwargs['context'] = self.context

                result = self._execute_with_timeout(
                    task.func, task.timeout,task.args,task_kwargs
                )

                end_time = datetime.now()
                execution_time = (end_time - start_time).total_seconds()

                # result cache
                self._cache_result(task=task,result=result)

                #successs callback
                if task.on_success:
                    try:
                        task.on_success(result)
                    except Exception as e :
                        self.logger.warning(f"on_success callback failed : {e}")

                self.logger.info(f"Task {task.name} completed in {execution_time : .2f} s")

                return TaskResult(
                    status=TaskStatus.COMPLETED,
                    output=result,
                    execution_time=execution_time,
                    start_time=start_time.isoformat(),
                    end_time=end_time.isoformat(),
                    attempt_count=attempts
                )
                
            except TimeoutError as e:
                self.logger.error(f"Task {task.name} timed out: {str(e)}")
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
                
                self.logger.error(
                    f"✗ Task {task.name} failed (attempt {attempts}/{max_attempts}): {str(e)}"
                )
                self.logger.debug(f"Traceback: {traceback.format_exc()}")
                
                # Retry callback
                if attempts < max_attempts:
                    if task.on_retry:
                        try:
                            task.on_retry(attempts)
                        except Exception as cb_e:
                            self.logger.warning(f"on_retry callback failed: {cb_e}")
                    
                    self.logger.info(f"Retrying in {task.retry_delay}s...")
                    time.sleep(task.retry_delay)
                else:
                    # Failure callback
                    if task.on_failure:
                        try:
                            task.on_failure(e)
                        except Exception as cb_e:
                            self.logger.warning(f"on_failure callback failed: {cb_e}")
                    
                    return TaskResult(
                        status=TaskStatus.FAILED,
                        error=e,
                        error_trace=traceback.format_exc(),
                        execution_time=execution_time,
                        start_time=start_time.isoformat(),
                        end_time=end_time.isoformat(),
                        attempt_count=attempts
                    )
        
        # BUG FIX: Ensure function always returns a TaskResult
        # This should never be reached, but provides safety
        return TaskResult(
            status=TaskStatus.FAILED,
            error=Exception("Task execution completed without returning a result"),
            execution_time=0.0,
            start_time=datetime.now().isoformat(),
            end_time=datetime.now().isoformat(),
            attempt_count=attempts if 'attempts' in locals() else 0
        )
            



    def _build_execution_graph(self)->List[set[str]]:
        """Build execution graph for parallel execution"""
        # Topological sort with levels for parallel executio
        in_degree = {name: len(task.depends_on) for name, task in self.tasks.items()}
        levels: List[Set[str]] = []
        remaining = set(self.tasks.keys())
        
        while remaining:
            # Find tasks with no dependencies (or dependencies satisfied)
            level = {
                name for name in remaining
                if all(dep not in remaining for dep in self.tasks[name].depends_on)
            }
            
            if not level:
                # Circular dependency detected
                raise ValueError(f"Circular dependency detected in tasks: {remaining}")
            
            levels.append(level)
            remaining -= level
        
        return levels


    


    def _execute_sequential(self, tasks:List[Task]):
        for task in tasks:
            self._execute_single_task(task)

    def _execute_parallel(self, tasks: List[Task]):
        with ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            futures = {
                executor.submit(self._execute_single_task, task): task
                for task in tasks
            }
            
            for future in as_completed(futures):
                task = futures[future]
                try:
                    future.result()
                except Exception as e:
                    self.logger.error(f"Parallel execution error for {task.name}: {e}")


    def _execute_single_task(self, task: Task):
        # Check condition
        if not self._check_condition(task):
            self.logger.info(f"⊘ Skipping {task.name} - condition not met")
            with self._results_lock:  # BUG FIX: Thread-safe update
                self.results[task.name] = TaskResult(status=TaskStatus.SKIPPED)
            self._update_ui_state()
            return
        
        # Check dependencies
        if not self._check_dependencies(task):
            self.logger.warning(f"⊘ Skipping {task.name} - dependencies failed")
            with self._results_lock:  # BUG FIX: Thread-safe update
                self.results[task.name] = TaskResult(status=TaskStatus.SKIPPED)
            self._update_ui_state()
            return
        
        with self._results_lock:  # BUG FIX: Thread-safe update
            self.results[task.name] = TaskResult(
                status=TaskStatus.RUNNING,
                start_time=datetime.now().isoformat()
            )
        self._update_ui_state()

        # Execute task
        result = self._execute_task(task)
        
        with self._results_lock:  # BUG FIX: Thread-safe update
            self.results[task.name] = result
        
        # Store result in context
        self.context.set(f"result_{task.name}", result.output)
        
        # Update UI after task completes
        self._update_ui_state()
        
        # Stop workflow if critical task failed
        if result.status == TaskStatus.FAILED and not task.skip_on_failure:
            raise Exception(f"Critical task {task.name} failed. Stopping workflow.")


        
    def _print_execution_plan(self, levels: List[Set[str]]):
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
        """Save execution history to file"""
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

    def plot_workflow(self, filepath: str = None, show: bool = True):
        """Generate workflow visualization using networkx and matplotlib"""
        import matplotlib.pyplot as plt
        import networkx as nx

        if not self.tasks:
            self.logger.warning("No tasks to plot.")
            return

        G = nx.DiGraph()
        for name, task in self.tasks.items():
            G.add_node(name)
            for dep in task.depends_on:
                G.add_edge(dep, name)

        color_map = []
        for name in G.nodes:
            result = self.results.get(name)
            if result is None:
                color_map.append("gray")
            else:
                if result.status == TaskStatus.COMPLETED:
                    color_map.append("green")
                elif result.status == TaskStatus.FAILED:
                    color_map.append("red")
                elif result.status == TaskStatus.SKIPPED:
                    color_map.append("yellow")
                elif result.status == TaskStatus.TIMEOUT:
                    color_map.append("orange")
                else:
                    color_map.append("gray")

        try:
            pos = nx.nx_agraph.graphviz_layout(G, prog="dot")
        except Exception:
            pos = nx.spring_layout(G, seed=42)

        plt.figure(figsize=(12, 8))
        nx.draw(
            G, pos,
            with_labels=True,
            node_color=color_map,
            node_size=3000,
            font_size=9,
            font_weight="bold",
            arrows=True,
            arrowstyle="->",
            arrowsize=15,
        )

        plt.title(f"Workflow Graph: {self.name}", fontsize=14, fontweight="bold")

        legend_labels = {
            "green": "COMPLETED",
            "red": "FAILED",
            "yellow": "SKIPPED",
            "orange": "TIMEOUT",
            "gray": "PENDING"
        }
        for color, label in legend_labels.items():
            plt.scatter([], [], c=color, label=label)
        plt.legend(frameon=True, loc="best")
        plt.tight_layout()

        if filepath:
            plt.savefig(filepath, dpi=200)
            self.logger.info(f"Workflow plot saved to {filepath}")
        if show:
            plt.show()
        else:
            plt.close()  


    def get_result(self,task_name:str):
        if task_name in self.results:
            return self.results[task_name].output
        return None

    def get_context(self):
        return self._context.to_dict()
    

    def export_history(self, filepath: str):
        with open(filepath, 'w') as f:
            json.dump(self._execution_history, f, indent=2, default=str)
        self.logger.info(f"Execution history exported to {filepath}")


    def clear_cache(self):
        """Clear all cached results"""
        self._cache.clear()
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

