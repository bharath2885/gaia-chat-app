"""
Quick test: fetch discovery/topics for a dataset.
Run from: examples/02-chat-app/ (with venv active)
Usage:    python3 test_discovery.py
"""
import asyncio, json, os
from dotenv import load_dotenv
load_dotenv()

from gaia_sdk import GaiaClient

API_KEY  = os.getenv("GAIA_API_KEY", "")
BASE_URL = os.getenv("GAIA_BASE_URL", "")
VERIFY   = os.getenv("GAIA_VERIFY_SSL", "true").lower() != "false"
DATASET  = "Clinical_Trial_Data_1"

async def main():
    async with GaiaClient(api_key=API_KEY, base_url=BASE_URL, verify_ssl=VERIFY) as gaia:
        # First get the dataset details to find the real ID
        details = await gaia.get_dataset(DATASET)
        print("=== Dataset details ===")
        print(json.dumps(details.model_dump(), indent=2))

        # Try discovery using the name (SDK uses dataset_id but may accept name)
        print("\n=== Discovery (by name) ===")
        try:
            disc = await gaia.get_discovery(DATASET)
            print(json.dumps(disc, indent=2)[:3000])
        except Exception as e:
            print(f"Discovery by name failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
