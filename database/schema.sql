CREATE TABLE IF NOT EXISTS uav (
    uav_id              INT AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(50) NOT NULL,
    model               VARCHAR(50) DEFAULT 'Standard-Quadcopter',
    battery_level       DECIMAL(5,2) NOT NULL DEFAULT 100.0,
    latitude            DECIMAL(9,6) DEFAULT 28.613900,
    longitude           DECIMAL(9,6) DEFAULT 77.209000,
    status              VARCHAR(20) NOT NULL DEFAULT 'IDLE',
                        -- Allowed: IDLE | ON_MISSION | CHARGING | MAINTENANCE | OFFLINE
    availability        TINYINT(1) NOT NULL DEFAULT 1,
    max_payload_kg      DECIMAL(5,2) DEFAULT 5.0,
    capabilities        VARCHAR(255) DEFAULT 'CAMERA',
                        -- Comma-separated: CAMERA,THERMAL,LIDAR,CARGO,MEDICAL_KIT,GAS_SENSOR,COMM_RELAY
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    CHECK (battery_level BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_uav_status ON uav(status);
CREATE INDEX idx_uav_availability ON uav(availability);


-- 2. MISSION (Operational Tasks & Requests)
CREATE TABLE IF NOT EXISTS mission (
    mission_id          INT AUTO_INCREMENT PRIMARY KEY,
    title               VARCHAR(100) NOT NULL,
    mission_type        VARCHAR(50) NOT NULL,
                        -- SEARCH_AND_RESCUE | MEDICAL_DELIVERY | SURVEILLANCE | FIRE_MONITORING | MAPPING | COMM_RELAY
    priority            INT NOT NULL DEFAULT 3,
                        -- 1 (Highest / Emergency) to 5 (Lowest / Background)
    latitude            DECIMAL(9,6) NOT NULL,
    longitude           DECIMAL(9,6) NOT NULL,
    required_capabilities VARCHAR(255) DEFAULT 'CAMERA',
    burst_time          INT NOT NULL DEFAULT 5,       -- Estimated duration in ticks / minutes
    arrival_time        INT NOT NULL DEFAULT 0,       -- Arrival timestamp / tick
    deadline            INT DEFAULT 60,               -- Deadline limit
    status              VARCHAR(20) NOT NULL DEFAULT 'PENDING',
                        -- PENDING | SCHEDULED | ASSIGNED | IN_PROGRESS | COMPLETED | FAILED | CANCELLED
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    CHECK (priority BETWEEN 1 AND 5)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_mission_status ON mission(status);
CREATE INDEX idx_mission_priority ON mission(priority);


-- 3. ASSIGNMENT (UAV <-> Mission Bindings)
CREATE TABLE IF NOT EXISTS assignment (
    assignment_id       INT AUTO_INCREMENT PRIMARY KEY,
    uav_id              INT NOT NULL,
    mission_id          INT NOT NULL,
    assigned_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at        DATETIME NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
                        -- ACTIVE | COMPLETED | REASSIGNED | FAILED
    CONSTRAINT fk_assignment_uav FOREIGN KEY (uav_id) REFERENCES uav(uav_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_assignment_mission FOREIGN KEY (mission_id) REFERENCES mission(mission_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_assignment_uav ON assignment(uav_id);
CREATE INDEX idx_assignment_mission ON assignment(mission_id);
CREATE INDEX idx_assignment_status ON assignment(status);


-- 4. MISSION_LOG (Audit Trail & Lifecycle Events)
CREATE TABLE IF NOT EXISTS mission_log (
    log_id              INT AUTO_INCREMENT PRIMARY KEY,
    mission_id          INT NOT NULL,
    uav_id              INT NULL,
    event               VARCHAR(100) NOT NULL,
    status              VARCHAR(20) NOT NULL,
    timestamp           DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_log_mission FOREIGN KEY (mission_id) REFERENCES mission(mission_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_log_uav FOREIGN KEY (uav_id) REFERENCES uav(uav_id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_log_mission ON mission_log(mission_id, timestamp);


-- 5. FLEET_RESOURCE (Charging Pads & Communication Channels)
CREATE TABLE IF NOT EXISTS fleet_resource (
    resource_id         INT AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(50) NOT NULL,
    resource_type       VARCHAR(30) NOT NULL,   -- CHARGING_PAD | COMM_CHANNEL | SENSOR_PAYLOAD
    total_capacity      INT NOT NULL DEFAULT 5,
    available_count     INT NOT NULL DEFAULT 5,
    CHECK (available_count >= 0 AND available_count <= total_capacity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- 6. FAULT_LOG (Failures, Emergency Warnings & Recovery Logs - Phase 3 ready)
CREATE TABLE IF NOT EXISTS fault_log (
    fault_id            INT AUTO_INCREMENT PRIMARY KEY,
    uav_id              INT NOT NULL,
    fault_type          VARCHAR(50) NOT NULL,
                        -- LOW_BATTERY | COMM_LOSS | MOTOR_FAILURE | GPS_ERROR | SENSOR_FAULT | CRASH | OTHER
    description         TEXT,
    timestamp           DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_fault_uav FOREIGN KEY (uav_id) REFERENCES uav(uav_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_fault_uav_time ON fault_log(uav_id, timestamp DESC);


-- 7. USERS (Authentication & Role-Based Access Control)
CREATE TABLE IF NOT EXISTS users (
    user_id             INT AUTO_INCREMENT PRIMARY KEY,
    username            VARCHAR(50) UNIQUE NOT NULL,
    password_hash       VARCHAR(128) NOT NULL,
    full_name           VARCHAR(100) NOT NULL,
    email               VARCHAR(100) NOT NULL,
    role                VARCHAR(30) NOT NULL DEFAULT 'operator',
                        -- admin | operator | viewer
    status              VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_user_username ON users(username);
