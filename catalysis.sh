#!/bin/zsh

# Check if required environment variables are set
if [[ -z "$PETIVITY_JWT" || -z "$PETIVITY_CLIENT_ID" || -z "$PETIVITY_REFRESH_TOKEN" ]]; then
    echo "Error: Required environment variables not set."
    echo "Please set:"
    echo "  export PETIVITY_JWT=\"your_jwt_token\""
    echo "  export PETIVITY_CLIENT_ID=\"your_client_id\""
    echo "  export PETIVITY_REFRESH_TOKEN=\"your_refresh_token\""
    exit 1
fi

# Global dry run flag
DRY_RUN=false


# Token refresh function
refresh_token() {
    if [[ -z "$PETIVITY_REFRESH_TOKEN" ]]; then
        echo "Error: PETIVITY_REFRESH_TOKEN not set. Cannot refresh token."
        return 1
    fi
    
    echo "Refreshing access token..." >&2
    
    local refresh_payload=$(jq -n \
        --arg clientId "$PETIVITY_CLIENT_ID" \
        --arg refreshToken "$PETIVITY_REFRESH_TOKEN" \
        '{
            ClientId: $clientId,
            AuthFlow: "REFRESH_TOKEN_AUTH",
            AuthParameters: {
                REFRESH_TOKEN: $refreshToken
            }
        }')
    
    local response=$(curl -s 'https://cognito-idp.us-east-1.amazonaws.com/' \
        -X POST \
        -H 'Content-Type: application/x-amz-json-1.1' \
        -H 'X-Amz-Target: AWSCognitoIdentityProviderService.InitiateAuth' \
        -H 'User-Agent: Petivity/954 CFNetwork/3857.100.1 Darwin/25.0.0' \
        -H 'Cache-Control: no-store' \
        --data-raw "$refresh_payload")
    
    # Check if refresh was successful
    local new_token=$(echo "$response" | jq -r '.AuthenticationResult.AccessToken // empty')
    
    if [[ -n "$new_token" && "$new_token" != "null" ]]; then
        echo "Token refreshed successfully!" >&2
        echo "New token: ${new_token:0:20}...${new_token: -20}" >&2
        echo "You can update your environment with:" >&2
        echo "  export PETIVITY_JWT=\"$new_token\"" >&2
        return 0
    else
        echo "Token refresh failed:" >&2
        echo "$response" | jq '.' >&2
        return 1
    fi
}

