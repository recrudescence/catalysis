"""Petivity integration for Home Assistant."""
import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, PLATFORMS
from .coordinator import PetivityStatusCoordinator, PetivityWeightCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Petivity from a config entry."""
    
    # Create coordinators
    status_coordinator = PetivityStatusCoordinator(hass, entry)
    weight_coordinator = PetivityWeightCoordinator(hass, entry)
    
    try:
        # Fetch initial data for status coordinator first (weight coordinator depends on it)
        _LOGGER.debug("Fetching initial status data...")
        await status_coordinator.async_config_entry_first_refresh()
        
        # Store coordinators early so weight coordinator can access status data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "status_coordinator": status_coordinator,
            "weight_coordinator": weight_coordinator,
        }
        
        # Now fetch initial weight data
        _LOGGER.debug("Fetching initial weight data...")
        await weight_coordinator.async_config_entry_first_refresh()
        
    except Exception as err:
        _LOGGER.error("Failed to fetch initial data: %s", err)
        raise ConfigEntryNotReady(f"Failed to fetch initial data: {err}")
    
    # Verify we have some basic data
    cats = status_coordinator.get_cats()
    if not cats:
        _LOGGER.warning("No cats found in status data")
    else:
        _LOGGER.info("Found %d cats: %s", len(cats), [cat.get("name", "Unknown") for cat in cats])
    
    machines = status_coordinator.get_machines()
    if not machines:
        _LOGGER.warning("No machines found in status data")
    else:
        _LOGGER.info("Found %d machines: %s", len(machines), [machine.get("name", "Unknown") for machine in machines])
    
    try:
        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception as err:
        _LOGGER.error("Failed to set up platforms: %s", err)
        raise ConfigEntryNotReady(f"Failed to set up platforms: {err}")
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok