"""Config flow for Petivity integration."""
import logging
import os
import subprocess
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_SCRIPT_PATH,
    CONF_WORKING_DIR,
    CONF_JWT,
    CONF_CLIENT_ID,
    CONF_REFRESH_TOKEN,
)

_LOGGER = logging.getLogger(__name__)

class PetivityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Petivity."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            # Validate script and working directory
            script_path = user_input[CONF_SCRIPT_PATH]
            working_dir = user_input[CONF_WORKING_DIR]
            
            if not await self._validate_setup(script_path, working_dir):
                errors["base"] = "invalid_setup"
            else:
                return self.async_create_entry(
                    title="Petivity Pet Monitoring",
                    data=user_input
                )

        data_schema = vol.Schema({
            vol.Required(CONF_SCRIPT_PATH): cv.string,
            vol.Required(CONF_WORKING_DIR): cv.string,
            vol.Required(CONF_JWT): cv.string,
            vol.Required(CONF_CLIENT_ID): cv.string,
            vol.Required(CONF_REFRESH_TOKEN): cv.string,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "script_example": "/path/to/catalysis",
                "working_dir_example": "/path/to/directory/with/queries",
            }
        )

    async def _validate_setup(self, script_path: str, working_dir: str) -> bool:
        """Validate the script and working directory setup."""
        # Check if script exists and is executable
        if not os.path.isfile(script_path) or not os.access(script_path, os.X_OK):
            _LOGGER.error("Script not found or not executable: %s", script_path)
            return False
        
        # Check if working directory exists
        if not os.path.isdir(working_dir):
            _LOGGER.error("Working directory not found: %s", working_dir)
            return False
        
        # Check if queries directory exists
        queries_dir = os.path.join(working_dir, "queries")
        if not os.path.isdir(queries_dir):
            _LOGGER.error("Queries directory not found: %s", queries_dir)
            return False
        
        # Check for required GraphQL files
        required_files = [
            "status.graphql",
            "cat-weight.graphql", 
        ]
        
        for file_name in required_files:
            file_path = os.path.join(queries_dir, file_name)
            if not os.path.isfile(file_path):
                _LOGGER.error("Required GraphQL file not found: %s", file_path)
                return False
        
        return True
