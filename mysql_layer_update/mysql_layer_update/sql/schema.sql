-- Schema for the crypto market cap pipeline.
-- Run this once against your MySQL instance before running load_staging.py
--
-- Layers:
--   staging_crypto        -> cleaned, deduped, one row per (coin, snapshot)
--   curated_daily_summary -> daily aggregates per coin, what the dashboard reads from
--   pipeline_runs         -> observability log: did each ETL step succeed?

CREATE DATABASE IF NOT EXISTS crypto_pipeline;
USE crypto_pipeline;

-- STAGING LAYER
-- One row per coin per API snapshot. UNIQUE constraint on (coin_id, snapshot_time)
-- makes re-running the load script safe (idempotent) — re-loading the same raw
-- CSV won't create duplicate rows, it just skips ones already there.
CREATE TABLE IF NOT EXISTS staging_crypto (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    coin_id             INT NOT NULL,
    name                VARCHAR(100) NOT NULL,
    symbol              VARCHAR(20) NOT NULL,
    price_usd           DECIMAL(20, 8) NOT NULL,
    market_cap          DECIMAL(24, 2),
    volume_24h          DECIMAL(24, 2),
    percent_change_1h   DECIMAL(10, 4),
    percent_change_24h  DECIMAL(10, 4),
    percent_change_7d   DECIMAL(10, 4),
    cmc_rank            INT,
    snapshot_time       DATETIME NOT NULL,
    loaded_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_coin_snapshot (coin_id, snapshot_time),
    INDEX idx_snapshot_time (snapshot_time),
    INDEX idx_coin_id (coin_id)
);

-- CURATED LAYER
-- Daily aggregate per coin — this is what powers the dashboard and analysis,
-- so it doesn't have to re-scan every raw snapshot every time.
CREATE TABLE IF NOT EXISTS curated_daily_summary (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    summary_date        DATE NOT NULL,
    coin_id             INT NOT NULL,
    name                VARCHAR(100) NOT NULL,
    symbol              VARCHAR(20) NOT NULL,
    open_price          DECIMAL(20, 8),
    close_price         DECIMAL(20, 8),
    min_price           DECIMAL(20, 8),
    max_price           DECIMAL(20, 8),
    avg_market_cap      DECIMAL(24, 2),
    pct_change_intraday DECIMAL(10, 4),   -- (close - open) / open * 100
    volatility          DECIMAL(10, 6),   -- stddev of price across the day's snapshots
    snapshot_count      INT,              -- how many snapshots that day (data completeness check)
    built_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_date_coin (summary_date, coin_id)
);

-- OBSERVABILITY LAYER
-- Tracks every pipeline run (fetch, staging load, curated build) so you can
-- answer "did last night's runs succeed?" without digging through log files.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_type        VARCHAR(50) NOT NULL,   -- 'fetch', 'staging_load', 'curated_build'
    status          VARCHAR(20) NOT NULL,   -- 'success', 'failure'
    rows_affected   INT DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP NOT NULL
);
