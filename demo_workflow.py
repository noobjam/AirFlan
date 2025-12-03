"""
AirFlan Enterprise Demo
=======================

Enterprise Data Processing Pipeline Simulation.
Demonstrates robust workflow orchestration for critical business processes.
"""

import random
import sys
import time

from airflan import WorkflowContext, WorkflowOrchestrator


# ANSI Colors for Terminal Branding
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


# Initialize Orchestrator
orchestrator = WorkflowOrchestrator(
    name="Enterprise_Financial_ETL", max_parallel=4, enable_cache=True, log_dir="logs"
)

# ---------------------------------------------------------
# Phase 1: Data Extraction (Parallel)
# ---------------------------------------------------------


@orchestrator.task(name="extract_ledger_data", retry_count=3)
def extract_ledger(context: WorkflowContext):
    """Extract data from General Ledger"""
    print(f"{Colors.BLUE}[EXTRACT]{Colors.ENDC} Connecting to General Ledger System...")
    time.sleep(5)  # Long duration for demo observation
    print(f"{Colors.GREEN}[SUCCESS]{Colors.ENDC} Ledger data extracted (1.2M records)")
    context.set("ledger_records", 1200000)
    return "Ledger Extracted"


@orchestrator.task(name="extract_crm_data", retry_count=3)
def extract_crm(context: WorkflowContext):
    """Extract data from CRM"""
    print(f"{Colors.BLUE}[EXTRACT]{Colors.ENDC} Connecting to CRM Database...")
    time.sleep(6)
    print(f"{Colors.GREEN}[SUCCESS]{Colors.ENDC} CRM data extracted (850k records)")
    context.set("crm_records", 850000)
    return "CRM Extracted"


@orchestrator.task(name="extract_market_data")
def extract_market():
    """Extract real-time market data"""
    print(f"{Colors.BLUE}[EXTRACT]{Colors.ENDC} Fetching Market Data API...")
    time.sleep(4)
    print(f"{Colors.GREEN}[SUCCESS]{Colors.ENDC} Market data received")
    return "Market Data Ready"


# ---------------------------------------------------------
# Phase 2: Transformation (Dependent)
# ---------------------------------------------------------


@orchestrator.task(
    name="normalize_transactions",
    depends_on=["extract_ledger_data", "extract_crm_data"],
)
def normalize_data(context: WorkflowContext):
    """Normalize and merge transaction data"""
    print(f"{Colors.CYAN}[TRANSFORM]{Colors.ENDC} Normalizing transaction formats...")
    time.sleep(8)  # Heavy processing simulation

    total = context.get("ledger_records") + context.get("crm_records")
    print(f"{Colors.GREEN}[SUCCESS]{Colors.ENDC} Normalized {total} transactions")
    context.set("total_processed", total)
    return "Normalization Complete"


@orchestrator.task(
    name="compliance_check", depends_on=["extract_ledger_data"], priority=10
)
def compliance_check():
    """Run regulatory compliance checks"""
    print(f"{Colors.WARNING}[AUDIT]{Colors.ENDC} Running SOX compliance validation...")
    time.sleep(6)
    print(f"{Colors.GREEN}[PASSED]{Colors.ENDC} Compliance validation successful")
    return "Compliance Verified"


# ---------------------------------------------------------
# Phase 3: Enrichment & External Services
# ---------------------------------------------------------


@orchestrator.task(
    name="enrich_customer_profiles", depends_on=["normalize_transactions"]
)
def enrich_profiles(context: WorkflowContext):
    """Enrich customer profiles with market data"""
    print(f"{Colors.CYAN}[ENRICH]{Colors.ENDC} Enriching profiles...")
    time.sleep(7)
    return "Enrichment Complete"


@orchestrator.task(
    name="fraud_detection_api",
    depends_on=["normalize_transactions"],
    retry_count=3,
    retry_delay=2.0,
)
def fraud_check():
    """Call external Fraud Detection System"""
    print(f"{Colors.WARNING}[SECURITY]{Colors.ENDC} Querying Fraud Detection System...")
    time.sleep(3)

    # Simulate occasional network blip
    if random.random() < 0.3:
        print(
            f"{Colors.FAIL}[ERROR]{Colors.ENDC} Connection timeout to Fraud API. Retrying..."
        )
        raise ConnectionError("Fraud API Timeout")

    print(f"{Colors.GREEN}[SECURE]{Colors.ENDC} No fraudulent activity detected")
    return "Fraud Check Passed"


# ---------------------------------------------------------
# Phase 4: Loading & Reporting
# ---------------------------------------------------------


@orchestrator.task(
    name="load_data_warehouse",
    depends_on=[
        "enrich_customer_profiles",
        "fraud_detection_api",
        "compliance_check",
        "extract_market_data",
    ],
    timeout=30.0,
)
def load_warehouse(context: WorkflowContext):
    """Load processed data into Enterprise Data Warehouse"""
    records = context.get("total_processed", 0)
    print(f"{Colors.BLUE}[LOAD]{Colors.ENDC} Loading {records} records to Snowflake...")

    steps = ["Staging", "Merging", "Indexing", "Committing"]
    for step in steps:
        print(f"    ... {step}")
        time.sleep(3)

    return "Warehouse Load Complete"


@orchestrator.task(
    name="generate_executive_dashboard",
    depends_on=["load_data_warehouse"],
    cache_result=True,
)
def generate_dashboard(context: WorkflowContext):
    """Generate and cache executive dashboard data"""
    print(f"{Colors.HEADER}[REPORT]{Colors.ENDC} Generating Executive Dashboard...")
    time.sleep(4)
    print(f"{Colors.GREEN}[DONE]{Colors.ENDC} Dashboard updated successfully")
    return "Dashboard Ready"


# ---------------------------------------------------------
# Main Execution
# ---------------------------------------------------------

if __name__ == "__main__":
    print("Starting Enterprise ETL Pipeline Simulation...")
    print(
        f"Monitor execution at: {Colors.UNDERLINE}http://localhost:6969{Colors.ENDC}\n"
    )

    try:
        start = time.time()
        results = orchestrator.run(parallel=True, enable_ui=True)
        duration = time.time() - start

        print(
            f"\n{Colors.HEADER}=================================================={Colors.ENDC}"
        )
        print(
            f"{Colors.GREEN}{Colors.BOLD}WORKFLOW COMPLETED SUCCESSFULLY{Colors.ENDC}"
        )
        print(f"Total Duration: {duration:.2f}s")
        print(
            f"{Colors.HEADER}=================================================={Colors.ENDC}"
        )

    except Exception as e:
        print(f"\n{Colors.FAIL}Workflow Failed: {e}{Colors.ENDC}")
