import time
from airflan.core.executor import DaskExecutor
from airflan.orchestrator import WorkflowOrchestrator

# This workflow runs every minute for testing daemon capabilities
orchestrator = WorkflowOrchestrator(
    name="demonstration_workflow",
    executor=DaskExecutor(),
    schedule="* * * * *"  # Run every minute
)

@orchestrator.task(priority=1)
def fetch_api_data():
    print("Fetching data from API...")
    time.sleep(1)
    return {"records": 100}

@orchestrator.task(depends_on=["fetch_api_data"])
def process_data(context):
    print("Processing Data...")
    time.sleep(2)
    return True

if __name__ == "__main__":
    # Also supports manual triggering
    orchestrator.run(parallel=True, enable_ui=False)
