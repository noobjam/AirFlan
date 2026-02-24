"""
AirFlan Metrics Store

SQLite-based storage for experiment metrics, parameters, and metadata.
Provides efficient time-series storage and querying for experiment tracking.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger


class MetricsStore:
    """
    SQLite-based storage for experiment tracking data
    
    Stores experiments, runs, metrics, parameters, and artifacts metadata.
    Provides efficient querying and filtering capabilities.
    """
    
    def __init__(self, db_path: str = "airflan_experiments.db"):
        """
        Initialize metrics store
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Create database schema if it doesn't exist"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Experiments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                experiment_name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            )
        """)
        
        # Runs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL,
                run_name TEXT,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                status TEXT CHECK(status IN ('running', 'completed', 'failed')),
                workflow_name TEXT,
                FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
            )
        """)
        
        # Metrics table (time-series)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                step INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            )
        """)
        
        # Parameters table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS params (
                param_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                param_name TEXT NOT NULL,
                param_value TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id),
                UNIQUE(run_id, param_name)
            )
        """)
        
        # Artifacts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                artifact_name TEXT NOT NULL,
                artifact_path TEXT NOT NULL,
                artifact_type TEXT,
                size_bytes INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            )
        """)
        
        # Create indexes for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_run_name 
            ON metrics(run_id, metric_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_runs_experiment 
            ON runs(experiment_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_runs_status 
            ON runs(status)
        """)
        
        conn.commit()
        conn.close()
        logger.debug(f"Initialized metrics store at {self.db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        return conn
    
    # ==================== Experiments ====================
    
    def create_experiment(self, experiment_id: str, experiment_name: str, 
                         description: Optional[str] = None) -> str:
        """
        Create a new experiment
        
        Args:
            experiment_id: Unique experiment ID
            experiment_name: Human-readable experiment name
            description: Optional experiment description
            
        Returns:
            experiment_id
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO experiments (experiment_id, experiment_name, description)
                VALUES (?, ?, ?)
            """, (experiment_id, experiment_name, description))
            conn.commit()
            logger.info(f"Created experiment: {experiment_name} ({experiment_id})")
        except sqlite3.IntegrityError:
            # Experiment already exists
            logger.debug(f"Experiment {experiment_name} already exists")
        finally:
            conn.close()
        
        return experiment_id
    
    def get_experiment(self, experiment_name: str) -> Optional[Dict[str, Any]]:
        """Get experiment by name"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM experiments WHERE experiment_name = ?
        """, (experiment_name,))
        
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def list_experiments(self) -> List[Dict[str, Any]]:
        """List all experiments"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM experiments ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # ==================== Runs ====================
    
    def create_run(self, run_id: str, experiment_id: str, 
                   run_name: Optional[str] = None,
                   workflow_name: Optional[str] = None) -> str:
        """
        Create a new run
        
        Args:
            run_id: Unique run ID
            experiment_id: Parent experiment ID
            run_name: Optional run name
            workflow_name: Optional workflow name
            
        Returns:
            run_id
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO runs (run_id, experiment_id, run_name, start_time, status, workflow_name)
            VALUES (?, ?, ?, ?, 'running', ?)
        """, (run_id, experiment_id, run_name, datetime.now(), workflow_name))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Created run: {run_id} in experiment {experiment_id}")
        return run_id
    
    def update_run_status(self, run_id: str, status: str, end_time: Optional[datetime] = None):
        """Update run status"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE runs 
            SET status = ?, end_time = ?
            WHERE run_id = ?
        """, (status, end_time or datetime.now(), run_id))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"Updated run {run_id} status to {status}")
    
    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get run by ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def list_runs(self, experiment_id: Optional[str] = None, 
                  status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List runs with optional filtering
        
        Args:
            experiment_id: Filter by experiment
            status: Filter by status
            
        Returns:
            List of run dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM runs WHERE 1=1"
        params = []
        
        if experiment_id:
            query += " AND experiment_id = ?"
            params.append(experiment_id)
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY start_time DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # ==================== Metrics ====================
    
    def log_metric(self, run_id: str, metric_name: str, metric_value: float,
                   step: Optional[int] = None, timestamp: Optional[datetime] = None):
        """
        Log a metric value
        
        Args:
            run_id: Run ID
            metric_name: Metric name
            metric_value: Metric value
            step: Optional step number (for iterative training)
            timestamp: Optional timestamp (defaults to now)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO metrics (run_id, metric_name, metric_value, step, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (run_id, metric_name, metric_value, step, timestamp or datetime.now()))
        
        conn.commit()
        conn.close()
    
    def get_metrics(self, run_id: str, metric_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get metrics for a run
        
        Args:
            run_id: Run ID
            metric_name: Optional metric name filter
            
        Returns:
            List of metric dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if metric_name:
            cursor.execute("""
                SELECT * FROM metrics 
                WHERE run_id = ? AND metric_name = ?
                ORDER BY step, timestamp
            """, (run_id, metric_name))
        else:
            cursor.execute("""
                SELECT * FROM metrics 
                WHERE run_id = ?
                ORDER BY metric_name, step, timestamp
            """, (run_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_metric_names(self, run_id: str) -> List[str]:
        """Get all unique metric names for a run"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT metric_name FROM metrics WHERE run_id = ?
            ORDER BY metric_name
        """, (run_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [row[0] for row in rows]
    
    # ==================== Parameters ====================
    
    def log_params(self, run_id: str, params: Dict[str, Any]):
        """
        Log parameters for a run
        
        Args:
            run_id: Run ID
            params: Dictionary of parameter names and values
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        for param_name, param_value in params.items():
            # Convert value to string for storage
            value_str = json.dumps(param_value) if isinstance(param_value, (dict, list)) else str(param_value)
            
            cursor.execute("""
                INSERT OR REPLACE INTO params (run_id, param_name, param_value)
                VALUES (?, ?, ?)
            """, (run_id, param_name, value_str))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"Logged {len(params)} parameters for run {run_id}")
    
    def get_params(self, run_id: str) -> Dict[str, Any]:
        """Get all parameters for a run"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT param_name, param_value FROM params WHERE run_id = ?", (run_id,))
        rows = cursor.fetchall()
        conn.close()
        
        params = {}
        for row in rows:
            param_name, param_value = row
            # Try to parse JSON, otherwise keep as string
            try:
                params[param_name] = json.loads(param_value)
            except (json.JSONDecodeError, TypeError):
                params[param_name] = param_value
        
        return params
    
    # ==================== Artifacts ====================
    
    def log_artifact(self, run_id: str, artifact_name: str, artifact_path: str,
                     artifact_type: Optional[str] = None, size_bytes: Optional[int] = None):
        """
        Log artifact metadata
        
        Args:
            run_id: Run ID
            artifact_name: Artifact name
            artifact_path: Path to artifact file
            artifact_type: Optional artifact type (model, plot, data, etc.)
            size_bytes: Optional file size
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO artifacts (run_id, artifact_name, artifact_path, artifact_type, size_bytes)
            VALUES (?, ?, ?, ?, ?)
        """, (run_id, artifact_name, artifact_path, artifact_type, size_bytes))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"Logged artifact {artifact_name} for run {run_id}")
    
    def get_artifacts(self, run_id: str) -> List[Dict[str, Any]]:
        """Get all artifacts for a run"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at", (run_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
