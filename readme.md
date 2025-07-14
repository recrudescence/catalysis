# Catalysis: a Petivity cli tool

Vibe coded command-line tool for Petivity smart litter box data.

## Setup

Install `jq` and `curl`, then set environment variables:

```bash
export PETIVITY_JWT="your_jwt_token"
```

## Usage

```bash
./petivity.sh status           # Get cats and machines overview
./petivity.sh --dry-run status # Debug mode - see the API call
```

## Output

Shows cats with health alerts, recent activity, and litter box status including battery levels and maintenance needs.
