# FleetOS &bull; Autonomous UAV Fleet Management Platform

**FleetOS** is an enterprise-grade autonomous multi-UAV fleet operations, dispatch, and resource operating system. Engineered for defense, disaster response, critical medical logistics, and industrial infrastructure inspection, FleetOS provides real-time situational awareness, dispatch scheduling optimization, deadlock detection and recovery, fault handling with autonomous mission reassignment, and database persistence.

---

## ⚡ Core Operational Flow

The complete mission lifecycle proceeds autonomously through six synchronized stages:

```
[Mission Submission] ──▶ [Database Persistence] ──▶ [Intelligent Dispatch]
                                                           │
                                                           ▼
[Command Center Dashboard] ◀── [Database State Update] ◀── [UAV Airframe Assignment]
```

1. **Mission Submission**: Operational tasks are registered with target coordinates, priority level, estimated burst duration, and payload sensor requirements.
2. **Database Persistence**: Persistent transaction logging with ACID safety and dual MySQL / SQLite storage engines.
3. **Intelligent Dispatch**: Mission queues are scheduled using core algorithms (Priority-Based, Shortest Mission First, Arrival Order, and Time-Sliced Dynamic) to minimize turnaround and queue delays.
4. **UAV Airframe Assignment**: Real-time evaluation of drone readiness, proximity (Haversine formula), battery reserve margins ($\ge 25\%$), and sensor payload matching.
5. **Database State Update**: Atomic state transitions locking airframes to active sorties and logging audit events.
6. **Command Center Dashboard**: Live telemetry streaming, interactive radar map tracking, battery health monitoring, and flight progress updates.

---

## 🌟 Key Platform Features

### 1. Operations Command Center
- **Executive KPI Metrics**: Real-time fleet readiness, airborne sorties, average battery reserves, and dispatch queue volume.
- **Tactical Live Radar Map**: Vector canvas radar with geofence zones, concentric range rings, drone markers with callsigns, and animated flight corridor paths.
- **Flight Sortie Monitoring**: Live tracking of airborne UAVs with current waypoint navigation and battery discharge rates.

### 2. Intelligent Dispatch & Mission Planning Engine
Configurable dispatch policies for diverse airspace conditions:
- **Priority-Based Dispatch**: Mission-critical and emergency sorties preempt routine tasks.
- **Shortest Mission First (SJF)**: Optimizes overall queue throughput and minimizes operational wait times.
- **Arrival Order (FCFS)**: Sequential dispatch strictly adhering to request arrival sequence.
- **Time-Sliced Dynamic (Round Robin)**: Cyclical quantum time sharing for balanced resource distribution.
- **Strategy Comparison Benchmarks**: Side-by-side performance cards and Chart.js analytics comparing average queue times and completion times.

### 3. Deadlock Detection & Autonomous Recovery Engine
- **Resource Allocation Graph (RAG) & Wait-For Graph (WFG)**: Real-time modeling of tasks (UAVs) and shared fleet resources (Fast-Charging Pads, RF Comm Bands, Sensor Pods).
- **Cycle Detection via Depth-First Search (DFS)**: Automatically detects circular wait deadlocks.
- **Autonomous Recovery Mechanism**: Selects optimal victim task based on lowest priority, preempts held resources, immediately satisfies blocked waiting tasks, rolls back victim mission to `PENDING` queue without data loss, and logs incident in `fault_log`.
- **Deadlock Simulator**: Interactive one-click simulation to demonstrate circular wait condition detection and resolution in the UI.

### 4. Fault Detection & Autonomous Recovery Engine
Comprehensive fault handling across five critical failure modes:
1. **Drone Failure** (`DRONE_FAILURE`): Hardware/motor crash forces airframe `OFFLINE`, releases all held resources, and automatically reassigns active mission to an eligible idle UAV (or re-queues to `PENDING`).
2. **Low Battery** (`LOW_BATTERY`): Battery depletion ($\le 20\%$) triggers emergency Return-to-Base (RTB), autonomous docking to charging pad, and sortie reassignment.
3. **Mission Failure** (`MISSION_FAILURE`): Aborts failed sorties, returns assigned UAV to `IDLE`, and records audit trace.
4. **Resource Unavailability** (`RESOURCE_UNAVAILABLE`): Detects resource exhaustion and queues requests.
5. **Communication Loss** (`COMM_LOSS`): Failsafe link disconnection releases bandwidth channels and executes failsafe procedures.
- **Autonomous Self-Healing Scan**: Scans all active faults, restores repaired/cleared airframes, and dispatches stranded missions.

### 5. Fleet Airframe & Resource Management (100% Database Integrated)
- **Airframe Registry**: Comprehensive UAV database tracking models, battery levels, payload capacities, and sensor suites.
- **Power & Charging Hubs**: Real-time monitoring of fast-charge station occupancy and automated docking queues.
- **RF Communications Infrastructure**: Telemetry bandwidth spectrum allocation and signal integrity monitoring.
- **Maintenance Lifecycle**: Persistent flight hour accumulation, motor wear diagnostics, and scheduled inspection alerts in `uav_maintenance`.

### 6. Role-Based Access Control (RBAC)
- Authenticated operator access with role-based feature gating (Admin, Operator, Viewer).

---

## 🔐 Operator Login Credentials

The platform includes pre-configured role-based operator accounts:

| Role | Username / Callsign | Password | Permitted Actions |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `admin123` | Full system access: User & access management, system safety limits, fleet registration, mission creation, dispatch execution, deadlock & fault simulation. |
| **Flight Operator** | `operator` | `operator123` | Tactical operations: Mission creation, dispatch execution, fleet monitoring, simulation telemetry stepping, fault resolution. |
| **Viewer / Observer** | `viewer` | `viewer123` | Situational awareness: Read-only access to Command Center, Live Map, and Analytics dashboards. |

---

## 🛠️ Technology Stack

- **Backend Architecture**: Python 3.10+, Flask RESTful API, Flask-CORS.
- **Database Engine**: Dual-Engine Architecture (MySQL 8.0 with automatic SQLite fallback).
- **Core Algorithms**: FCFS, SJF, Priority Scheduling, Round Robin, DFS Cycle Detection, RAG/WFG Preemption.
- **Frontend Architecture**: Vanilla HTML5, Modular CSS Design System (CSS Variables), JavaScript ES6+ Modules.
- **Visualization & Maps**: HTML5 Canvas Tactical Radar Engine, Chart.js.
- **Security & RBAC**: SHA-256 cryptographic password hashing, Bearer session tokens.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10 or higher
- Modern web browser (Chrome, Edge, Firefox, Safari)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Launch FleetOS Server
```bash
python backend/main.py
```

### 4. Access the Application
- **Command Center Dashboard**: `http://localhost:5000/`
- **Login Portal**: `http://localhost:5000/login.html`
- **API Health Check**: `http://localhost:5000/api/health`

### 5. Run Unit Tests
```bash
python -m unittest discover -s tests -p "test_*.py"
```
