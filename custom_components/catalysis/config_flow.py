"""Config flow for Petivity integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class PetivityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Petivity."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(
                title="Petivity Pet Monitoring",
                data=user_input
            )

        data_schema = vol.Schema({
            # vol.Required("petivity_jwt"): cv.string,
            vol.Required("petivity_client_id"): cv.string,
            vol.Required("petivity_refresh_token"): cv.string,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
        )