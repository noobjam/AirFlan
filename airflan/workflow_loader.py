import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Dict, Union

from loguru import logger

from airflan.orchestrator import WorkflowOrchestrator


def load_workflows(workflows_dir: Union[str, Path]) -> Dict[str, WorkflowOrchestrator]:
    """Load WorkflowOrchestrator instances from Python files in a directory."""
    workflow_path = Path(workflows_dir)
    workflow_path.mkdir(parents=True, exist_ok=True)

    workflows: Dict[str, WorkflowOrchestrator] = {}
    logger.info(f"Scanning {workflow_path} for workflows...")

    for file_path in workflow_path.glob("**/*.py"):
        try:
            module_name = f"airflan_user_workflow_{file_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            if not spec or not spec.loader:
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            for _, obj in inspect.getmembers(module):
                if isinstance(obj, WorkflowOrchestrator):
                    workflows[obj.name] = obj
                    logger.info(
                        f"Discovered workflow: {obj.name} in {file_path.name} "
                        f"(Schedule: {getattr(obj, 'schedule', 'None')})"
                    )
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")

    return workflows
