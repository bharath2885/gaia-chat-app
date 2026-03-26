# Gaia SDK for Python

A lightweight, async Python client for the Cohesity Gaia RAG API.

## Installation

```bash
pip install -e .
```

## Quick Start

```python
import asyncio
from gaia_sdk import GaiaClient

async def main():
    async with GaiaClient(api_key="your-api-key") as gaia:
        # List datasets
        datasets = await gaia.list_datasets()
        print(f"Found {len(datasets)} datasets")

        # Ask a question
        response = await gaia.ask(
            dataset_names=["my-dataset"],
            query="What are the key findings from yesterday's reports?"
        )
        print(response.response_string)

asyncio.run(main())
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GAIA_API_KEY` | Yes | Your Cohesity Gaia API key |
| `GAIA_BASE_URL` | No | API base URL (default: `https://helios.cohesity.com/v2/mcm/gaia`) |
| `GAIA_VERIFY_SSL` | No | Enable SSL verification (default: `true`) |
| `GAIA_SECURITY_CTX` | No | Security context for multi-tenant operations |

## Features

- Async/await support with `httpx`
- Pydantic models for type safety
- SSE streaming support
- Exhaustive search with pagination
- Document upload
- Conversation management
- Error handling with typed exceptions
