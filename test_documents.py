"""
Quick test: stream one question and print any documents returned.
Run from: examples/02-chat-app/
Usage:    python test_documents.py
"""
import asyncio
import json
from dotenv import load_dotenv
import os

load_dotenv()

from gaia_sdk import GaiaClient

API_KEY = os.getenv("GAIA_API_KEY", "")
BASE_URL = os.getenv("GAIA_BASE_URL", "")
VERIFY_SSL = os.getenv("GAIA_VERIFY_SSL", "true").lower() != "false"
DATASET = "Clinical_Trial_Data_1"
QUERY = "What are the side effects of DrugX?"


async def main():
    print(f"Connecting to {BASE_URL}")
    print(f"Dataset: {DATASET}  |  SSL verify: {VERIFY_SSL}\n")

    async with GaiaClient(
        api_key=API_KEY, base_url=BASE_URL, verify_ssl=VERIFY_SSL
    ) as gaia:
        chunk_count = 0
        all_docs = []
        seen = set()
        response_text = ""

        async for chunk in gaia.ask_stream_iter(
            dataset_names=[DATASET], query=QUERY
        ):
            chunk_count += 1
            if chunk.parsed:
                data = chunk.parsed.get("data") or {}
                # Collect response text
                rs = data.get("responseString")
                if rs:
                    response_text += rs

                # Collect documents
                docs = data.get("documents") or []
                for doc in docs:
                    key = doc.get("docId") or doc.get("filename") or json.dumps(doc)
                    if key not in seen:
                        seen.add(key)
                        all_docs.append(doc)
                        print(f"[chunk #{chunk_count}] NEW DOCUMENT FOUND:")
                        print(json.dumps(doc, indent=2))
                        print()

        print(f"\n--- Done: {chunk_count} chunks ---")
        print(f"Response length: {len(response_text)} chars")
        print(f"Total unique documents: {len(all_docs)}")

        if not all_docs:
            print("\n⚠️  No documents returned — Gaia may not populate 'documents' for this dataset/query.")
            print("   Citations section will be empty until documents are returned.")
        else:
            print("\n✅ Documents found! Citation keys available:")
            for i, doc in enumerate(all_docs, 1):
                print(f"  {i}. filename={doc.get('filename')!r}  filepath={doc.get('filepath')!r}  docId={doc.get('docId')!r}")


if __name__ == "__main__":
    asyncio.run(main())
