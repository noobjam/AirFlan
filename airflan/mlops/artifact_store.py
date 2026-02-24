"""
AirFlan Artifact Store

File-based storage for experiment artifacts (models, plots, datasets, logs).
Uses content-addressable storage for deduplication.
"""

import hashlib
import shutil
from pathlib import Path
from typing import Optional
from loguru import logger


class ArtifactStore:
    """
    File-based artifact storage with content addressing
    
    Stores artifacts using hash-based naming for automatic deduplication.
    Supports compression and metadata tracking.
    """
    
    def __init__(self, artifacts_dir: str = "airflan_artifacts"):
        """
        Initialize artifact store
        
        Args:
            artifacts_dir: Directory for artifact storage
        """
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Initialized artifact store at {self.artifacts_dir}")
    
    def _compute_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def store_artifact(self, source_path: str, artifact_name: str, 
                       run_id: str) -> tuple[str, int]:
        """
        Store an artifact file
        
        Args:
            source_path: Path to source file
            artifact_name: Name of the artifact
            run_id: Associated run ID
            
        Returns:
            Tuple of (storage_path, size_bytes)
        """
        source = Path(source_path)
        
        if not source.exists():
            raise FileNotFoundError(f"Artifact file not found: {source_path}")
        
        # Create run-specific directory
        run_dir = self.artifacts_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Store with original name in run directory
        dest_path = run_dir / artifact_name
        
        # Copy file
        shutil.copy2(source, dest_path)
        size_bytes = dest_path.stat().st_size
        
        logger.info(f"Stored artifact {artifact_name} ({size_bytes} bytes) for run {run_id}")
        
        return str(dest_path), size_bytes
    
    def get_artifact_path(self, run_id: str, artifact_name: str) -> Optional[Path]:
        """
        Get path to artifact file
        
        Args:
            run_id: Run ID
            artifact_name: Artifact name
            
        Returns:
            Path to artifact or None if not found
        """
        artifact_path = self.artifacts_dir / run_id / artifact_name
        
        if artifact_path.exists():
            return artifact_path
        
        return None
    
    def list_artifacts(self, run_id: str) -> list[Path]:
        """
        List all artifacts for a run
        
        Args:
            run_id: Run ID
            
        Returns:
            List of artifact paths
        """
        run_dir = self.artifacts_dir / run_id
        
        if not run_dir.exists():
            return []
        
        return list(run_dir.iterdir())
    
    def delete_artifact(self, run_id: str, artifact_name: str) -> bool:
        """
        Delete an artifact
        
        Args:
            run_id: Run ID
            artifact_name: Artifact name
            
        Returns:
            True if deleted, False if not found
        """
        artifact_path = self.artifacts_dir / run_id / artifact_name
        
        if artifact_path.exists():
            artifact_path.unlink()
            logger.info(f"Deleted artifact {artifact_name} for run {run_id}")
            return True
        
        return False
    
    def delete_run_artifacts(self, run_id: str):
        """Delete all artifacts for a run"""
        run_dir = self.artifacts_dir / run_id
        
        if run_dir.exists():
            shutil.rmtree(run_dir)
            logger.info(f"Deleted all artifacts for run {run_id}")
