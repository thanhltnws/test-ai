"""
Test vector similarity search against insight_embeddings in the DB.

Usage:
    python backend/seed/test_search.py
    python backend/seed/test_search.py "VNPay payment issues" 3
"""
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).parent.parent.parent / ".env")

QUERY = sys.argv[1] if len(sys.argv) > 1 else "What are the main pain points in logistics?"
TOP_K = int(sys.argv[2]) if len(sys.argv) > 2 else 5


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
    return result.embeddings[0].values


def search(vector: list[float], top_k: int) -> list[dict]:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    i.source,
                    i.source_url,
                    i.funnel_stage,
                    e.embedding_text,
                    1 - (e.embedding <=> %s::vector) AS score
                FROM insight_embeddings e
                JOIN insights i ON i.id = e.insight_id
                ORDER BY e.embedding <=> %s::vector
                LIMIT %s
                """,
                (str(vector), str(vector), top_k),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


if __name__ == "__main__":
    print(f"Query : {QUERY}")
    print(f"Top-K : {TOP_K}\n")

    vector = embed_query(QUERY)
    results = search(vector, TOP_K)

    if not results:
        print("No results — insight_embeddings may be empty.")
    else:
        for i, r in enumerate(results, 1):
            print(f"[{i}] score={r['score']:.4f}  source={r['source']}  stage={r['funnel_stage']}")
            print(f"     url  : {r['source_url']}")
            print(f"     text : {r['embedding_text'][:120]}...")
            print()
