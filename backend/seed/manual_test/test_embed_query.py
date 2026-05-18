"""
Quick test: embed a query string with RETRIEVAL_QUERY task type.

Usage:
    python backend/seed/test_embed_query.py
    python backend/seed/test_embed_query.py "your custom question here"
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).parent.parent.parent / ".env")

QUERY = sys.argv[1] if len(sys.argv) > 1 else "What are the main pain points in logistics?"


def embed_query(text: str) -> list[float]:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=1024,
        ),
    )
    [embedding_obj] = result.embeddings
    return embedding_obj.values


if __name__ == "__main__":
    print(f"Query : {QUERY}")
    vector = embed_query(QUERY)
    print(f"Dims  : {len(vector)}")
    print(f"Sample: {[round(v, 4) for v in vector[:6]]}")