# Check if JWT is expired or expiring soon
is_token_expired() {
    local jwt="$1"
    local current_time=$(date +%s)
    local buffer_time=300  # 5 minutes buffer
    
    # Extract payload (second part of JWT)
    local payload=$(echo "$jwt" | cut -d'.' -f2)
    
    # Add padding if needed (JWT base64 might not be padded)
    local padding_needed=$(( 4 - ${#payload} % 4 ))
    if [[ $padding_needed -ne 4 ]]; then
        payload="${payload}$(printf '%*s' $padding_needed | tr ' ' '=')"
    fi
    
    # Decode and extract expiration
    local exp=$(echo "$payload" | base64 -d 2>/dev/null | jq -r '.exp // empty')
    
    if [[ -n "$exp" && "$exp" != "null" ]]; then
        local time_until_exp=$(( exp - current_time ))
        if [[ $time_until_exp -lt $buffer_time ]]; then
            if [[ $time_until_exp -lt 0 ]]; then
                echo "Token expired $(( -time_until_exp )) seconds ago (at $(date -r $exp))" >&2
            else
                echo "Token expires in $time_until_exp seconds (at $(date -r $exp))" >&2
            fi
            return 0  # Token is expired or expiring soon
        else
            echo "Token expires at $(date -r $exp) (in $time_until_exp seconds)" >&2
            return 1  # Token is valid
        fi
    else
        echo "Warning: Could not parse token expiration" >&2
        return 1  # Assume valid if can't parse
    fi
}

# Auto-refresh token if needed
auto_refresh_if_needed() {
    if is_token_expired "$PETIVITY_JWT"; then
        echo "Access token has expired or is expiring soon, attempting to refresh..." >&2
        if new_token=$(refresh_token); then
            PETIVITY_JWT="$new_token"
            echo "Successfully refreshed token. Try again!" >&2
            return 0
        else
            echo "Failed to refresh token. Please manually update PETIVITY_JWT." >&2
            return 1
        fi
    fi
    return 0
}

# Base curl function for all API calls
petivity_api() {
    local query="$1"
    
    # Check and refresh token if needed (unless in dry run mode)
    if [[ "$DRY_RUN" != "true" ]]; then
        auto_refresh_if_needed || return 1
    fi

    # Build curl command components
    local curl_cmd=(
        curl -s 'https://api.petivity.com/graphql'
        -X POST
        -H 'Host: api.petivity.com'
        -H 'Accept: */*'
        -H 'Connection: keep-alive'
        -H 'Accept-Language: en-US,en;q=0.9'
        -H 'User-Agent: Petivity/954 CFNetwork/3857.100.1 Darwin/25.0.0'
        -H 'Content-Type: application/json'
        -H 'Accept-Encoding: gzip, deflate, br'
        --compressed
        -H 'X-Requested-With: com.petivity.app'
        -H 'Origin: https://api.petivity.com'
        --data-raw "$query"
    )
    
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "=== DRY RUN - Would execute the following curl command ==="
        echo ""
        echo "curl -s 'https://api.petivity.com/graphql' \\"
        echo "  -X POST \\"
        echo "  -H 'Host: api.petivity.com' \\"
        echo "  -H 'Accept: */*' \\"
        echo "  -H 'Connection: keep-alive' \\"
        echo "  -H 'Accept-Language: en-US,en;q=0.9' \\"
        echo "  -H 'User-Agent: Petivity/954 CFNetwork/3857.100.1 Darwin/25.0.0' \\"
        echo "  -H 'Content-Type: application/json' \\"
        echo "  -H 'Accept-Encoding: gzip, deflate, br' \\"
        echo "  --compressed \\"
        echo "  -H 'X-Requested-With: com.petivity.app' \\"
        echo "  -H 'Origin: https://api.petivity.com' \\"
        echo "  --data-raw '$query'"
        echo ""
        echo "=== Environment Variables ==="
        echo "Client ID: $PETIVITY_CLIENT_ID"
        echo "JWT length: ${#PETIVITY_JWT} chars"
        echo "JWT preview: ${PETIVITY_JWT:0:10}...${PETIVITY_JWT: -10}"
        if [[ -n "$PETIVITY_REFRESH_TOKEN" ]]; then
            echo "Refresh token length: ${#PETIVITY_REFRESH_TOKEN} chars"
            echo "Refresh token preview: ${PETIVITY_REFRESH_TOKEN:0:10}...${PETIVITY_REFRESH_TOKEN: -10}"
        else
            echo "Refresh token: Not set"
        fi
        return 0
    else
        local response=$("${curl_cmd[@]}")
        local exit_code=$?
        
        # Check for authentication errors
        if echo "$response" | jq -e '.errors[]? | select(.extensions.code == "UNAUTHENTICATED")' >/dev/null 2>&1; then
            echo "Authentication error detected. Token may be invalid or expired." >&2
            if [[ -n "$PETIVITY_REFRESH_TOKEN" ]]; then
                echo "Attempting to refresh token..." >&2
                if new_token=$(refresh_token); then
                    PETIVITY_JWT="$new_token"
                    echo "Retrying API call with new token..." >&2
                    # Update the query with new JWT
                    local updated_query=$(echo "$query" | jq --arg jwt "$PETIVITY_JWT" '.variables.jwt = $jwt')
                    response=$("${curl_cmd[@]}" --data-raw "$updated_query")
                fi
            fi
        fi
        
        echo "$response" | jq '.'
        return $exit_code
    fi
}

# Status command - gets cats and machines overview
petivity_status() {
    # Use printf and jq -Rs to properly escape the JWT token
    local escaped_jwt=$(printf '%s' "$PETIVITY_JWT" | jq -Rs '.')
    local variables=$(jq -n --argjson jwt "$escaped_jwt" '{jwt: $jwt}')
    
    # Load the GraphQL query from file
    if [[ ! -f "./queries/status.graphql" ]]; then
        echo "Error: ./queries/status.graphql file not found"
        return 1
    fi
    
    local query=$(cat ./queries/status.graphql)
    
    # Use jq to properly escape the query string
    local json_query=$(jq -n \
        --arg operationName "RetrievePetsMachine" \
        --argjson variables "$variables" \
        --arg query "$query" \
        '{operationName: $operationName, variables: $variables, query: $query}')
    
    petivity_api "$json_query"
}

# Manual token refresh command
petivity_refresh() {
    refresh_token
}

# Token info command
petivity_token_info() {
    echo "=== Current Token Information ==="
    echo "JWT length: ${#PETIVITY_JWT} chars"
    echo "JWT preview: ${PETIVITY_JWT:0:20}...${PETIVITY_JWT: -20}"
    
    if [[ -n "$PETIVITY_REFRESH_TOKEN" ]]; then
        echo "Refresh token length: ${#PETIVITY_REFRESH_TOKEN} chars"
        echo "Refresh token preview: ${PETIVITY_REFRESH_TOKEN:0:20}...${PETIVITY_REFRESH_TOKEN: -20}"
    else
        echo "Refresh token: Not set"
    fi
    
    echo ""
    is_token_expired "$PETIVITY_JWT"
}

# Usage and help
case "${1:-help}" in
    "status")
        if [[ "$2" == "--dry-run" ]]; then
            DRY_RUN=true
        fi
        petivity_status
        ;;
    "refresh")
        petivity_refresh
        ;;
    "token-info")
        petivity_token_info
        ;;
    "help"|*)
        echo "Petivity API Helper - Usage:"
        echo ""
        echo "  catalysis <command> [--dry-run]"
        echo ""
        echo "Commands:"
        echo "  status        Get overview of cats and machines"
        echo "  refresh       Manually refresh access token"
        echo "  token-info    Show current token information and expiration"
        echo ""
        echo "Options:"
        echo "  --dry-run     Print the curl command that would be executed"
        echo ""
        echo "Environment variables needed:"
        echo "  PETIVITY_JWT                 (required) Current access token"
        echo "  PETIVITY_CLIENT_ID           (required) For automatic token refresh"
        echo "  PETIVITY_REFRESH_TOKEN       (required) For automatic token refresh"
        echo ""
        echo "Examples:"
        echo "  catalysis status"
        echo "  catalysis status --dry-run"
        echo "  catalysis refresh"
        echo "  catalysis token-info"
        echo ""
        echo "Auto-refresh behavior:"
        echo "  - If refresh token is set, expired access tokens will auto-refresh"
        echo "  - If refresh token is not set, you'll need to manually update JWT"
        ;;
esac