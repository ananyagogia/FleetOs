-- 1. UAV QUERIES (CRUD & Fleet Operations)
-- ----------------------------------------------------------------------------

-- 1.1 Insert a new UAV
INSERT INTO uav (name, model, battery_level, latitude, longitude, status, availability, max_payload_kg, capabilities)
VALUES ('Garuda-03', 'DJI Matrice 300 RTK', 100.0, 28.6139, 77.2090, 'IDLE', 1, 9.0, 'CAMERA,THERMAL');

-- 1.2 Get all UAVs
SELECT * FROM uav ORDER BY uav_id ASC;

-- 1.3 Get available UAVs for assignment
SELECT * FROM uav WHERE availability = 1 AND status = 'IDLE' AND battery_level >= 30.0;

-- 1.4 Get UAV by ID
SELECT * FROM uav WHERE uav_id = 1;

-- 1.5 Update UAV status and battery after mission step
UPDATE uav 
SET battery_level = 88.5, status = 'ON_MISSION', availability = 0
WHERE uav_id = 1;

-- 1.6 Update UAV position
UPDATE uav
SET latitude = 28.6180, longitude = 77.2150
WHERE uav_id = 1;


-- ----------------------------------------------------------------------------
-- 2. MISSION QUERIES (CRUD & Mission Queue)
-- ----------------------------------------------------------------------------

-- 2.1 Insert a new mission request
INSERT INTO mission (title, mission_type, priority, latitude, longitude, required_capabilities, burst_time, arrival_time, deadline, status)
VALUES ('Sector 7 Thermal Scan', 'SURVEILLANCE', 2, 28.6185, 77.2135, 'THERMAL', 6, 0, 30, 'PENDING');

-- 2.2 List all pending missions waiting for scheduling
SELECT * FROM mission WHERE status = 'PENDING' ORDER BY priority ASC, arrival_time ASC;

-- 2.3 List all missions by status
SELECT * FROM mission ORDER BY mission_id DESC;

-- 2.4 Update mission status
UPDATE mission SET status = 'ASSIGNED' WHERE mission_id = 1;


-- ----------------------------------------------------------------------------
-- 3. ASSIGNMENT & TRANSACTION QUERIES
-- ----------------------------------------------------------------------------

-- 3.1 Assign UAV to Mission (Atomic Transition)
-- Step A: Insert assignment
INSERT INTO assignment (uav_id, mission_id, status) VALUES (1, 1, 'ACTIVE');

-- Step B: Update UAV status
UPDATE uav SET status = 'ON_MISSION', availability = 0 WHERE uav_id = 1;

-- Step C: Update Mission status
UPDATE mission SET status = 'ASSIGNED' WHERE mission_id = 1;

-- Step D: Log event
INSERT INTO mission_log (mission_id, uav_id, event, status) 
VALUES (1, 1, 'UAV Assigned to Mission', 'ASSIGNED');


-- 3.2 Complete an Assignment
-- Step A: Mark assignment complete
UPDATE assignment SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP 
WHERE assignment_id = 1;

-- Step B: Set UAV back to IDLE
UPDATE uav SET status = 'IDLE', availability = 1 WHERE uav_id = 1;

-- Step C: Mark mission complete
UPDATE mission SET status = 'COMPLETED' WHERE mission_id = 1;

-- Step D: Log completion
INSERT INTO mission_log (mission_id, uav_id, event, status)
VALUES (1, 1, 'Mission execution completed', 'COMPLETED');


-- 3.3 List Active Assignments with Drone and Mission info (JOIN query)
SELECT 
    a.assignment_id,
    a.status AS assignment_status,
    a.assigned_at,
    u.uav_id,
    u.name AS uav_name,
    u.battery_level,
    m.mission_id,
    m.title AS mission_title,
    m.mission_type,
    m.priority
FROM assignment a
JOIN uav u ON a.uav_id = u.uav_id
JOIN mission m ON a.mission_id = m.mission_id
WHERE a.status = 'ACTIVE';


-- ----------------------------------------------------------------------------
-- 4. ANALYTICS & DASHBOARD METRICS QUERIES
-- ----------------------------------------------------------------------------

-- 4.1 Fleet Overview Stats
SELECT 
    COUNT(*) AS total_drones,
    SUM(CASE WHEN status = 'IDLE' THEN 1 ELSE 0 END) AS idle_drones,
    SUM(CASE WHEN status = 'ON_MISSION' THEN 1 ELSE 0 END) AS on_mission_drones,
    SUM(CASE WHEN status = 'CHARGING' THEN 1 ELSE 0 END) AS charging_drones,
    AVG(battery_level) AS avg_fleet_battery
FROM uav;

-- 4.2 Mission Overview Stats
SELECT 
    COUNT(*) AS total_missions,
    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending_missions,
    SUM(CASE WHEN status = 'ASSIGNED' THEN 1 ELSE 0 END) AS assigned_missions,
    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_missions
FROM mission;
