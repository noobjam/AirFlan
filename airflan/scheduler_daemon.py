import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from loguru import logger
from croniter import croniter

from airflan.orchestrator import WorkflowOrchestrator
from airflan.storage.backend import DatabaseSession, DagRun
from airflan.workflow_loader import load_workflows

class SchedulerDaemon:
    """
    Background daemon that parses workflows and schedules them.
    Similar to the Apache Airflow Scheduler process.
    """
    
    def __init__(self, workflows_dir: str = "workflows", parse_interval: int = 10, db_url: Optional[str] = None):
        """
        Args:
            workflows_dir: Directory containing Python workflow definitions
            parse_interval: How often to re-parse the directory (seconds)
        """
        self.workflows_dir = Path(workflows_dir)
        self.parse_interval = parse_interval
        self.known_workflows: Dict[str, WorkflowOrchestrator] = {}
        self.workflow_schedules: Dict[str, str] = {} # dag_id -> cron_string
        
        self.db = DatabaseSession(db_url)
        self.db.init_db()
        
        # Ensure directory exists
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        
    def _parse_workflows(self):
        """Scan directory for Python files containing WorkflowOrchestrator objects"""
        self.known_workflows = load_workflows(self.workflows_dir)
        self.workflow_schedules = {
            workflow.name: workflow.schedule
            for workflow in self.known_workflows.values()
            if workflow.schedule
        }
                
    def _should_run_workflow(self, dag_id: str, cron_string: str) -> bool:
        """Evaluate if a workflow should run right now based on its cron schedule"""
        session = self.db.get_session()
        try:
            active_run = session.query(DagRun).filter(
                DagRun.dag_id == dag_id,
                DagRun.status.in_(["queued", "running"])
            ).order_by(DagRun.start_time.desc()).first()

            if active_run:
                return False

            # Find the last completed or failed run
            last_run = session.query(DagRun).filter(
                DagRun.dag_id == dag_id,
                DagRun.status.in_(["completed", "failed"])
            ).order_by(DagRun.start_time.desc()).first()
            
            now = datetime.utcnow()
            
            if not last_run:
                # No previous runs, we should run it now if it has a schedule
                return True
                
            # Use croniter to find when the *next* run should be, based on the *last* run time
            cron = croniter(cron_string, last_run.start_time)
            next_run_time = cron.get_next(datetime)
            
            # If the next scheduled time is strictly in the past or right now, we are due to run
            return now >= next_run_time
            
        except Exception as e:
            logger.error(f"Error checking schedule for {dag_id}: {e}")
            return False
        finally:
            session.close()

    def _enqueue_workflow(self, orchestrator: WorkflowOrchestrator) -> str:
        """Create a queued DagRun for workers to claim."""
        run_id = (
            f"scheduled_{orchestrator.name}_"
            f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}_"
            f"{uuid.uuid4().hex[:8]}"
        )

        session = self.db.get_session()
        try:
            dag_run = DagRun(
                dag_id=orchestrator.name,
                run_id=run_id,
                status="queued",
                start_time=datetime.utcnow(),
            )
            session.add(dag_run)
            session.commit()
            logger.info(f"Queued workflow run: {orchestrator.name} ({run_id})")
            return run_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def run(self):
        """Start the infinite scheduler loop"""
        logger.info("Scheduler Daemon starting...")
        logger.info("Press Ctrl+C to exit")
        
        try:
            while True:
                # 1. Parse Directory for new or updated workflows
                self._parse_workflows()
                
                # 2. Check schedules
                for dag_id, cron_string in self.workflow_schedules.items():
                    if self._should_run_workflow(dag_id, cron_string):
                        orchestrator = self.known_workflows[dag_id]
                        self._enqueue_workflow(orchestrator)
                        
                # 3. Sleep until next parser cycle
                time.sleep(self.parse_interval)
                
        except KeyboardInterrupt:
            logger.info("Scheduler shutting down.")
            
if __name__ == "__main__":
    daemon = SchedulerDaemon()
    daemon.run()
