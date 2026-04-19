from __future__ import annotations
import json
import uuid
from pathlib import Path
import datetime
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field
from typing import List, Dict, Any

# Asumimos una base de datos en memoria para el placeholder
MEMORY_DB: List[Dict[str, Any]] = []

class MemoryItem(BaseModel):
    memory_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    layer: int
    type: str # e.g., "STEP", "OBSERVATION"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(ZoneInfo("UTC")).isoformat())

async def ingest_event(event_type: str, content: str, source: str, *args, **kwargs) -> str:
    """
    Ingests an event into memory. Handles diff events specifically.
    Implements SPEC-3.2.
    """
    if event_type.startswith("diff_"):
        try:
            diff_data = json.loads(content)
            layer = 1 # Working Memory
            mem_type = "STEP"
            metadata = {
                "source": source,
                "event_type": event_type,
                "file_path": diff_data.get("file_path"),
                "language": diff_data.get("language"),
                "change_id": diff_data.get("change_id"),
            }
            
            mem_item = MemoryItem(
                content=json.dumps(diff_data.get("diff_text")),
                layer=layer,
                type=mem_type,
                metadata=metadata
            )
            
            MEMORY_DB.append(mem_item.model_dump())
            
            return json.dumps({"status": "ingested", "memory_id": mem_item.memory_id})

        except json.JSONDecodeError as e:
            return json.dumps({"status": "error", "message": f"Invalid JSON content for diff event: {e}"})
    
    # Placeholder for other event types
    return json.dumps({"status": "ignored", "reason": "Event type not a diff event"})

async def get_memory_db() -> str:
    """Helper for testing to inspect the in-memory DB."""
    return json.dumps(MEMORY_DB)
