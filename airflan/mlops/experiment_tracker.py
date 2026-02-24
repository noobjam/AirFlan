"""
AirFlan Experiment Tracker

High-level API for experiment tracking. Coordinates metrics store and artifact store.
Provides simple interface for logging experiments, metrics, parameters, and artifacts.
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger

from .metrics_store import MetricsStore
from .artifact_store import ArtifactStore


class ExperimentTracker:
    """
    High-level experiment tracking interface
    
    Coordinates between metrics store (database) and artifact store (files).
    Provides simple API for logging all experiment data.
    """
    
    def __init__(self, 
                 experiment_name: str,
                 db_path: str = "airflan_experiments.db",
                 artifacts_dir: str = "airflan_artifacts"):
        """
        Initialize experiment tracker
        
        Args:
            experiment_name: Name of the experiment
            db_path: Path to SQLite database
            artifacts_dir: Directory for artifacts
        """
        self.experiment_name = experiment_name
        self.metrics_store = MetricsStore(db_path)
        self.artifact_store = ArtifactStore(artifacts_dir)
        
        # Create or get experiment
        self.experiment_id = str(uuid.uuid4())
        existing = self.metrics_store.get_experiment(experiment_name)
        
        if existing:
            self.experiment_id = existing['experiment_id']
            logger.debug(f"Using existing experiment: {experiment_name}")
        else:
            self.metrics_store.create_experiment(
                self.experiment_id, 
                experiment_name
            )
            logger.info(f"Created new experiment: {experiment_name}")
        
        self.current_run_id: Optional[str] = None
    
    def start_run(self, run_name: Optional[str] = None, 
                  workflow_name: Optional[str] = None) -> str:
        """
        Start a new experiment run
        
        Args:
            run_name: Optional name for the run
            workflow_name: Optional workflow name
            
        Returns:
            run_id
        """
        self.current_run_id = str(uuid.uuid4())
        
        self.metrics_store.create_run(
            self.current_run_id,
            self.experiment_id,
            run_name,
            workflow_name
        )
        
        logger.info(f"Started run {self.current_run_id} in experiment {self.experiment_name}")
        return self.current_run_id
    
    def end_run(self, status: str = "completed"):
        """
        End the current run
        
        Args:
            status: Run status ('completed' or 'failed')
        """
        if self.current_run_id:
            self.metrics_store.update_run_status(
                self.current_run_id, 
                status,
                datetime.now()
            )
            logger.info(f"Ended run {self.current_run_id} with status: {status}")
            self.current_run_id = None
    
    def log_metric(self, name: str, value: float, step: Optional[int] = None):
        """
        Log a metric value
        
        Args:
            name: Metric name (e.g., 'loss', 'accuracy')
            value: Metric value
            step: Optional step number (e.g., epoch, iteration)
        """
        if not self.current_run_id:
            logger.warning("No active run. Call start_run() first.")
            return
        
        self.metrics_store.log_metric(
            self.current_run_id,
            name,
            value,
            step
        )
        
        logger.debug(f"Logged metric {name}={value} (step={step})")
    
    def log_metrics(self, metrics: Dict[str, float], step: Optional[int] = None):
        """
        Log multiple metrics at once
        
        Args:
            metrics: Dictionary of metric names and values
            step: Optional step number
        """
        for name, value in metrics.items():
            self.log_metric(name, value, step)
    
    def log_param(self, name: str, value: Any):
        """
        Log a single parameter
        
        Args:
            name: Parameter name
            value: Parameter value
        """
        self.log_params({name: value})
    
    def log_params(self, params: Dict[str, Any]):
        """
        Log multiple parameters
        
        Args:
            params: Dictionary of parameter names and values
        """
        if not self.current_run_id:
            logger.warning("No active run. Call start_run() first.")
            return
        
        self.metrics_store.log_params(self.current_run_id, params)
        logger.debug(f"Logged {len(params)} parameters")
    
    def log_artifact(self, file_path: str, artifact_name: Optional[str] = None,
                     artifact_type: Optional[str] = None):
        """
        Log an artifact file
        
        Args:
            file_path: Path to artifact file
            artifact_name: Optional artifact name (defaults to filename)
            artifact_type: Optional type (model, plot, data, etc.)
        """
        if not self.current_run_id:
            logger.warning("No active run. Call start_run() first.")
            return
        
        # Use filename if no name provided
        if not artifact_name:
            artifact_name = Path(file_path).name
        
        # Store artifact file
        storage_path, size_bytes = self.artifact_store.store_artifact(
            file_path,
            artifact_name,
            self.current_run_id
        )
        
        # Log metadata to database
        self.metrics_store.log_artifact(
            self.current_run_id,
            artifact_name,
            storage_path,
            artifact_type,
            size_bytes
        )
        
        logger.info(f"Logged artifact: {artifact_name}")
    
    # Query methods
    
    def get_run_info(self, run_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get run information"""
        rid = run_id or self.current_run_id
        if not rid:
            return None
        return self.metrics_store.get_run(rid)
    
    def get_metrics(self, run_id: Optional[str] = None, 
                    metric_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get metrics for a run"""
        rid = run_id or self.current_run_id
        if not rid:
            return []
        return self.metrics_store.get_metrics(rid, metric_name)
    
    def get_params(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """Get parameters for a run"""
        rid = run_id or self.current_run_id
        if not rid:
            return {}
        return self.metrics_store.get_params(rid)
    
    def get_artifacts(self, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get artifacts for a run"""
        rid = run_id or self.current_run_id
        if not rid:
            return []
        return self.metrics_store.get_artifacts(rid)
    
    def get_artifact_path(self, artifact_name: str, 
                         run_id: Optional[str] = None) -> Optional[Path]:
        """Get path to artifact file"""
        rid = run_id or self.current_run_id
        if not rid:
            return None
        return self.artifact_store.get_artifact_path(rid, artifact_name)
    
    def list_runs(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all runs in this experiment"""
        return self.metrics_store.list_runs(self.experiment_id, status)
    
    def compare_runs(self, run_ids: List[str]) -> Dict[str, Any]:
        """
        Compare multiple runs
        
        Args:
            run_ids: List of run IDs to compare
            
        Returns:
            Dictionary with comparison data
        """
        comparison = {
            'runs': [],
            'metrics': {},
            'params': {}
        }
        
        for run_id in run_ids:
            run_info = self.metrics_store.get_run(run_id)
            if run_info:
                comparison['runs'].append(run_info)
                
                # Get final metric values
                metrics = {}
                metric_names = self.metrics_store.get_metric_names(run_id)
                for metric_name in metric_names:
                    metric_data = self.metrics_store.get_metrics(run_id, metric_name)
                    if metric_data:
                        # Get last value
                        metrics[metric_name] = metric_data[-1]['metric_value']
                
                comparison['metrics'][run_id] = metrics
                comparison['params'][run_id] = self.metrics_store.get_params(run_id)
        
        return comparison
