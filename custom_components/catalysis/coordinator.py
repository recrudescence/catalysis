"""Data coordinators for Petivity integration."""
import asyncio
import json
import logging
import os
import stat
import subprocess
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    STATUS_UPDATE_INTERVAL,
    WEIGHT_UPDATE_INTERVAL,
    WEIGHT_TIME_WINDOW,
    CONF_JWT,
    CONF_CLIENT_ID,
    CONF_REFRESH_TOKEN,
    SCRIPT_RELATIVE_PATH,
    QUERIES_RELATIVE_PATH,
)

_LOGGER = logging.getLogger(__name__)

class PetivityCoordinatorBase(DataUpdateCoordinator):
    """Base coordinator for Petivity data."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, update_interval_minutes: int) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        
        # Get integration directory and construct paths
        integration_dir = os.path.dirname(__file__)
        self._script_path = os.path.join(integration_dir, SCRIPT_RELATIVE_PATH)
        self._working_dir = integration_dir
        
        # Ensure script is executable on initialization
        self._ensure_script_executable()
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_coordinator",
            update_interval=timedelta(minutes=update_interval_minutes),
        )
    
    def _ensure_script_executable(self) -> None:
        """Ensure the script has executable permissions."""
        try:
            import stat
            
            if os.path.exists(self._script_path):
                # Get current permissions
                current_permissions = os.stat(self._script_path).st_mode
                
                # Add execute permissions for owner, group, and others
                executable_permissions = current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                
                # Only change if needed
                if current_permissions != executable_permissions:
                    os.chmod(self._script_path, executable_permissions)
                    _LOGGER.info("Made script executable: %s", self._script_path)
                else:
                    _LOGGER.debug("Script already executable: %s", self._script_path)
            else:
                _LOGGER.warning("Script not found at: %s", self._script_path)
        except Exception as err:
            _LOGGER.error("Failed to make script executable: %s", err)
    
    def _get_environment(self) -> Dict[str, str]:
        """Get environment variables for the script."""
        env = os.environ.copy()
        env.update({
            "PETIVITY_JWT": self.entry.data[CONF_JWT],
            "PETIVITY_CLIENT_ID": self.entry.data[CONF_CLIENT_ID], 
            "PETIVITY_REFRESH_TOKEN": self.entry.data[CONF_REFRESH_TOKEN],
        })
        return env
    
    async def _run_catalysis_command(self, command: str, *args) -> Dict[str, Any]:
        """Execute a catalysis command and return parsed JSON."""
        cmd = [self._script_path, command] + list(args)
        env = self._get_environment()
        
        _LOGGER.debug("Executing: %s", " ".join(cmd))
        
        try:
            result = await self.hass.async_add_executor_job(
                self._execute_command, cmd, env
            )
            
            if result.returncode != 0:
                _LOGGER.error(
                    "Command failed with exit code %d: %s", 
                    result.returncode, 
                    result.stderr
                )
                raise UpdateFailed(f"Command failed: {result.stderr}")
            
            # Parse JSON output
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError as err:
                _LOGGER.error("Failed to parse JSON response: %s", result.stdout)
                raise UpdateFailed(f"Invalid JSON response: {err}")
                
        except subprocess.TimeoutExpired:
            _LOGGER.error("Command timed out")
            raise UpdateFailed("Command timed out")
        except Exception as err:
            _LOGGER.error("Command execution failed: %s", err)
            raise UpdateFailed(f"Command execution failed: {err}")
    
    def _execute_command(self, cmd: List[str], env: Dict[str, str]) -> subprocess.CompletedProcess:
        """Execute command synchronously with permission retry."""
        try:
            return subprocess.run(
                cmd,
                cwd=self._working_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except PermissionError:
            # Try to fix permissions and retry once
            _LOGGER.warning("Permission denied, attempting to fix script permissions and retry")
            self._ensure_script_executable()
            
            # Retry the command
            return subprocess.run(
                cmd,
                cwd=self._working_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )

class PetivityStatusCoordinator(PetivityCoordinatorBase):
    """Coordinator for status data (cats and machines)."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize status coordinator."""
        super().__init__(hass, entry, STATUS_UPDATE_INTERVAL)
    
    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch status data."""
        return await self._run_catalysis_command("status")
    
    def get_cats(self) -> List[Dict[str, Any]]:
        """Extract cat information from status data."""
        # Add null check to prevent AttributeError
        if not self.data:
            _LOGGER.debug("No status data available for cats")
            return []
        
        cats = []
        try:
            # Parse actual GraphQL response structure
            cats_data = self.data.get("data", {}).get("authenticate", {}).get("myHousehold", {}).get("cats", [])
            
            for cat in cats_data:
                activity_state = cat.get("activityState", {})
                cats.append({
                    "id": cat.get("id"),
                    "name": cat.get("name"),
                    "most_recent_event": activity_state.get("mostRecentEvent"),
                    "last_activated": activity_state.get("lastActivated"),
                    "cat_not_seen_warning": activity_state.get("catNotSeenWarning", False),
                })
        except (KeyError, TypeError) as err:
            _LOGGER.warning("Failed to extract cat data: %s", err)
        
        return cats
    
    def get_machines(self) -> List[Dict[str, Any]]:
        """Extract machine information from status data."""
        # Add null check to prevent AttributeError
        if not self.data:
            _LOGGER.debug("No status data available for machines")
            return []
        
        machines = []
        try:
            # Parse actual GraphQL response structure  
            machines_data = self.data.get("data", {}).get("authenticate", {}).get("myHousehold", {}).get("machines", [])
            
            for machine in machines_data:
                # Parse elimination events for detailed tracking
                elimination_events = machine.get("eliminationEvents", [])
                
                # Process events for easier access
                processed_events = []
                event_counts = {"urination": 0, "defecation": 0, "combo": 0, "unknown": 0}
                
                for event in elimination_events:
                    classification = event.get("normalisedClassification", {})
                    if classification.get("isCat") and classification.get("isElimination"):
                        elim_type = classification.get("elimType", "unknown")
                        cat_info = classification.get("cat", {})
                        
                        processed_event = {
                            "start_time": event.get("startTime"),
                            "elimination_type": elim_type,
                            "cat_id": cat_info.get("id"),
                        }
                        processed_events.append(processed_event)
                        
                        # Count by type
                        event_counts[elim_type] = event_counts.get(elim_type, 0) + 1
                
                # Get most recent event details
                most_recent_event = processed_events[0] if processed_events else None
                
                machines.append({
                    "id": machine.get("name", "unknown"),  # Using name as ID since no explicit ID field
                    "name": machine.get("name"),
                    "battery_percentage": machine.get("batteryPercentage"),
                    "show_battery_warning": machine.get("showBatteryWarning", False),
                    "wifi_rssi": machine.get("wifiRssi"),
                    "power_mode": machine.get("powerMode"),
                    "is_frozen": machine.get("isFrozen", False),
                    "most_recent_upload": machine.get("mostRecentUploadAt"),
                    "upload_warning": machine.get("mostRecentUploadWarning", False),
                    "is_dirty": machine.get("isDirty", False),
                    "balanced_status": machine.get("balancedStatus"),
                    
                    # Enhanced event tracking
                    "recent_events": processed_events,
                    "recent_event_count": len(processed_events),
                    "event_counts": event_counts,
                    "most_recent_event": most_recent_event,
                    "last_event_time": most_recent_event.get("start_time") if most_recent_event else None,
                    "last_event_type": most_recent_event.get("elimination_type") if most_recent_event else None,
                    "last_event_cat_id": most_recent_event.get("cat_id") if most_recent_event else None,
                })
        except (KeyError, TypeError) as err:
            _LOGGER.warning("Failed to extract machine data: %s", err)
        
        return machines

class PetivityWeightCoordinator(PetivityCoordinatorBase):
    """Coordinator for weight data."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize weight coordinator."""
        super().__init__(hass, entry, WEIGHT_UPDATE_INTERVAL)
        self._cat_weights = {}

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch weight data for all cats."""
        # Get cats from status coordinator with proper error handling
        try:
            status_coordinator = self.hass.data[DOMAIN][self.entry.entry_id]["status_coordinator"]
            cats = status_coordinator.get_cats()
            
            if not cats:
                _LOGGER.warning("No cats found for weight data - status coordinator may not be ready")
                return self._cat_weights or {}  # Return existing data if available
                
        except KeyError as err:
            _LOGGER.error("Status coordinator not found: %s", err)
            return self._cat_weights or {}
        except Exception as err:
            _LOGGER.error("Error accessing status coordinator: %s", err) 
            return self._cat_weights or {}
        
        # Calculate date range (last 7 days)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=WEIGHT_TIME_WINDOW)
        
        weight_data = {}
        successful_updates = 0
        
        for cat in cats:
            cat_id = cat["id"]
            cat_name = cat["name"]
            
            try:
                # Fetch weight data for this cat
                _LOGGER.debug("Fetching weight data for cat %s (%s)", cat_name, cat_id)
                weight_response = await self._run_catalysis_command(
                    "weight",
                    cat_id,
                    start_date.isoformat(),
                    end_date.isoformat(),
                    "DAY"
                )
                
                # Extract current weight (most recent data point)
                current_weight = self._extract_current_weight(weight_response, cat_name)
                
                weight_data[cat_id] = {
                    "cat_name": cat_name,
                    "current_weight": current_weight,
                    "raw_data": weight_response,
                    "last_updated": datetime.now().isoformat(),
                }
                
                successful_updates += 1
                _LOGGER.debug("Successfully updated weight for cat %s: %s lbs", cat_name, current_weight)
                
            except Exception as err:
                _LOGGER.error("Failed to fetch weight data for cat %s: %s", cat_name, err)
                # Keep previous data if available
                if cat_id in self._cat_weights:
                    weight_data[cat_id] = self._cat_weights[cat_id]
                    _LOGGER.debug("Keeping previous weight data for cat %s", cat_name)
        
        _LOGGER.debug("Weight coordinator updated data for %d/%d cats", successful_updates, len(cats))
        self._cat_weights = weight_data
        return weight_data
    
    def _extract_current_weight(self, weight_response: Dict, cat_name: str) -> Optional[float]:
        """Extract current weight from GraphQL response."""
        try:
            # Parse actual GraphQL response structure
            cat_data = weight_response.get("data", {}).get("authenticate", {}).get("node", {})
            weight_data = cat_data.get("aggregatedEvents", {}).get("weight", [])
            
            # Get the most recent weight measurement (last item in array)
            if weight_data:
                latest_measurement = weight_data[-1]
                weight_grams = latest_measurement.get("mean")
                
                if weight_grams is not None:
                    # Convert grams to pounds (1 gram = 0.00220462 pounds)
                    weight_pounds = weight_grams * 0.00220462
                    return round(weight_pounds, 2)
            
        except (KeyError, TypeError, IndexError) as err:
            _LOGGER.warning("Failed to extract weight for cat %s: %s", cat_name, err)
        
        return None
    
    def get_cat_weight(self, cat_id: str) -> Optional[float]:
        """Get current weight for a specific cat."""
        if cat_id in self._cat_weights:
            return self._cat_weights[cat_id].get("current_weight")
        return None
    
    def get_cat_name(self, cat_id: str) -> Optional[str]:
        """Get cat name for a specific cat ID."""
        if cat_id in self._cat_weights:
            return self._cat_weights[cat_id].get("cat_name")
        return None