"""
FleetOS Database Connection & Persistence Manager
Supports MySQL connection with seamless automatic SQLite fallback for local development/testing.
"""

import os
import sqlite3
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("fleetos.db")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Database configuration from environment variables or defaults
DB_HOST = os.environ.get("FLEETOS_DB_HOST", "localhost")
DB_USER = os.environ.get("FLEETOS_DB_USER", "root")
DB_PASSWORD = os.environ.get("FLEETOS_DB_PASSWORD", "")
DB_NAME = os.environ.get("FLEETOS_DB_NAME", "fleetos")
DB_PORT = int(os.environ.get("FLEETOS_DB_PORT", "3306"))
FORCE_SQLITE = os.environ.get("FLEETOS_USE_SQLITE", "false").lower() in ("true", "1", "yes")

# Path to SQLite fallback database
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB_PATH = os.path.join(BASE_DIR, "fleetos.db")

_ENGINE_MODE = None  # 'mysql' or 'sqlite'


def detect_engine() -> str:
    """Detect whether to use MySQL or SQLite."""
    global _ENGINE_MODE
    if _ENGINE_MODE is not None:
        return _ENGINE_MODE

    if FORCE_SQLITE:
        logger.info("FleetOS DB: FORCE_SQLITE is set. Using SQLite database at %s", SQLITE_DB_PATH)
        _ENGINE_MODE = "sqlite"
        return _ENGINE_MODE

    # Try MySQL first
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
            connection_timeout=2
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARACTER SET utf8mb4;")
        conn.database = DB_NAME
        cursor.close()
        conn.close()
        logger.info("FleetOS DB: Successfully connected to MySQL at %s:%s (database: %s)", DB_HOST, DB_PORT, DB_NAME)
        _ENGINE_MODE = "mysql"
        return _ENGINE_MODE
    except Exception as exc:
        logger.warning(
            "FleetOS DB: MySQL connection failed (%s). Falling back to SQLite at %s",
            exc, SQLITE_DB_PATH
        )
        _ENGINE_MODE = "sqlite"
        return _ENGINE_MODE


def get_connection():
    """Get an active database connection."""
    mode = detect_engine()
    if mode == "mysql":
        import mysql.connector
        return mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT
        )
    else:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn


def _adapt_query_for_sqlite(query: str) -> str:
    """Converts MySQL %s placeholders to SQLite ? placeholders."""
    return query.replace("%s", "?")


def execute_query(query: str, params: Tuple = (), commit: bool = True) -> int:
    """
    Execute INSERT / UPDATE / DELETE query safely.
    Returns lastrowid for INSERT, or rowcount for UPDATE/DELETE.
    """
    mode = detect_engine()
    conn = get_connection()
    try:
        if mode == "mysql":
            cursor = conn.cursor()
            cursor.execute(query, params)
            if commit:
                conn.commit()
            last_id = cursor.lastrowid
            row_count = cursor.rowcount
            cursor.close()
            return last_id if last_id else row_count
        else:
            adapted_query = _adapt_query_for_sqlite(query)
            cursor = conn.cursor()
            cursor.execute(adapted_query, params)
            if commit:
                conn.commit()
            last_id = cursor.lastrowid
            row_count = cursor.rowcount
            cursor.close()
            return last_id if last_id else row_count
    except Exception:
        if conn and mode == "mysql" and conn.is_connected():
            conn.rollback()
        elif conn and mode == "sqlite":
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def fetch_all(query: str, params: Tuple = ()) -> List[Dict[str, Any]]:
    """Execute SELECT query and return list of dictionary records."""
    mode = detect_engine()
    conn = get_connection()
    try:
        if mode == "mysql":
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cursor.close()
            return [dict(row) for row in rows]
        else:
            adapted_query = _adapt_query_for_sqlite(query)
            cursor = conn.cursor()
            cursor.execute(adapted_query, params)
            rows = cursor.fetchall()
            cursor.close()
            return [dict(row) for row in rows]
    finally:
        if conn:
            conn.close()


def fetch_one(query: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
    """Execute SELECT query and return single dictionary or None."""
    mode = detect_engine()
    conn = get_connection()
    try:
        if mode == "mysql":
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params)
            row = cursor.fetchone()
            cursor.close()
            return dict(row) if row else None
        else:
            adapted_query = _adapt_query_for_sqlite(query)
            cursor = conn.cursor()
            cursor.execute(adapted_query, params)
            row = cursor.fetchone()
            cursor.close()
            return dict(row) if row else None
    finally:
        if conn:
            conn.close()


