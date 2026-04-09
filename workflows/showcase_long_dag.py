import time
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from airflan.core.executor import ParallelExecutor
from airflan.orchestrator import WorkflowOrchestrator


orchestrator = WorkflowOrchestrator(
    name="showcase_long_dag",
    executor=ParallelExecutor(max_workers=6),
)


def pause(seconds=0.9):
    time.sleep(seconds)


@orchestrator.task(priority=10)
def ingest_orders():
    pause(26)
    return {"rows": 4200}


@orchestrator.task(priority=10)
def ingest_customers():
    pause(28)
    return {"rows": 1200}


@orchestrator.task(priority=9)
def ingest_products():
    pause(24)
    return {"rows": 860}


@orchestrator.task(priority=8)
def ingest_marketing():
    pause(30)
    return {"rows": 540}


@orchestrator.task(depends_on=["ingest_orders"])
def clean_orders(context):
    pause(22)
    return {"status": "ok", "source": "orders"}


@orchestrator.task(depends_on=["ingest_customers"])
def clean_customers(context):
    pause(20)
    return {"status": "ok", "source": "customers"}


@orchestrator.task(depends_on=["ingest_products"])
def clean_products(context):
    pause(18)
    return {"status": "ok", "source": "products"}


@orchestrator.task(depends_on=["ingest_marketing"])
def clean_marketing(context):
    pause(24)
    return {"status": "ok", "source": "marketing"}


@orchestrator.task(depends_on=["clean_orders", "clean_customers"])
def build_customer_360(context):
    pause(24)
    return {"profiles": 1180}


@orchestrator.task(depends_on=["clean_orders", "clean_products"])
def build_sales_facts(context):
    pause(28)
    return {"facts": 4100}


@orchestrator.task(depends_on=["clean_marketing", "clean_customers"])
def build_campaign_facts(context):
    pause(22)
    return {"campaign_rows": 520}


@orchestrator.task(depends_on=["build_customer_360", "build_sales_facts"])
def enrich_ltv_features(context):
    pause(24)
    return {"feature_set": "ltv"}


@orchestrator.task(depends_on=["build_sales_facts", "build_campaign_facts"])
def enrich_attribution_features(context):
    pause(22)
    return {"feature_set": "attribution"}


@orchestrator.task(depends_on=["build_sales_facts"])
def aggregate_daily_revenue(context):
    pause(16)
    return {"grain": "day"}


@orchestrator.task(depends_on=["build_sales_facts"])
def aggregate_weekly_revenue(context):
    pause(18)
    return {"grain": "week"}


@orchestrator.task(depends_on=["enrich_ltv_features", "enrich_attribution_features"])
def train_segmentation_model(context):
    pause(42)
    return {"model": "segmentation_v1"}


@orchestrator.task(depends_on=["aggregate_daily_revenue", "aggregate_weekly_revenue"])
def publish_finance_mart(context):
    pause(34)
    return {"published": True}


@orchestrator.task(depends_on=["train_segmentation_model", "publish_finance_mart"])
def build_exec_dashboard(context):
    pause(36)
    return {"dashboard": "ready"}


@orchestrator.task(depends_on=["build_exec_dashboard"])
def notify_stakeholders(context):
    pause(28)
    return {"sent": True}


if __name__ == "__main__":
    orchestrator.run(parallel=True, enable_ui=False)
