import datetime
import os
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, 
    create_engine, Engine, UniqueConstraint, inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import NullPool

Base = declarative_base()

class DagRun(Base):
    """Tracks a single execution of an entire workflow/DAG"""
    __tablename__ = 'dag_runs'
    
    id = Column(Integer, primary_key=True)
    dag_id = Column(String(250), nullable=False)
    run_id = Column(String(250), unique=True, nullable=False)
    status = Column(String(50), nullable=False, default="running")
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime, nullable=True)

class TaskInstance(Base):
    """Tracks a single execution of a specific task within a DagRun"""
    __tablename__ = 'task_instances'
    __table_args__ = (UniqueConstraint('run_id', 'task_id', name='_run_task_uc'),)
    
    id = Column(Integer, primary_key=True)
    task_id = Column(String(250), nullable=False)
    dag_id = Column(String(250), nullable=False)
    run_id = Column(String(250), nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    execution_time = Column(Float, nullable=True)
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    attempt_count = Column(Integer, default=1)
    error_trace = Column(Text, nullable=True)
    worker_id = Column(String(250), nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)

class XCom(Base):
    """Tracks data passed between tasks (Cross-Communication)"""
    __tablename__ = 'xcom'
    __table_args__ = (
        UniqueConstraint('run_id', 'task_id', 'key', name='_run_task_key_uc'),
    )
    
    id = Column(Integer, primary_key=True)
    task_id = Column(String(250), nullable=False)
    dag_id = Column(String(250), nullable=False)
    run_id = Column(String(250), nullable=False)
    key = Column(String(250), nullable=False)
    value = Column(Text, nullable=True) # Stored as JSON string
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class Log(Base):
    """Stores workflow and task logs"""
    __tablename__ = 'logs'
    
    id = Column(Integer, primary_key=True)
    dag_id = Column(String(250), nullable=True)
    task_id = Column(String(250), nullable=True)
    run_id = Column(String(250), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    level = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)

class DatabaseSession:
    """Manages the database connection and sessions"""
    def __init__(self, db_url: Optional[str] = None):
        db_url = db_url or os.getenv("AIRFLAN_DATABASE_URL") or os.getenv("AIRFLAN_DB_URL")
        if not db_url:
            # Default to a local SQLite database in the current working directory
            db_path = Path.cwd() / "airflan_metadata.db"
            db_url = f"sqlite:///{db_path}"
        self.db_url = db_url
            
        connect_args = {}
        if db_url.startswith("sqlite"):
            # Enable multithreading and high timeouts for SQLite to prevent 'database locked'
            connect_args = {'check_same_thread': False, 'timeout': 15}
            
        self.engine: Engine = create_engine(db_url, echo=False, connect_args=connect_args, poolclass=NullPool)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
    def init_db(self):
        """Creates all tables if they don't exist"""
        Base.metadata.create_all(bind=self.engine)
        self._add_missing_columns()
        
    def get_session(self) -> Session:
        """Returns a new database session"""
        return self.SessionLocal()

    def _add_missing_columns(self) -> None:
        """Apply small compatibility migrations for existing local metadata DBs."""
        inspector = inspect(self.engine)
        if "task_instances" not in inspector.get_table_names():
            return

        existing_columns = {
            column["name"]
            for column in inspector.get_columns("task_instances")
        }
        column_definitions = {
            "worker_id": "VARCHAR(250)",
            "heartbeat_at": "DATETIME",
        }

        with self.engine.begin() as connection:
            for column_name, column_type in column_definitions.items():
                if column_name not in existing_columns:
                    connection.execute(
                        text(f"ALTER TABLE task_instances ADD COLUMN {column_name} {column_type}")
                    )
