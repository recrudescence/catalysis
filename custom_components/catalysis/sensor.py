"""Sensor platform for Petivity integration."""
from datetime import datetime
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfMass

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Petivity sensors."""
    coordinators = hass.data[DOMAIN][config_entry.entry_id]
    status_coordinator = coordinators["status_coordinator"]
    weight_coordinator = coordinators["weight_coordinator"]
    
    entities = []
    
    # Dynamically create cat sensors based on discovered cats
    cats = status_coordinator.get_cats()
    for cat in cats:
        cat_id = cat["id"]
        entities.extend([
            PetivityCatActivitySensor(status_coordinator, config_entry, cat_id),
            PetivityCatWeightSensor(weight_coordinator, config_entry, cat_id),
        ])
    
    # Dynamically create machine sensors based on discovered machines  
    machines = status_coordinator.get_machines()
    for machine in machines:
        machine_id = machine["id"]
        entities.extend([
            PetivityMachineStatusSensor(status_coordinator, config_entry, machine_id),
            PetivityMachineEventCountSensor(status_coordinator, config_entry, machine_id),
            PetivityMachineLastEventSensor(status_coordinator, config_entry, machine_id),
        ])
        
        # Only add battery sensor if machine has battery (not AC powered)
        if machine.get("battery_percentage") is not None:
            entities.append(
                PetivityMachineBatterySensor(status_coordinator, config_entry, machine_id)
            )
    
    async_add_entities(entities)

class PetivitySensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Petivity sensors."""
    
    def __init__(self, coordinator, config_entry: ConfigEntry, sensor_type: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{config_entry.entry_id}_{sensor_type}"
        
    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": "Petivity System",
            "manufacturer": "Petivity",
            "sw_version": "1.0.0",
        }

class PetivityCatCountSensor(PetivitySensorBase):
    """Sensor for number of cats."""
    
    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize cat count sensor."""
        super().__init__(coordinator, config_entry, "cat_count")
        self._attr_name = "Petivity Cat Count"
        self._attr_icon = "mdi:cat"
    
    @property
    def native_value(self) -> Optional[int]:
        """Return the number of cats."""
        cats = self.coordinator.get_cats()
        return len(cats) if cats else None

class PetivityMachineCountSensor(PetivitySensorBase):
    """Sensor for number of machines."""
    
    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize machine count sensor."""
        super().__init__(coordinator, config_entry, "machine_count")
        self._attr_name = "Petivity Machine Count"
        self._attr_icon = "mdi:devices"
    
    @property
    def native_value(self) -> Optional[int]:
        """Return the number of machines."""
        machines = self.coordinator.get_machines()
        return len(machines) if machines else None

