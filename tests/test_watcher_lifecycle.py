import os
import time
import asyncio
import pytest
from datetime import datetime, timezone
from services.file_watcher import WatcherService

@pytest.mark.anyio
async def test_watcher_lifecycle_states(tmp_path):
    # Setup test directories
    incoming = str(tmp_path / "incoming")
    final = str(tmp_path / "final")
    os.makedirs(incoming, exist_ok=True)
    os.makedirs(final, exist_ok=True)
    
    project_id = "test_project_lifecycle"
    
    # 1. Start watcher
    WatcherService.start_watcher(project_id, incoming, final)
    
    # Allow start task to run
    await asyncio.sleep(0.1)
    
    state = WatcherService.get_state(project_id)
    assert state["status"] in ["RUNNING", "STARTING"]
    
    # Ensure it reaches RUNNING
    for _ in range(10):
        if state["status"] == "RUNNING":
            break
        await asyncio.sleep(0.1)
    assert state["status"] == "RUNNING"
    
    # Check metadata initialized
    meta = WatcherService._watcher_metadata.get(project_id)
    assert meta is not None
    assert meta["retry_count"] == 0
    assert meta["last_heartbeat"] > 0
    
    # 2. Simulate Heartbeat Timeout (UNHEALTHY status triggers recovery restart)
    meta["suspend_heartbeat"] = True
    meta["last_heartbeat"] = datetime.now(timezone.utc).timestamp() - 10.0
    
    # Wait for monitor loop to tick, detect unhealthy, and trigger a restart
    for _ in range(30):
        if meta["retry_count"] > 0:
            break
        await asyncio.sleep(0.1)
    assert meta["retry_count"] >= 1
    
    # Wait to go back to RUNNING (which resets retry_count to 0)
    for _ in range(30):
        if state["status"] == "RUNNING" and meta["retry_count"] == 0:
            break
        await asyncio.sleep(0.1)
    assert state["status"] == "RUNNING"
    assert meta["retry_count"] == 0
    
    # Restore heartbeat suspension for subsequent crash test
    meta["suspend_heartbeat"] = False
    
    # 3. Simulate Task Crash & Recovery
    # Get active task
    old_task = WatcherService._active_tasks.get(project_id)
    assert old_task is not None
    
    # Cancel the active watch loop task
    old_task.cancel()
    
    # Wait for monitor to detect crash and assign a new task to _active_tasks
    for _ in range(40):
        current_task = WatcherService._active_tasks.get(project_id)
        if current_task is not None and current_task is not old_task:
            break
        await asyncio.sleep(0.1)
        
    new_task = WatcherService._active_tasks.get(project_id)
    assert new_task is not None
    assert new_task is not old_task
    
    # Clean shutdown
    WatcherService.stop_watcher(project_id)
    assert state["status"] == "STOPPED"

@pytest.mark.anyio
async def test_watcher_retry_threshold(tmp_path):
    incoming = str(tmp_path / "incoming")
    final = str(tmp_path / "final")
    os.makedirs(incoming, exist_ok=True)
    os.makedirs(final, exist_ok=True)
    
    project_id = "test_project_retry_limit"
    
    # Start watcher
    WatcherService.start_watcher(project_id, incoming, final)
    await asyncio.sleep(0.1)
    
    state = WatcherService.get_state(project_id)
    meta = WatcherService._watcher_metadata.get(project_id)
    
    # Wait to reach RUNNING
    for _ in range(10):
        if state["status"] == "RUNNING":
            break
        await asyncio.sleep(0.1)
    assert state["status"] == "RUNNING"
    
    # Set retry count to 3 to simulate threshold reached
    meta["retry_count"] = 3
    
    # Cancel loop task to trigger recovery check
    task = WatcherService._active_tasks.get(project_id)
    task.cancel()
    
    # Wait for monitor loop to detect and set ERROR state
    for _ in range(20):
        if state["status"] == "ERROR":
            break
        await asyncio.sleep(0.1)
        
    assert state["status"] == "ERROR"
    
    # Clean shutdown
    WatcherService.stop_watcher(project_id)
    assert state["status"] == "STOPPED"
