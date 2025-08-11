"""Petivity integration for Home Assistant."""
import asyncio
import logging
from datetime import timedelta

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

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
    
    # Fetch initial data
    await status_coordinator.async_config_entry_first_refresh()
    
    # Store coordinators
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "status_coordinator": status_coordinator,
        "weight_coordinator": weight_coordinator,
    }
    
    # Register services
    async def get_weight_history(call):
        """Service to get historical weight data for a cat."""
        cat_id = call.data.get("cat_id")
        days = call.data.get("days", 30)
        
        try:
            historical_data = await weight_coordinator.async_get_historical_weight(cat_id, days)
            
            # Return data via event for the frontend to consume
            hass.bus.async_fire(
                f"{DOMAIN}_weight_history_response",
                {
                    "cat_id": cat_id,
                    "days": days,
                    "data": historical_data,
                    "request_id": call.data.get("request_id", ""),
                }
            )
            
        except Exception as err:
            _LOGGER.error("Failed to get weight history: %s", err)
            hass.bus.async_fire(
                f"{DOMAIN}_weight_history_error",
                {
                    "cat_id": cat_id,
                    "error": str(err),
                    "request_id": call.data.get("request_id", ""),
                }
            )
    
    # Register the service
    hass.services.async_register(
        DOMAIN,
        "get_weight_history",
        get_weight_history,
        schema=vol.Schema({
            vol.Required("cat_id"): cv.string,
            vol.Optional("days", default=30): cv.positive_int,
            vol.Optional("request_id", default=""): cv.string,
        })
    )
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Remove services
        hass.services.async_remove(DOMAIN, "get_weight_history")
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
