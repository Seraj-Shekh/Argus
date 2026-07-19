CREATE TABLE sensor_readings (
    id          SERIAL PRIMARY KEY,
    node_id     VARCHAR(20)       NOT NULL,
    temperature DOUBLE PRECISION,
    humidity    DOUBLE PRECISION,
    smoke       DOUBLE PRECISION,
    wind_speed  DOUBLE PRECISION,
    fwi_index   DOUBLE PRECISION,
    risk_level  VARCHAR(20),
    timestamp   TIMESTAMPTZ       DEFAULT NOW()
);

CREATE TABLE alerts (
    id            SERIAL PRIMARY KEY,
    node_id       VARCHAR(20)  NOT NULL,
    source        VARCHAR(20)  NOT NULL DEFAULT 'software',
    message_en    TEXT         NOT NULL,
    message_fi    TEXT         NOT NULL,
    severity      VARCHAR(20)  NOT NULL,
    risk_level    VARCHAR(20),
    temperature   DOUBLE PRECISION,
    humidity      DOUBLE PRECISION,
    wind_speed    DOUBLE PRECISION,
    precipitation DOUBLE PRECISION,
    smoke         DOUBLE PRECISION,
    station_lat   DOUBLE PRECISION,
    station_lon   DOUBLE PRECISION,
    ai_metadata   JSONB,
    timestamp     TIMESTAMPTZ  DEFAULT NOW()
);
