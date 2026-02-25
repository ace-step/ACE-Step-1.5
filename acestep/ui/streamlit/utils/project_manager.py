"""
Project management for ACE Studio
Handles saving, loading, and organizing music projects
"""
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from loguru import logger
from config import PROJECTS_DIR


@dataclass
class ProjectMetadata:
    """Metadata for a music project"""
    name: str
    created_at: str  # ISO format
    modified_at: str  # ISO format
    description: str = ""
    genre: str = ""
    mood: str = ""
    bpm: Optional[int] = None
    duration: Optional[int] = None  # seconds
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class ProjectManager:
    """Manage music projects (save, load, organize)"""
    
    def __init__(self, projects_dir: Path = PROJECTS_DIR):
        self.projects_dir = projects_dir
        self.projects_dir.mkdir(exist_ok=True)
    
    def create_project(self, name: str, description: str = "") -> Path:
        """Create a new project folder"""
        project_path = self.projects_dir / name
        project_path.mkdir(exist_ok=True)
        
        # Create metadata file
        metadata = ProjectMetadata(
            name=name,
            created_at=datetime.now().isoformat(),
            modified_at=datetime.now().isoformat(),
            description=description,
        )
        self._save_metadata(project_path, metadata)
        
        logger.info(f"Created project: {name} at {project_path}")
        return project_path
    
    def get_project(self, name: str) -> Optional[Path]:
        """Get project path by name"""
        project_path = self.projects_dir / name
        if project_path.exists():
            return project_path
        return None
    
    def list_projects(self) -> List[Dict]:
        """List all projects with metadata"""
        projects = []
        for project_path in self.projects_dir.iterdir():
            if project_path.is_dir():
                metadata = self._load_metadata(project_path)
                if metadata:
                    projects.append({
                        "path": str(project_path),
                        "name": project_path.name,
                        **asdict(metadata),
                    })
        
        # Sort by modified date (newest first)
        projects.sort(key=lambda p: p["modified_at"], reverse=True)
        return projects
    
    def save_metadata(self, project_path: Path, **kwargs) -> None:
        """Update project metadata"""
        metadata = self._load_metadata(project_path) or ProjectMetadata(
            name=project_path.name,
            created_at=datetime.now().isoformat(),
            modified_at=datetime.now().isoformat(),
        )
        
        # Update with provided kwargs
        for key, value in kwargs.items():
            if hasattr(metadata, key):
                setattr(metadata, key, value)
        
        metadata.modified_at = datetime.now().isoformat()
        self._save_metadata(project_path, metadata)
    
    def save_audio(self, project_path: Path, audio_data: bytes, filename: str = "output.wav") -> Path:
        """Save audio file to project"""
        audio_path = project_path / filename
        with open(audio_path, "wb") as f:
            f.write(audio_data)
        
        self.save_metadata(project_path)  # Update modified_at
        return audio_path
    
    def get_audio_files(self, project_path: Path) -> List[Path]:
        """Get all audio files in project"""
        audio_extensions = [".wav", ".mp3", ".m4a", ".flac"]
        return [
            f for f in project_path.iterdir()
            if f.suffix.lower() in audio_extensions
        ]
    
    def delete_project(self, name: str) -> bool:
        """Delete a project"""
        project_path = self.projects_dir / name
        if project_path.exists():
            shutil.rmtree(project_path)
            logger.info(f"Deleted project: {name}")
            return True
        return False
    
    def _save_metadata(self, project_path: Path, metadata: ProjectMetadata) -> None:
        """Save metadata JSON file"""
        metadata_path = project_path / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(asdict(metadata), f, indent=2)
    
    def _load_metadata(self, project_path: Path) -> Optional[ProjectMetadata]:
        """Load metadata JSON file"""
        metadata_path = project_path / "metadata.json"
        if metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    data = json.load(f)
                    return ProjectMetadata(**data)
            except Exception as e:
                logger.error(f"Failed to load metadata from {metadata_path}: {e}")
        return None
