# Experiment Tracking Guide

## Overview

AirFlan includes native experiment tracking capabilities that allow you to track metrics, parameters, and artifacts for your workflow runs - similar to MLflow or Weights & Biases, but fully integrated with your workflow orchestration.

## Quick Start

### Enable Experiment Tracking

Simply add `experiment_name` when creating your orchestrator:

```python
from airflan import WorkflowOrchestrator, WorkflowContext

wf = WorkflowOrchestrator(
    name="ml_training",
    experiment_name="mnist_classifier"  # ← Enable tracking!
)
```

### Log Metrics

Track metrics over time (e.g., training loss, accuracy):

```python
@wf.task(name="train_model")
def train_model(context: WorkflowContext):
    for epoch in range(10):
        loss = train_one_epoch()
        accuracy = evaluate()
        
        # Log metrics with step number
        context.log_metric("train_loss", loss, step=epoch)
        context.log_metric("val_accuracy", accuracy, step=epoch)
```

### Log Parameters

Track hyperparameters and configuration:

```python
@wf.task(name="train_model")
def train_model(context: WorkflowContext):
    # Log all hyperparameters
    context.log_params({
        "learning_rate": 0.001,
        "batch_size": 32,
        "epochs": 10,
        "optimizer": "Adam"
    })
```

### Log Artifacts

Save models, plots, datasets, and other files:

```python
@wf.task(name="train_model")
def train_model(context: WorkflowContext):
    # Save model
    torch.save(model.state_dict(), "model.pth")
    context.log_artifact("model.pth", artifact_type="model")
    
    # Save plot
    plt.savefig("training_curve.png")
    context.log_artifact("training_curve.png", artifact_type="plot")
```

## View Results in Dashboard

After running your workflow, launch the experiments dashboard:

```bash
streamlit run airflan/ui/experiments_dashboard.py
```

The dashboard provides:

- **📊 Experiments Overview** - See all experiments and their runs
- **🔬 Run Details** - View metrics charts, parameters, and artifacts for each run
- **📈 Compare Runs** - Side-by-side comparison of multiple runs

## Complete Example

Here's a full ML training workflow with experiment tracking:

```python
from airflan import WorkflowOrchestrator, WorkflowContext
import torch
import matplotlib.pyplot as plt

# Initialize with experiment tracking
wf = WorkflowOrchestrator(
    name="neural_net_training",
    experiment_name="image_classifier"
)

@wf.task(name="load_data")
def load_data(context: WorkflowContext):
    # Log dataset info
    context.log_params({
        "dataset": "CIFAR10",
        "train_samples": 50000,
        "test_samples": 10000
    })
    
    # Load data...
    return train_loader, test_loader

@wf.task(name="train", depends_on=["load_data"])
def train_model(context: WorkflowContext):
    # Log hyperparameters
    context.log_params({
        "learning_rate": 0.001,
        "batch_size": 32,
        "epochs": 50,
        "model": "ResNet18"
    })
    
    # Training loop
    for epoch in range(50):
        train_loss = train_one_epoch(model, train_loader)
        val_acc = validate(model, test_loader)
        
        # Log metrics
        context.log_metric("train_loss", train_loss, step=epoch)
        context.log_metric("val_accuracy", val_acc, step=epoch)
    
    # Save model
    torch.save(model.state_dict(), "model.pth")
    context.log_artifact("model.pth", artifact_type="model")
    
    # Save training plot
    plot_training_curve()
    context.log_artifact("training_curve.png", artifact_type="plot")
    
    return model

@wf.task(name="evaluate", depends_on=["train"])
def evaluate_model(context: WorkflowContext):
    # Evaluate on test set
    test_accuracy = evaluate(model, test_loader)
    test_loss = compute_loss(model, test_loader)
    
    # Log final metrics
    context.log_metric("test_accuracy", test_accuracy)
    context.log_metric("test_loss", test_loss)
    
    return test_accuracy

# Run workflow - automatically tracked!
wf.run(parallel=True)
```

## Architecture

### Database Schema

Experiment data is stored in SQLite (`airflan_experiments.db`):

- **experiments** - Top-level experiments
- **runs** - Individual workflow executions
- **metrics** - Time-series metrics (loss, accuracy, etc.)
- **params** - Hyperparameters and configuration
- **artifacts** - File metadata

