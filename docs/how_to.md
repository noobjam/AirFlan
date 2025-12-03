# How to Use AirFlan

AirFlan is a lightweight, modular workflow orchestrator designed for simplicity and scalability.

## Core Concepts

1. **Orchestrator**: The main engine that manages tasks and execution.
2. **Task**: A unit of work (function) with defined dependencies.
3. **Context**: A shared storage mechanism to pass data between tasks.

## Quick Start

### 1. Basic Setup

```python
from airflan import WorkflowOrchestrator, WorkflowContext

# Initialize
wf = WorkflowOrchestrator(name="my_pipeline")
```

### 2. Defining Tasks

Use the `@wf.task` decorator to register functions as tasks.

**Sequential Task:**
```python
@wf.task(name="step_1")
def start_process():
    print("Starting...")
    return "Started"
```

**Dependent Task (DAG):**
```python
@wf.task(name="step_2", depends_on=["step_1"])
def process_data(context: WorkflowContext):
    # Tasks run only after dependencies complete
    return "Processed"
```

### 3. Passing Data (Context)

Tasks can accept a `context` argument to read/write shared data.

```python
@wf.task(name="producer")
def produce(context: WorkflowContext):
    context.set("my_key", 123)

@wf.task(name="consumer", depends_on=["producer"])
def consume(context: WorkflowContext):
    val = context.get("my_key")
    print(f"Got: {val}")
```

### 4. Advanced Features

**Retries & Timeouts:**
```python
@wf.task(
    name="flaky_api",
    retry_count=3,      # Retry 3 times on failure
    retry_delay=2.0,    # Wait 2s between retries
    timeout=5.0         # Fail if takes > 5s
)
def call_api():
    # ...
```

**Caching:**
```python
@wf.task(name="expensive_calc", cache_result=True)
def calculate():
    # Result will be cached and reused if run again
    return 42
```

### 5. Running the Workflow

```python
if __name__ == "__main__":
    # Run in parallel with UI enabled
    wf.run(parallel=True, enable_ui=True)
```

## Execution Modes

- **Sequential**: `wf.run(parallel=False)` - Runs one task at a time. Good for debugging.
- **Parallel**: `wf.run(parallel=True)` - Runs independent tasks concurrently using threads.

## Monitoring

When `enable_ui=True` is set, AirFlan launches a dashboard at `http://localhost:6969` to visualize the DAG and track progress in real-time.
