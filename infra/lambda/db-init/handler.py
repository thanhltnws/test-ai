import json
import os
from urllib.parse import urlparse

import boto3
import pg8000.dbapi


SCHEMA_SQL = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    """
    CREATE TABLE IF NOT EXISTS insights (
        id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
        source           TEXT         NOT NULL,
        source_id        TEXT         NOT NULL,
        source_url       TEXT         NOT NULL CHECK (source_url <> ''),
        raw_text         TEXT,
        pain_points      TEXT[],
        objections       TEXT[],
        use_cases        TEXT[],
        icp              JSONB,
        funnel_stage     TEXT         CHECK (funnel_stage IN ('awareness', 'consideration', 'negotiation', 'won', 'lost')),
        confidence_score NUMERIC(3,2) CHECK (confidence_score BETWEEN 0 AND 1),
        embedding_text   TEXT,
        ingested_at      TIMESTAMPTZ,
        extracted_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
        UNIQUE (source, source_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS recommendations (
        id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        period       TEXT        NOT NULL,
        period_start DATE        NOT NULL,
        result_type  TEXT        NOT NULL,
        payload      JSONB       NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS insight_embeddings (
        insight_id     UUID         PRIMARY KEY REFERENCES insights(id) ON DELETE CASCADE,
        embedding_text TEXT         NOT NULL,
        embedding      vector(1024) NOT NULL,
        metadata       JSONB
    )
    """,
    "CREATE INDEX IF NOT EXISTS insights_source_idx ON insights (source)",
    "CREATE INDEX IF NOT EXISTS insights_funnel_stage_idx ON insights (funnel_stage)",
    "CREATE INDEX IF NOT EXISTS insights_extracted_at_idx ON insights (extracted_at DESC)",
    "CREATE INDEX IF NOT EXISTS insights_source_url_idx ON insights (source_url)",
    "CREATE INDEX IF NOT EXISTS insights_icp_idx ON insights USING GIN (icp)",
    "CREATE INDEX IF NOT EXISTS insights_pain_points_idx ON insights USING GIN (pain_points)",
    "CREATE INDEX IF NOT EXISTS recommendations_computed_at_idx ON recommendations (computed_at DESC)",
    "CREATE INDEX IF NOT EXISTS recommendations_period_period_start_result_type_idx ON recommendations (period, period_start DESC, result_type)",
    "CREATE INDEX IF NOT EXISTS insight_embeddings_embedding_idx ON insight_embeddings USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS insight_embeddings_metadata_idx ON insight_embeddings USING GIN (metadata)",
]


def _db_url_from_secret() -> str:
    secret_arn = os.environ["DB_SECRET_ARN"]
    sm = boto3.client("secretsmanager")
    secret = json.loads(sm.get_secret_value(SecretId=secret_arn)["SecretString"])
    return (
        f"postgresql://{secret['username']}:{secret['password']}"
        f"@{secret['host']}:{secret.get('port', 5432)}/{secret['dbname']}"
    )


def _connect():
    url = urlparse(_db_url_from_secret())
    return pg8000.dbapi.connect(
        host=url.hostname,
        database=url.path.lstrip("/"),
        user=url.username,
        password=url.password,
        port=url.port or 5432,
    )


def handler(event, context):
    request_type = event.get("RequestType")
    if request_type == "Delete":
        return {"PhysicalResourceId": "ai-insight-hub-db-schema"}

    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            for statement in SCHEMA_SQL:
                cur.execute(statement)
            conn.commit()
        finally:
            cur.close()
    finally:
        conn.close()

    return {
        "PhysicalResourceId": "ai-insight-hub-db-schema",
        "Data": {"StatementsApplied": len(SCHEMA_SQL)},
    }
