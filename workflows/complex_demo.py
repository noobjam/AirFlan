import time
import random
from airflan.core.executor import ParallelExecutor, DaskExecutor
from airflan.orchestrator import WorkflowOrchestrator

# Create an orchestrator
orchestrator = WorkflowOrchestrator(
    name="complex_etl_pipeline",
    executor=ParallelExecutor(max_workers=4) # Using ParallelExecutor for local demo
)

@orchestrator.task(priority=2)
def extract_users():
    print("Extracting users from database...")
    time.sleep(4)
    return {"users": 1500}

@orchestrator.task(priority=1)
def extract_transactions():
    print("Extracting transactions from API...")
    time.sleep(6)
    return {"txs": 50000}

@orchestrator.task(depends_on=["extract_users"])
def clean_users(context):
    print("Cleaning user data...")
    time.sleep(3)
    return True

@orchestrator.task(depends_on=["extract_transactions"])
def clean_transactions(context):
    print("Cleaning transaction data...")
    time.sleep(5)
    return True

@orchestrator.task(depends_on=["clean_users", "clean_transactions"])
def merge_data(context):
    print("Merging users and transactions...")
    time.sleep(4)
    return True

@orchestrator.task(depends_on=["merge_data"])
def train_model(context):
    print("Training predictive model...")
    time.sleep(8)
    return {"accuracy": 0.92}

@orchestrator.task(depends_on=["merge_data"])
def generate_report(context):
    print("Generating BI report...")
    time.sleep(5)
    return True

@orchestrator.task(depends_on=["train_model", "generate_report"])
def send_notifications(context):
    print("Sending slack notifications...")
    time.sleep(2)
    return True

if __name__ == "__main__":
    print("Starting Complex Demo Workflow")
    # Launch without opening a new UI, we just want to push metrics to the DB
    orchestrator.run(parallel=True, enable_ui=False)