class PetivityMachineStatusSensor(PetivitySensorBase):
    """Sensor for individual machine status."""
    
    def __init__(self, coordinator, config_entry: ConfigEntry, machine_id: str) -> None:
        """Initialize machine status sensor."""
        self._machine_id = machine_id
        super().__init__(coordinator, config_entry, f"machine_{machine_id.lower().replace(' ', '_')}_status")
        self._attr_icon = "mdi:litter-box"
    
    @property
    def name(self) -> Optional[str]:
        """Return sensor name."""
        machines = self.coordinator.get_machines()
        for machine in machines:
            if machine["id"] == self._machine_id:
                return f"Petivity {machine.get('name', 'Machine')} Status"
        return f"Petivity Machine {self._machine_id} Status"
    
    @property
    def native_value(self) -> Optional[str]:
        """Return machine status."""
        machines = self.coordinator.get_machines()
        for machine in machines:
            if machine["id"] == self._machine_id:
                # Create a status based on multiple factors
                status_parts = []
                
                if machine.get("is_frozen"):
                    status_parts.append("FROZEN")
                elif machine.get("upload_warning"):
                    status_parts.append("UPLOAD_WARNING")
                elif machine.get("show_battery_warning"):
                    status_parts.append("LOW_BATTERY")
                elif machine.get("is_dirty"):
                    status_parts.append("NEEDS_CLEANING")
                else:
                    status_parts.append("NORMAL")
                
                # Add power mode
                power_mode = machine.get("power_mode", "UNKNOWN")
                status_parts.append(power_mode)
                
                return " | ".join(status_parts)
        return None
    
    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return additional attributes."""
        machines = self.coordinator.get_machines()
        for machine in machines:
            if machine["id"] == self._machine_id:
                attrs = {
                    "machine_id": machine["id"],
                    "name": machine.get("name"),
                    "battery_percentage": machine.get("battery_percentage"),
                    "power_mode": machine.get("power_mode"),
                    "wifi_rssi": machine.get("wifi_rssi"),
                    "is_dirty": machine.get("is_dirty"),
                    "is_frozen": machine.get("is_frozen"),
                    "balanced_status": machine.get("balanced_status"),
                    "most_recent_upload": machine.get("most_recent_upload"),
                    "recent_events_today": machine.get("recent_event_count", 0),
                    "last_event_time": machine.get("recent_event_time"),
                }
                
                # Only include battery percentage if it exists (some machines are AC powered)
                if machine.get("battery_percentage") is not None:
                    attrs["battery_level"] = machine["battery_percentage"]
                
                return attrs
        return None

class PetivityCatWeightSensor(PetivitySensorBase):
    """Sensor for cat weight."""
    
    def __init__(self, coordinator, config_entry: ConfigEntry, cat_id: str) -> None:
        """Initialize cat weight sensor."""
        self._cat_id = cat_id
        super().__init__(coordinator, config_entry, f"cat_{cat_id}_weight")
        self._attr_device_class = SensorDeviceClass.WEIGHT
        self._attr_native_unit_of_measurement = UnitOfMass.POUNDS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:scale"
    
    @property
    def name(self) -> Optional[str]:
        """Return sensor name."""
        cat_name = self.coordinator.get_cat_name(self._cat_id)
        if cat_name:
            return f"{cat_name} Weight"
        return f"Cat {self._cat_id} Weight"
    
    @property
    def native_value(self) -> Optional[float]:
        """Return cat weight."""
        return self.coordinator.get_cat_weight(self._cat_id)
    
    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return additional attributes."""
        if self._cat_id in self.coordinator._cat_weights:
            weight_data = self.coordinator._cat_weights[self._cat_id]
            return {
                "cat_id": self._cat_id,
                "cat_name": weight_data.get("cat_name"),
                "last_updated": weight_data.get("last_updated"),
                "data_source": "petivity_api",
                "unit": "pounds",
                "original_unit": "grams",
            }
        return None
    
    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        return self.coordinator.get_cat_weight(self._cat_id) is not None

class PetivityCatActivitySensor(PetivitySensorBase):
    """Sensor for cat activity status."""
    
    def __init__(self, coordinator, config_entry: ConfigEntry, cat_id: str) -> None:
        """Initialize cat activity sensor."""
        self._cat_id = cat_id
        super().__init__(coordinator, config_entry, f"cat_{cat_id}_activity")
        self._attr_icon = "mdi:cat"
    
    @property
    def name(self) -> Optional[str]:
        """Return sensor name."""
        cats = self.coordinator.get_cats()
        for cat in cats:
            if cat["id"] == self._cat_id:
                return f"{cat['name']} Activity"
        return f"Cat {self._cat_id} Activity"
    
    @property
    def native_value(self) -> Optional[str]:
        """Return cat activity status."""
        cats = self.coordinator.get_cats()
        for cat in cats:
            if cat["id"] == self._cat_id:
                if cat.get("cat_not_seen_warning"):
                    return "Not Seen"
                elif cat.get("most_recent_event"):
                    return "Active"
                else:
                    return "Unknown"
        return None
    
    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return additional attributes."""
        cats = self.coordinator.get_cats()
        for cat in cats:
            if cat["id"] == self._cat_id:
                return {
                    "cat_id": self._cat_id,
                    "cat_name": cat.get("name"),
                    "most_recent_event": cat.get("most_recent_event"),
                    "last_activated": cat.get("last_activated"),
                    "not_seen_warning": cat.get("cat_not_seen_warning", False),
                }
        return None

class PetivityMachineBatterySensor(PetivitySensorBase):
    """Sensor for machine battery level."""
    
    def __init__(self, coordinator, config_entry: ConfigEntry, machine_id: str) -> None:
        """Initialize machine battery sensor."""
        self._machine_id = machine_id
        super().__init__(coordinator, config_entry, f"machine_{machine_id.lower().replace(' ', '_')}_battery")
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = "%"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:battery"
    
    @property
    def name(self) -> Optional[str]:
        """Return sensor name."""
        machines = self.coordinator.get_machines()
        for machine in machines:
            if machine["id"] == self._machine_id:
                return f"Petivity {machine.get('name', 'Machine')} Battery"
        return f"Petivity Machine {self._machine_id} Battery"
    
    @property
    def native_value(self) -> Optional[int]:
        """Return battery percentage."""
        machines = self.coordinator.get_machines()
        for machine in machines:
            if machine["id"] == self._machine_id:
                return machine.get("battery_percentage")
        return None
    
    @property
    def available(self) -> bool:
        """Return if sensor is available (only for battery-powered machines)."""
        machines = self.coordinator.get_machines()
        for machine in machines:
            if machine["id"] == self._machine_id:
                return machine.get("battery_percentage") is not None
        return False

class PetivityMachineEventCountSensor(PetivitySensorBase):
    """Sensor for machine recent event count."""
    
    def __init__(self, coordinator, config_entry: ConfigEntry, machine_id: str) -> None:
        """Initialize machine event count sensor."""
        self._machine_id = machine_id
        super().__init__(coordinator, config_entry, f"machine_{machine_id.lower().replace(' ', '_')}_events")
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:counter"
    
    @property
    def name(self) -> Optional[str]:
        """Return sensor name."""
        machines = self.coordinator.get_machines()
        for machine in machines:
            if machine["id"] == self._machine_id:
                return f"Petivity {machine.get('name', 'Machine')} Recent Events"
        return f"Petivity Machine {self._machine_id} Recent Events"
    
    @property
    def native_value(self) -> Optional[int]:
        """Return recent event count."""
        machines = self.coordinator.get_machines()
        for machine in machines:
            if machine["id"] == self._machine_id:
                return machine.get("recent_event_count", 0)
        return None
    
    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return additional attributes."""
        machines = self.coordinator.get_machines()
        for machine in machines:
            if machine["id"] == self._machine_id:
                return {
                    "machine_id": machine["id"],
                    "machine_name": machine.get("name"),
                    "last_event_time": machine.get("recent_event_time"),
                    "time_period": "recent_eliminations",
                }
        return None