def init_database(seed_demo_data: bool = True):
    """
    Initialize database tables and optionally seed default UAV fleet & missions.
    """
    mode = detect_engine()
    conn = get_connection()

    if mode == "mysql":
        # MySQL table definitions
        schema_statements = [
            """
            CREATE TABLE IF NOT EXISTS uav (
                uav_id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(50) NOT NULL,
                model VARCHAR(50) DEFAULT 'Standard-Quadcopter',
                battery_level DECIMAL(5,2) NOT NULL DEFAULT 100.0,
                latitude DECIMAL(9,6) DEFAULT 28.6139,
                longitude DECIMAL(9,6) DEFAULT 77.2090,
                status VARCHAR(20) NOT NULL DEFAULT 'IDLE',
                availability TINYINT(1) NOT NULL DEFAULT 1,
                max_payload_kg DECIMAL(5,2) DEFAULT 5.0,
                capabilities VARCHAR(255) DEFAULT 'CAMERA',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            """
            CREATE TABLE IF NOT EXISTS mission (
                mission_id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(100) NOT NULL,
                mission_type VARCHAR(50) NOT NULL,
                priority INT NOT NULL DEFAULT 3,
                latitude DECIMAL(9,6) NOT NULL,
                longitude DECIMAL(9,6) NOT NULL,
                required_capabilities VARCHAR(255) DEFAULT 'CAMERA',
                burst_time INT NOT NULL DEFAULT 5,
                arrival_time INT NOT NULL DEFAULT 0,
                deadline INT DEFAULT 60,
                status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            """
            CREATE TABLE IF NOT EXISTS assignment (
                assignment_id INT AUTO_INCREMENT PRIMARY KEY,
                uav_id INT NOT NULL,
                mission_id INT NOT NULL,
                assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
                FOREIGN KEY (uav_id) REFERENCES uav(uav_id) ON DELETE CASCADE,
                FOREIGN KEY (mission_id) REFERENCES mission(mission_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            """
            CREATE TABLE IF NOT EXISTS mission_log (
                log_id INT AUTO_INCREMENT PRIMARY KEY,
                mission_id INT NOT NULL,
                uav_id INT NULL,
                event VARCHAR(100) NOT NULL,
                status VARCHAR(20) NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (mission_id) REFERENCES mission(mission_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            """
            CREATE TABLE IF NOT EXISTS fleet_resource (
                resource_id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(50) NOT NULL,
                resource_type VARCHAR(30) NOT NULL,
                total_capacity INT NOT NULL DEFAULT 5,
                available_count INT NOT NULL DEFAULT 5
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            """
            CREATE TABLE IF NOT EXISTS fault_log (
                fault_id INT AUTO_INCREMENT PRIMARY KEY,
                uav_id INT NOT NULL,
                fault_type VARCHAR(50) NOT NULL,
                description TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (uav_id) REFERENCES uav(uav_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        ]
        cursor = conn.cursor()
        for statement in schema_statements:
            cursor.execute(statement)
        conn.commit()
        cursor.close()
    else:
        # SQLite table definitions
        schema_statements = [
            """
            CREATE TABLE IF NOT EXISTS uav (
                uav_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                model TEXT DEFAULT 'Standard-Quadcopter',
                battery_level REAL NOT NULL DEFAULT 100.0,
                latitude REAL DEFAULT 28.6139,
                longitude REAL DEFAULT 77.2090,
                status TEXT NOT NULL DEFAULT 'IDLE',
                availability INTEGER NOT NULL DEFAULT 1,
                max_payload_kg REAL DEFAULT 5.0,
                capabilities TEXT DEFAULT 'CAMERA',
                created_at TEXT DEFAULT (datetime('now'))
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS mission (
                mission_id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                mission_type TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 3,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                required_capabilities TEXT DEFAULT 'CAMERA',
                burst_time INTEGER NOT NULL DEFAULT 5,
                arrival_time INTEGER NOT NULL DEFAULT 0,
                deadline INTEGER DEFAULT 60,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT DEFAULT (datetime('now'))
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS assignment (
                assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                uav_id INTEGER NOT NULL,
                mission_id INTEGER NOT NULL,
                assigned_at TEXT DEFAULT (datetime('now')),
                completed_at TEXT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                FOREIGN KEY (uav_id) REFERENCES uav(uav_id) ON DELETE CASCADE,
                FOREIGN KEY (mission_id) REFERENCES mission(mission_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS mission_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id INTEGER NOT NULL,
                uav_id INTEGER NULL,
                event TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (mission_id) REFERENCES mission(mission_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS fleet_resource (
                resource_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                total_capacity INTEGER NOT NULL DEFAULT 5,
                available_count INTEGER NOT NULL DEFAULT 5
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS fault_log (
                fault_id INTEGER PRIMARY KEY AUTOINCREMENT,
                uav_id INTEGER NOT NULL,
                fault_type TEXT NOT NULL,
                description TEXT,
                timestamp TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (uav_id) REFERENCES uav(uav_id) ON DELETE CASCADE
            );
            """
        ]
        cursor = conn.cursor()
        for statement in schema_statements:
            cursor.execute(statement)
        conn.commit()
        cursor.close()

    conn.close()
    logger.info("FleetOS DB: Tables initialized successfully.")

    if seed_demo_data:
        seed_fleet_and_missions()


def seed_fleet_and_missions():
    """Seed initial realistic UAV fleet and demo missions if not present."""
    existing_uavs = fetch_all("SELECT COUNT(*) as cnt FROM uav;")
    count = existing_uavs[0]["cnt"] if existing_uavs else 0
    if count == 0:
        logger.info("FleetOS DB: Seeding initial UAV fleet...")
        demo_uavs = [
            ("Garuda-01", "DJI Matrice 300 RTK", 98.0, 28.6139, 77.2090, "IDLE", 1, 9.0, "CAMERA,THERMAL,LIDAR"),
            ("Garuda-02", "DJI Matrice 300 RTK", 85.0, 28.6150, 77.2100, "IDLE", 1, 9.0, "CAMERA,THERMAL"),
            ("Netra-01", "IdeaForge NETRA V4+", 92.0, 28.6120, 77.2050, "IDLE", 1, 4.0, "CAMERA,SURVEILLANCE"),
            ("Netra-02", "IdeaForge NETRA V4+", 74.0, 28.6180, 77.2150, "IDLE", 1, 4.0, "CAMERA,SURVEILLANCE"),
            ("Sanjivani-01", "SkyDrive Cargo Heavy", 95.0, 28.6100, 77.2000, "IDLE", 1, 15.0, "CARGO,MEDICAL_KIT"),
            ("Sanjivani-02", "SkyDrive Cargo Heavy", 45.0, 28.6220, 77.2250, "CHARGING", 0, 15.0, "CARGO,MEDICAL_KIT"),
            ("Agni-01", "FireWatch Hexacopter", 88.0, 28.6160, 77.2120, "IDLE", 1, 8.0, "THERMAL,GAS_SENSOR,CAMERA"),
            ("Pawan-01", "CommsRelay Aerodyne", 90.0, 28.6190, 77.2080, "IDLE", 1, 6.0, "COMM_RELAY,RADIO"),
        ]
        for uav in demo_uavs:
            execute_query(
                """
                INSERT INTO uav (name, model, battery_level, latitude, longitude, status, availability, max_payload_kg, capabilities)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                uav
            )

    existing_missions = fetch_all("SELECT COUNT(*) as cnt FROM mission;")
    m_count = existing_missions[0]["cnt"] if existing_missions else 0
    if m_count == 0:
        logger.info("FleetOS DB: Seeding initial demo missions...")
        demo_missions = [
            ("Emergency Search: Sector 4", "SEARCH_AND_RESCUE", 1, 28.6175, 77.2140, "THERMAL,CAMERA", 6, 0, 20),
            ("Critical Blood Delivery", "MEDICAL_DELIVERY", 1, 28.6110, 77.2030, "CARGO,MEDICAL_KIT", 4, 1, 15),
            ("Perimeter Security Scan", "SURVEILLANCE", 3, 28.6190, 77.2180, "CAMERA,SURVEILLANCE", 8, 2, 45),
            ("Industrial Flare Hotspot Check", "FIRE_MONITORING", 2, 28.6145, 77.2085, "THERMAL,GAS_SENSOR", 5, 3, 30),
            ("Disaster Area Topo Mapping", "MAPPING", 4, 28.6250, 77.2300, "CAMERA,LIDAR", 10, 4, 60),
        ]
        for m in demo_missions:
            execute_query(
                """
                INSERT INTO mission (title, mission_type, priority, latitude, longitude, required_capabilities, burst_time, arrival_time, deadline)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                m
            )

    existing_res = fetch_all("SELECT COUNT(*) as cnt FROM fleet_resource;")
    r_count = existing_res[0]["cnt"] if existing_res else 0
    if r_count == 0:
        resources = [
            ("Fast-Charge Pad Alpha", "CHARGING_PAD", 4, 3),
            ("Fast-Charge Pad Beta", "CHARGING_PAD", 4, 4),
            ("Telemetry Comm Band High", "COMM_CHANNEL", 8, 7),
        ]
        for r in resources:
            execute_query(
                """
                INSERT INTO fleet_resource (name, resource_type, total_capacity, available_count)
                VALUES (%s, %s, %s, %s)
                """,
                r
            )
