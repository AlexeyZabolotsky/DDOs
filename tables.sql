CREATE TABLE antiddos.abrupt_history (
    timestamp           DateTime DEFAULT now(),
    start               DateTime,
    end                 DateTime,
    source              LowCardinality(String),
    metric              LowCardinality(String),
    sample_rate         LowCardinality(String),
    mae                 Float32,
    smoothed            UInt32,
    data                Array(Float32),
    predicted           Array(Float32),
    indices             Array(UInt64),
    status              LowCardinality(String),
    env                 LowCardinality(String) DEFAULT 'dev'
) ENGINE = MergeTree()
PARTITION BY toDate(end)
ORDER BY (source, metric, end)
TTL timestamp + toIntervalDay(7)
SETTINGS index_granularity = 8192;


CREATE TABLE antiddos.local_access_log (
    timestamp           UInt64,
    host                LowCardinality(String),
    request             String,
    ja4                 LowCardinality(String),
    ipv6                UInt64
) ENGINE = MergeTree()
ORDER BY (timestamp, host, ja4, ipv6)
SETTINGS index_granularity = 8192;


CREATE TABLE antiddos.refs (
    timestamp           UInt64,
    host                LowCardinality(String),
    http_referer        String,
    domain              String DEFAULT domainWithoutWWW(http_referer),
    zone                LowCardinality(String) DEFAULT topLevelDomain(domain)
) ENGINE = MergeTree()
ORDER BY (zone, domain, http_referer)
SETTINGS index_granularity = 8192;


CREATE TABLE antiddos.pusher_metrics (
    insert_time         DateTime DEFAULT now(),
    node                LowCardinality(String),
    metric_type         LowCardinality(String),
    metric              LowCardinality(String),
    source              LowCardinality(String),
    fetch_dt            UInt32,
    prepare_dt          UInt32,
    analysis_dt         UInt32,
    mitigation_dt       UInt32,
    final_dt            UInt32
) ENGINE = MergeTree()
PARTITION BY toStartOfMonth(insert_time)
ORDER BY (metric_type, source, metric)
SETTINGS index_granularity = 8192;


CREATE TABLE antiddos.pusher_events (
    timestamp           DateTime,
    utc_ts              UInt64,
    start               DateTime,
    end                 DateTime,
    source              LowCardinality(String),
    metric              LowCardinality(String),
    sample_rate         LowCardinality(String),
    delay               UInt8,
    k                   Float32,
    v                   Float32,
    thr                 Float32,
    mae                 Float32,
    smoothed            UInt32,
    data                Array(Float32),
    predicted           Array(Float32),
    indices             Array(UInt64),
    rules_created       UInt8,
    rules_failed        UInt8,
    env                 LowCardinality(String),
    event_type          LowCardinality(String),
    status              LowCardinality(String)
) ENGINE = MergeTree()
PARTITION BY toStartOfMonth(timestamp)
ORDER BY (env, status, event_type, source, metric, timestamp)
SETTINGS index_granularity = 8192;


CREATE TABLE antiddos.access_log_paths
(
    t       DateTime DEFAULT fromUnixTimestamp(t_2m),
    t_2m    UInt64,
    host    LowCardinality(String),
    p       String,
    n       UInt64
)
ENGINE = SummingMergeTree(n)
PARTITION BY toDate(t)
PRIMARY KEY (t, host, p)
ORDER BY (t, host, p)
TTL t + toIntervalHour(3)
SETTINGS merge_with_ttl_timeout = 3600, index_granularity = 8192


CREATE MATERIALIZED VIEW antiddos.access_log_paths_mv TO antiddos.access_log_paths
(
    t_2m    UInt64,
    host    LowCardinality(String),
    p       String,
    n       UInt64
) AS
SELECT
    intDiv(timestamp, 120) * 120 AS t_2m,
    host,
    path(request) AS p,
    count() AS n
FROM antiddos.local_access_log
WHERE request != '' and host != ''
GROUP BY t_2m, host, p


CREATE TABLE antiddos.access_log_ja4
(
    t       DateTime DEFAULT fromUnixTimestamp(t_15s),
    t_15s   UInt64,
    host    LowCardinality(String),
    ja4     String,
    n       UInt64
)
ENGINE = SummingMergeTree(n)
PARTITION BY toDate(t)
PRIMARY KEY (t, host, ja4)
ORDER BY (t, host, ja4)
TTL t + toIntervalHour(3)
SETTINGS merge_with_ttl_timeout = 3600, index_granularity = 8192


CREATE MATERIALIZED VIEW antiddos.access_log_ja4_mv TO antiddos.access_log_ja4
(
    t_15s   UInt64,
    host    LowCardinality(String),
    ja4     String,
    n       UInt64
) AS
SELECT
    intDiv(timestamp, 15) * 15 AS t_15s,
    host,
    ja4,
    count() AS n
FROM antiddos.local_access_log
WHERE request != '' and ja4 != ''
GROUP BY t_15s, host, ja4


CREATE TABLE antiddos.access_log_uniq_ip
(
    t       DateTime DEFAULT fromUnixTimestamp(t_1m),
    t_1m    UInt64,
    host    LowCardinality(String),
    ip      UInt64
)
ENGINE = ReplacingMergeTree()
ORDER BY (t, host, ip)
TTL t + toIntervalHour(3)
SETTINGS merge_with_ttl_timeout = 3600, index_granularity = 8192


CREATE MATERIALIZED VIEW antiddos.access_log_ip_mv TO antiddos.access_log_uniq_ip
(
    t_1m    UInt64,
    host    LowCardinality(String),
    ip      UInt64
) AS
SELECT
    intDiv(timestamp, 60) * 60 AS t_1m,
    host,
    ipv6 as ip
FROM antiddos.local_access_log
GROUP BY t_1m, host, ip
