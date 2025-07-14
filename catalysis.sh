#!/bin/zsh

# Check if required environment variables are set
if [[ -z "$PETIVITY_JWT" || -z "$PETIVITY_COOKIES" ]]; then
    echo "Error: Required environment variables not set."
    echo "Please set:"
    echo "  export PETIVITY_JWT=\"your_jwt_token\""
    exit 1
fi

# Global dry run flag
DRY_RUN=false

# Base curl function for all API calls
petivity_api() {
    local query="$1"
    
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
        echo "JWT length: ${#PETIVITY_JWT} chars"
        echo "Cookies length: ${#PETIVITY_COOKIES} chars"
        echo "JWT preview: ${PETIVITY_JWT:0:10}...${PETIVITY_JWT: -10}"
        echo "Cookies preview: ${PETIVITY_COOKIES:0:20}...${PETIVITY_COOKIES: -20}"
        return 0
    else
        "${curl_cmd[@]}" | jq '.'
    fi
}

# Status command - gets cats and machines overview
petivity_status() {
    local variables=$(jq -n --arg jwt "$PETIVITY_JWT" '{jwt: $jwt}')
    
    # Load the GraphQL query from file
    if [[ ! -f "status.graphql" ]]; then
        echo "Error: status.graphql file not found"
        return 1
    fi
    
    local query=$(cat status.graphql)
    
    # Use jq to properly escape the query string
    local json_query=$(jq -n \
        --arg operationName "RetrievePetsMachine" \
        --argjson variables "$variables" \
        --arg query "$query" \
        '{operationName: $operationName, variables: $variables, query: $query}')
    
    petivity_api "$json_query"
}

# Usage and help
case "${1:-help}" in
    "status")
        if [[ "$2" == "--dry-run" ]]; then
            DRY_RUN=true
        fi
        petivity_status
        ;;
    "help"|*)
        echo "Petivity API Helper - Usage:"
        echo ""
        echo "  petivity <command> [--dry-run]"
        echo ""
        echo "Commands:"
        echo "  status    Get overview of cats and machines"
        echo ""
        echo "Options:"
        echo "  --dry-run    Print the curl command that would be executed"
        echo ""
        echo "Environment variables needed:"
        echo "  PETIVITY_JWT, PETIVITY_COOKIES"
        echo ""
        echo "Examples:"
        echo "  petivity status"
        echo "  petivity status --dry-run"
        ;;
esac