class PetivityMachineLastEventSensor(PetivitySensorBase):
    """Sensor for machine's last elimination event details."""
    
    def __init__(self, coordinator, config_entry: ConfigEntry, machine_id: str) -> None:
        """Initialize machine last event sensor."""
        self._machine_id = machine_id
        super().__init__(coordinator, config_entry, f"machine_{machine_id.lower().replace(' ', '_')}_last_event")
        self._attr_icon = "mdi:information"
    
    @property
    def name(self) -> Optional[str]:
        """Return sensor name."""
        machines = self.coordinator.get_machines()
        for machine in machines:
            if machine["id"] == self._machine_id:
                return f"Petivity {machine.get('name', 'Machine')} Last Event"
        return f"Petivity Machine {self._machine_id} Last Event"
    
    @property
    def native_value(self) -> Optional[str]:
        """Return last event type."""
        machines = self.coordinator.get_machines()
        for machine in machines:
            if machine["id"] == self._machine_id:
                event_type = machine.get("last_event_type")
                if event_type:
                    return event_type.title()  # Capitalize first letter
                return "None"
        return None
    
    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return detailed event information."""
        machines = self.coordinator.get_machines()
        for machine in machines:
            if machine["id"] == self._machine_id:
                # Get cat name for the last event
                cat_name = "Unknown"
                if machine.get("last_event_cat_id"):
                    cats = self.coordinator.get_cats()
                    for cat in cats:
                        if cat["id"] == machine["last_event_cat_id"]:
                            cat_name = cat["name"]
                            break
                
                return {
                    "machine_id": machine["id"],
                    "machine_name": machine.get("name"),
                    "last_event_time": machine.get("last_event_time"),
                    "last_event_type": machine.get("last_event_type"),
                    "last_event_cat": cat_name,
                    "last_event_cat_id": machine.get("last_event_cat_id"),
                    
                    # Event counts by type
                    "urination_count": machine.get("event_counts", {}).get("urination", 0),
                    "defecation_count": machine.get("event_counts", {}).get("defecation", 0),
                    "combo_count": machine.get("event_counts", {}).get("combo", 0),
                    "unknown_count": machine.get("event_counts", {}).get("unknown", 0),
                    "total_events": machine.get("recent_event_count", 0),
                    
                    # All recent events (limited to last 10 for performance)
                    "recent_events": machine.get("recent_events", [])[:10],
                }
        return None
    
    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        machines = self.coordinator.get_machines()
        for machine in machines:
            if machine["id"] == self._machine_id:
                return machine.get("recent_event_count", 0) > 0
        return False
    
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
