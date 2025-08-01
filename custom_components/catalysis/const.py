"""Constants for Petivity integration."""

DOMAIN = "petivity"
PLATFORMS = ["sensor"]

# Configuration keys
CONF_JWT = "petivity_jwt"
CONF_CLIENT_ID = "petivity_client_id" 
CONF_REFRESH_TOKEN = "petivity_refresh_token"

# Update intervals
STATUS_UPDATE_INTERVAL = 30  # minutes
WEIGHT_UPDATE_INTERVAL = 24 * 60  # minutes (24 hours)

# Default time windows for weight data
WEIGHT_TIME_WINDOW = 7  # days

# Bundled paths (relative to integration directory)
SCRIPT_RELATIVE_PATH = "bin/catalysis.sh"
QUERIES_RELATIVE_PATH = "queries"