### Artifact Storage

Files are stored in `airflan_artifacts/[run_id]/`:

- Models (.pth, .h5, .pkl)
- Plots (.png, .jpg, .pdf)
- Data (.csv, .parquet)
- Configs (.json, .yaml)
- Logs (.txt, .log)

### Context Methods

When experiment tracking is enabled, tasks have access to:

- `context.log_metric(name, value, step=None)` - Log scalar metric
- `context.log_params(dict)` - Log parameters
- `context.log_artifact(path, name=None, type=None)` - Save artifact
- `context.get_experiment_tracker()` - Access tracker directly

## Comparing Runs

Use the dashboard to compare different hyperparameter configurations:

1. Navigate to "📈 Compare Runs"
2. Select 2-5 runs to compare
3. View parameter differences
4. Compare metric curves side-by-side
5. Identify best performing configuration

## Best Practices

### 1. Meaningful Experiment Names

```python
# Good
experiment_name="resnet_cifar10_baseline"

# Not ideal
experiment_name="experiment1"
```

### 2. Log Early and Often

```python
# Log dataset info
context.log_params({"dataset": "MNIST", "samples": 60000})

# Log hyperparameters
context.log_params({"lr": 0.001, "batch_size": 32})

# Log metrics per epoch
for epoch in range(epochs):
    context.log_metric("loss", loss, step=epoch)

# Log final results
context.log_metric("test_accuracy", final_acc)
```

### 3. Organize Artifacts

```python
# Use descriptive names and types
context.log_artifact("model_epoch_50.pth", artifact_type="model")
context.log_artifact("confusion_matrix.png", artifact_type="plot")
context.log_artifact("predictions.csv", artifact_type="data")
```

### 4. Use Steps for Training Metrics

```python
# Training metrics should use steps
context.log_metric("train_loss", loss, step=epoch)
context.log_metric("val_accuracy", acc, step=epoch)

# Final metrics don't need steps
context.log_metric("test_accuracy", test_acc)  # No step
```

## Advanced Usage

### Access Tracker Directly

```python
tracker = context.get_experiment_tracker()

# Get run ID
run_id = tracker.current_run_id

# Query metrics
metrics = tracker.get_metrics(metric_name="train_loss")

# Compare runs
comparison = tracker.compare_runs([run_id_1, run_id_2])
```

### Programmatic Access

```python
from airflan.mlops import MetricsStore, ExperimentTracker

# Query database directly
store = MetricsStore("airflan_experiments.db")

# List all experiments
experiments = store.list_experiments()

# Get runs for an experiment
runs = store.list_runs(experiment_id)

# Get metrics for a run
metrics = store.get_metrics(run_id, "val_accuracy")
```

## Troubleshooting

### No Metrics Showing in Dashboard

Make sure you:
1. Added `experiment_name` to orchestrator
2. Called `context.log_metric()` in your tasks
3. Ran the workflow to completion

### Artifacts Not Found

Check that:
1. File exists before calling `log_artifact()`
2. Using absolute or relative path correctly
3. `airflan_artifacts/` directory has proper permissions

### Database Locked Error

If running multiple workflows simultaneously:
- SQLite has limited concurrency
- Consider using different experiment names
- Or run workflows sequentially

## Migration from MLflow/W&B

If you're coming from MLflow or Weights & Biases:

| MLflow | W&B | AirFlan |
|--------|-----|---------|
| `mlflow.log_param()` | `wandb.config` | `context.log_params()` |
| `mlflow.log_metric()` | `wandb.log()` | `context.log_metric()` |
| `mlflow.log_artifact()` | `wandb.save()` | `context.log_artifact()` |
| `mlflow ui` | `wandb.ai` | `streamlit run experiments_dashboard.py` |

**Advantages of AirFlan:**
- ✅ Integrated with workflow orchestration
- ✅ No external services required
- ✅ Simple SQLite storage
- ✅ Full control over data
- ✅ Free and open source

## What's Next?

Future enhancements planned:
- Model registry with versioning
- Feature store integration  
- Hyperparameter optimization
- Model deployment tracking
- Team collaboration features
- REST API for programmatic access

See the main README for the complete roadmap!
