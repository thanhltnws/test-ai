import json
import os
from urllib.parse import urlparse

import boto3
import pg8000.dbapi


SCHEMA_SQL = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    """
    CREATE TABLE IF NOT EXISTS signals (
        id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        source         TEXT NOT NULL,
        source_id      TEXT NOT NULL,
        source_url     TEXT,
        pain_points    TEXT[],
        objections     TEXT[],
        use_cases      TEXT[],
        deal_size      TEXT         CHECK (deal_size      IN ('small', 'medium', 'large')),
        client_type    TEXT         CHECK (client_type    IN ('individual', 'startup', 'corporate')),
        tech_maturity  TEXT         CHECK (tech_maturity  IN ('non-tech', 'semi-tech', 'technical')),
        market         TEXT         CHECK (market         IN ('vietnam', 'japan', 'korea', 'international')),
        sector         TEXT,
        funnel_stage   TEXT         CHECK (funnel_stage   IN ('awareness', 'consideration', 'negotiation', 'won', 'lost')),
        embedding_text TEXT,
        record_date    DATE,
        ingested_at    TIMESTAMPTZ,
        extracted_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
        CONSTRAINT signals_source_record_unique UNIQUE (source, source_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS insights (
        id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        period       TEXT        NOT NULL,
        period_start DATE        NOT NULL,
        period_end   DATE        NOT NULL,
        result_type  TEXT        NOT NULL,
        market       TEXT,
        payload      JSONB       NOT NULL
    )
    """,
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS market        TEXT CHECK (market IN ('vietnam', 'japan', 'korea', 'international'))",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS sector        TEXT",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS record_date   DATE",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS deal_size     TEXT CHECK (deal_size     IN ('small', 'medium', 'large'))",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS client_type   TEXT CHECK (client_type   IN ('individual', 'startup', 'corporate'))",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS tech_maturity TEXT CHECK (tech_maturity IN ('non-tech', 'semi-tech', 'technical'))",
    "ALTER TABLE insights ADD COLUMN IF NOT EXISTS market       TEXT",
    "ALTER TABLE insights ADD COLUMN IF NOT EXISTS period_end   DATE NOT NULL DEFAULT now()",
    """
    CREATE TABLE IF NOT EXISTS signal_embeddings (
        signal_id      UUID         PRIMARY KEY REFERENCES signals(id) ON DELETE CASCADE,
        embedding_text TEXT         NOT NULL,
        embedding      vector(1024) NOT NULL,
        embedded_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS insight_embeddings (
        insight_id     UUID         PRIMARY KEY REFERENCES insights(id) ON DELETE CASCADE,
        embedding_text TEXT         NOT NULL,
        embedding      vector(1024) NOT NULL,
        embedded_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS signals_market_idx          ON signals (market)",
    "CREATE INDEX IF NOT EXISTS signals_sector_idx          ON signals (sector)",
    "CREATE INDEX IF NOT EXISTS signals_market_sector_idx   ON signals (market, sector)",
    "CREATE INDEX IF NOT EXISTS signals_funnel_stage_idx    ON signals (funnel_stage)",
    "CREATE INDEX IF NOT EXISTS signals_source_idx          ON signals (source)",
    "CREATE INDEX IF NOT EXISTS signals_extracted_at_idx    ON signals (extracted_at DESC)",
    "CREATE INDEX IF NOT EXISTS signals_deal_size_idx       ON signals (deal_size)",
    "CREATE INDEX IF NOT EXISTS signals_client_type_idx     ON signals (client_type)",
    "CREATE INDEX IF NOT EXISTS signals_tech_maturity_idx   ON signals (tech_maturity)",
    "CREATE INDEX IF NOT EXISTS signals_pain_points_idx     ON signals USING GIN (pain_points)",
    "CREATE INDEX IF NOT EXISTS insights_period_slice_idx   ON insights (period, period_start, result_type, market)",
    "CREATE INDEX IF NOT EXISTS insights_computed_at_idx    ON insights (computed_at DESC)",
    "CREATE INDEX IF NOT EXISTS signal_embeddings_embedding_idx  ON signal_embeddings  USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS insight_embeddings_embedding_idx ON insight_embeddings USING hnsw (embedding vector_cosine_ops)",
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
