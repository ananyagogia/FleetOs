CREATE TABLE  UAV (
    uav_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name            VARCHAR(50)  NOT NULL,
    model           VARCHAR(50),
    battery_level   DECIMAL(5,2) NOT NULL DEFAULT 100,   
    latitude        DECIMAL(9,6),
    longitude       DECIMAL(9,6),
    status          VARCHAR(20)  NOT NULL DEFAULT 'IDLE',
                    -- IDLE | ON_MISSION | CHARGING | MAINTENANCE | OFFLINE
    availability    BOOLEAN      NOT NULL DEFAULT 1,  
    CHECK (battery_level BETWEEN 0 AND 100)
);

CREATE TABLE  MISSION (
    mission_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_type    VARCHAR(30)  NOT NULL,   
    priority        INTEGER      NOT NULL DEFAULT 3,  
    latitude        DECIMAL(9,6) NOT NULL,
    longitude       DECIMAL(9,6) NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                    -- PENDING | ASSIGNED | IN_PROGRESS | COMPLETED | FAILED | CANCELLED
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (priority BETWEEN 1 AND 5)
);

CREATE TABLE  FAULT_LOG (
    fault_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    uav_id          INTEGER      NOT NULL,
    fault_type      VARCHAR(30)  NOT NULL,   -- LOW_BATTERY | COMM_LOSS | MOTOR_FAILURE |
                                              -- GPS_ERROR | SENSOR_FAULT | CRASH | OTHER
    description     TEXT,
    timestamp       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (uav_id) REFERENCES UAV(uav_id)
);

CREATE INDEX  idx_faultlog_uav_time ON FAULT_LOG(uav_id, timestamp DESC);
