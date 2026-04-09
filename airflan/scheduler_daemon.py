import importlib.util
import inspect
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from loguru import logger
from croniter import croniter

from airflan.orchestrator import WorkflowOrchestrator
from airflan.storage.backend import DatabaseSession, DagRun

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
        self._active_runs = set()
        self._active_runs_lock = threading.Lock()
        
        self.db = DatabaseSession(db_url)
        self.db.init_db()
        
        # Ensure directory exists
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        
    def _parse_workflows(self):
        """Scan directory for Python files containing WorkflowOrchestrator objects"""
        logger.info(f"Scanning {self.workflows_dir} for workflows...")
        
        for file_path in self.workflows_dir.glob("**/*.py"):
            try:
                # Dynamically load the python module
                module_name = file_path.stem
                spec = importlib.util.spec_from_file_location(module_name, str(file_path))
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    
                    # Find WorkflowOrchestrator instances in the module
                    for name, obj in inspect.getmembers(module):
                        if isinstance(obj, WorkflowOrchestrator):
                            self.known_workflows[obj.name] = obj
                            # Check if a schedule was defined (we will add this attr to WorkflowOrchestrator next)
                            if hasattr(obj, 'schedule') and obj.schedule:
                                self.workflow_schedules[obj.name] = obj.schedule
                            
                            logger.info(f"Discovered workflow: {obj.name} in {file_path.name} (Schedule: {getattr(obj, 'schedule', 'None')})")
            except Exception as e:
                logger.error(f"Failed to parse {file_path}: {e}")
                
    def _should_run_workflow(self, dag_id: str, cron_string: str) -> bool:
        """Evaluate if a workflow should run right now based on its cron schedule"""
        with self._active_runs_lock:
            if dag_id in self._active_runs:
                return False

        session = self.db.get_session()
        try:
            running_run = session.query(DagRun).filter(
                DagRun.dag_id == dag_id,
                DagRun.status == "running"
            ).order_by(DagRun.start_time.desc()).first()

            if running_run:
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

    def _trigger_workflow(self, orchestrator: WorkflowOrchestrator):
        """Execute the workflow in a non-blocking process/thread. 
           In Phase 4 we will spawn a subprocess to avoid blocking the scheduler loop.
        """
        with self._active_runs_lock:
            if orchestrator.name in self._active_runs:
                logger.info(f"Skipping {orchestrator.name} - run already active")
                return
            self._active_runs.add(orchestrator.name)

        logger.info(f"Triggering scheduled workflow: {orchestrator.name}")
        # Assuming the workflow file can be executed directly as `python filename.py`
        # In a pure daemon, we might pickle it and send it to a worker. 
        # For this phase, we'll run it in a subprocess using a generic AirFlan CLI entrypoint (Phase 5).
        # For now, we will just call it in a thread so the scheduler loop continues.
        
        def run_it():
            try:
                orchestrator.run(parallel=True, enable_ui=False)
            except Exception as e:
                logger.error(f"Scheduled run failed: {e}")
            finally:
                with self._active_runs_lock:
                    self._active_runs.discard(orchestrator.name)
                
        t = threading.Thread(target=run_it, daemon=True)
        t.start()

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
                        self._trigger_workflow(orchestrator)
                        
                # 3. Sleep until next parser cycle
                time.sleep(self.parse_interval)
                
        except KeyboardInterrupt:
            logger.info("Scheduler shutting down.")
            
if __name__ == "__main__":
    daemon = SchedulerDaemon()
    daemon.run()
