import time
import random
from airflan.core.executor import ParallelExecutor
from airflan.orchestrator import WorkflowOrchestrator

orchestrator = WorkflowOrchestrator(
    name="enterprise_ml_pipeline",
    executor=ParallelExecutor(max_workers=8) # High concurrency
)

# --- Level 1: Ingestion ---
@orchestrator.task(priority=10)
def ingest_clickstream():
    time.sleep(3)
    return {"records": 100000}

@orchestrator.task(priority=10)
def ingest_crm_data():
    time.sleep(5)
    return {"records": 5000}

@orchestrator.task(priority=5)
def scrape_competitor_pricing():
    time.sleep(7)
    return {"status": "ok"}

# --- Level 2: Processing (Scatter) ---
@orchestrator.task(depends_on=["ingest_clickstream"])
def clean_clickstream(context):
    time.sleep(4)
    return True

@orchestrator.task(depends_on=["ingest_crm_data"])
def anonymize_pii(context):
    time.sleep(2)
    return True

@orchestrator.task(depends_on=["scrape_competitor_pricing"])
def parse_html_tables(context):
    time.sleep(6)
    return True

# --- Level 3: Feature Engineering ---
@orchestrator.task(depends_on=["clean_clickstream", "anonymize_pii"])
def build_user_features(context):
    time.sleep(5)
    return {"features": 128}

@orchestrator.task(depends_on=["parse_html_tables"])
def build_market_features(context):
    time.sleep(3)
    return {"features": 45}

# --- Level 4: Model Training (Parallel Grid Search) ---
@orchestrator.task(depends_on=["build_user_features", "build_market_features"])
def train_xgboost(context):
    time.sleep(12)
    return {"auc": 0.89}

@orchestrator.task(depends_on=["build_user_features", "build_market_features"])
def train_random_forest(context):
    time.sleep(10)
    return {"auc": 0.82}

@orchestrator.task(depends_on=["build_user_features", "build_market_features"])
def train_neural_net(context):
    # Simulate a flaky task
    if random.random() < 0.3:
        time.sleep(4)
        raise ValueError("CUDA Out of Memory Exception (simulated)")
    time.sleep(15)
    return {"auc": 0.94}

# --- Level 5: Evaluation (Gather) ---
@orchestrator.task(depends_on=["train_xgboost", "train_random_forest", "train_neural_net"], skip_on_failure=True)
def select_best_model(context):
    time.sleep(3)
    return "neural_net"

# --- Level 6: Deployment & Reporting ---
@orchestrator.task(depends_on=["select_best_model"])
def deploy_to_production(context):
    time.sleep(5)
    return {"endpoint": "api.airflan.internal/v2/predict"}

@orchestrator.task(depends_on=["select_best_model"])
def generate_shap_values(context):
    time.sleep(6)
    return True

@orchestrator.task(depends_on=["select_best_model"])
def email_stakeholders(context):
    time.sleep(2)
    return True

if __name__ == "__main__":
    print("Starting Enterprise Machine Learning Pipeline Demo")
    orchestrator.run(parallel=True, enable_ui=False)
