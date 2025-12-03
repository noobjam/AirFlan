# AirFlan Manual

## Overview

![Alt text](../images/airflan.png)

AirFlan manages task execution with dependencies, parallelism, retries, timeouts, caching, and logging. Supports UI for monitoring via Streamlit.

# Initialization
```python
orchestrator = WorkflowOrchestrator(
    name: str = 'workflow',              # Workflow name
    log_dir: Optional[str] = None,       # Directory for logs (creates timestamped .log file)
    max_parallel: int = 4,               # Max concurrent tasks
    enable_cache: bool = True            # Enable result caching
)
```

- Logs to console by default; adds file logging if log_dir provided.
- Creates workflow_state.json and workflow_logs.txt in current directory for UI.
## Adding Tasks

### Using Decorator
```python
@orchestrator.task(
    name: Optional[str] = None,                  # Task name (defaults to function name)
    depends_on: List[str] = [],                  # Dependent task names
    order: int = 0,                              # Execution order within level (lower first)
    priority: int = 0,                           # Priority (higher first)
    retry_count: int = 0,                        # Max retries on failure
    retry_delay: float = 1.0,                    # Delay between retries (seconds)
    skip_on_failure: bool = False,               # Continue workflow on failure
    timeout: Optional[float] = None,             # Max execution time (seconds)
    condition: Optional[Callable[[WorkflowContext], bool]] = None,  # Pre-execution condition
    on_success: Optional[Callable[[Any], None]] = None,             # Callback on success
    on_failure: Optional[Callable[[Exception], None]] = None,       # Callback on failure
    on_retry: Optional[Callable[[int], None]] = None,               # Callback on retry (attempt count)
    cache_result: bool = False                   # Cache output for reuse
)
```
```python
def task_function(*args, context: Optional[WorkflowContext] = None, **kwargs) -> Any:
    # Task logic; access shared context if needed
    pass
```

### Using add_task Method
```python
orchestrator.add_task(
    func: Callable,                              # Task function
    name: Optional[str] = None,                  # Task name (defaults to function name)
    depends_on: List[str] = [],                  # As above
    order: int = 0,
    priority: int = 0,
    retry_count: int = 0,
    retry_delay: float = 1.0,
    skip_on_failure: bool = False,
    timeout: Optional[float] = None,
    condition: Optional[Callable] = None,
    args: tuple = (),                            # Positional args for func
    task_kwargs: dict = {},                      # Keyword args for func
    on_success: Optional[Callable] = None,
    on_failure: Optional[Callable] = None,
    on_retry: Optional[Callable] = None,
    cache_result: bool = False
)
```
- Tasks form a DAG via depends_on; cycles raise errors.
- Context is injectable if function accepts context parameter.
- Caching uses task name + function ID as key.

# Running the Workflow
```python

results: Dict[str, TaskResult] = orchestrator.run(
    parallel: bool = True,                       # Enable parallel execution
    dry_run: bool = False,                       # Print plan without executing
    enable_ui: bool = True                       # Launch Streamlit UI at http://localhost:6969
)
```
- Executes tasks level-by-level based on dependencies.
- Updates workflow_state.json and workflow_logs.txt for UI.
- Stops on critical failures (unless skip_on_failure=True).
- Returns dict of task results with status, output, error, etc.

# Monitoring and Visualization

## Real-time UI

- Enabled via enable_ui=True in run().
- Requires Streamlit: pip install streamlit.
- Views progress, logs, and DAG at http://localhost:6969.
- Persists after run; keep browser open.

# Example

This example defines three tasks (A, B, C) that run in a strict sequence: task_a runs first, then task_b (which depends on A), and finally task_c (which depends on B).

```python 
import time
from workflow_orchestrator import WorkflowOrchestrator, WorkflowContext

# 1. Initialize the orchestrator
orchestrator = WorkflowOrchestrator(name="sequential_workflow", log_dir="logs")

# 2. Define tasks with dependencies
@orchestrator.task(name="task_a")
def task_a():
    print("Executing Task A...")
    time.sleep(1)
    return "Result from A"

@orchestrator.task(name="task_b", depends_on=["task_a"])
def task_b(context: WorkflowContext):
    # Access output from dependency
    result_a = context.get_task_result("task_a").output
    print(f"Executing Task B... got '{result_a}'")
    time.sleep(1)
    return "Result from B"

@orchestrator.task(name="task_c", depends_on=["task_b"])
def task_c(context: WorkflowContext):
    result_b = context.get_task_result("task_b").output
    print(f"Executing Task C... got '{result_b}'")
    time.sleep(1)
    return "Workflow Complete"

# 3. Run the workflow
if __name__ == "__main__":
    print("Starting sequential workflow...")
    results = orchestrator.run(enable_ui=False)
    print("Workflow finished.")
    print(f"Final result from task_c: {results['task_c'].output}")
```
- Result: This workflow executes sequentially (A -> B -> C) because task_b depends_on task_a, and task_c depends_on task_b.
