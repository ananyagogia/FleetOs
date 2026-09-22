CREATE TABLE IF NOT EXISTS drone (
    drone_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    call_sign        VARCHAR(30)  NOT NULL UNIQUE,
    model            VARCHAR(50),
    max_payload_kg   DECIMAL(5,2),
    battery_pct      DECIMAL(5,2) NOT NULL DEFAULT 100,   
    status           VARCHAR(20)  NOT NULL DEFAULT 'AVAILABLE',
                     -- AVAILABLE | ON_MISSION | CHARGING | MAINTENANCE | OFFLINE
    home_station_id  INTEGER,
    last_heartbeat   DATETIME,
    FOREIGN KEY (home_station_id) REFERENCES charging_station(station_id),
    CHECK (battery_pct BETWEEN 0 AND 100),
    CHECK (status IN ('AVAILABLE','ON_MISSION','CHARGING','MAINTENANCE','OFFLINE'))
);

CREATE TABLE IF NOT EXISTS mission (
    mission_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    emergency_id    INTEGER,                 -- NULL if it's a routine mission
    mission_type    VARCHAR(30)  NOT NULL,   -- MAPPING | DELIVERY | SURVEILLANCE | RESCUE ...
    priority        INTEGER      NOT NULL DEFAULT 3,  
    payload_kg      DECIMAL(5,2) DEFAULT 0,
    dest_latitude   DECIMAL(9,6) NOT NULL,
    dest_longitude  DECIMAL(9,6) NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'QUEUED',
                    -- QUEUED | ASSIGNED | IN_PROGRESS | COMPLETED | FAILED | CANCELLED
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deadline_at     DATETIME,
    FOREIGN KEY (emergency_id) REFERENCES emergency_request(emergency_id),
    CHECK (priority BETWEEN 1 AND 5)
);

CREATE INDEX IF NOT EXISTS idx_mission_status_priority
    ON mission(status, priority);
