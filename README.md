# tidybot-agent-server

Hardware server for the TidyBot robot fleet. Acts as the gateway between AI agents (e.g. [OpenClaw](https://github.com/anthropics/openclaw)) and the physical robot — a Franka Panda arm on a holonomic mobile base.

```
Agent ──► Hardware Server ──► BaseServer  (mobile base, Python RPC)
           (FastAPI)       ──► FrankaServer (arm, C++/ZMQ 1 kHz)
```

## Features

- **Lease system** — one operator at a time, with idle detection, queue, and auto-revocation
- **Safety envelope** — workspace bounds, velocity limits, gripper force caps
- **Trajectory recording** — logs waypoints after each position command
- **Reset via reversal** — undo the last N% of moves by replaying the trajectory backwards
- **WebSocket streaming** — real-time state (`/ws/state`) and command feedback (`/ws/feedback`)
- **Dry-run mode** — simulated backends for development without hardware

## Quickstart

```bash
# Install dependencies (Python 3.10+)
pip install -r requirements.txt

# Run with simulated backends
python server.py --dry-run

# Run against real hardware
python server.py --host 0.0.0.0 --port 8080
```

## API

### State

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Server and backend status |
| `/state` | GET | Full robot state snapshot |
| `/state/cameras` | GET | Latest camera frame (JPEG) |
| `/trajectory` | GET | Recorded waypoint history |
| `/ws/state` | WS | Streaming state at configurable Hz |
| `/ws/feedback` | WS | Command ack/result events |

### Lease

All command endpoints require an `X-Lease-Id` header.

| Endpoint | Method | Description |
|---|---|---|
| `/lease/acquire` | POST | Acquire or queue for the operator lease |
| `/lease/release` | POST | Release the current lease |
| `/lease/extend` | POST | Reset the idle timer |
| `/lease/status` | GET | Current lease holder and queue depth |

### Commands

| Endpoint | Method | Body | Description |
|---|---|---|---|
| `/cmd/base/move` | POST | `{x, y, theta}` or `{vx, vy, wz}` | Position or velocity move |
| `/cmd/base/stop` | POST | — | Stop the base |
| `/cmd/arm/move` | POST | `{mode, values}` | `joint_position`, `cartesian_pose`, `joint_velocity`, or `cartesian_velocity` |
| `/cmd/arm/stop` | POST | — | Emergency stop the arm |
| `/cmd/gripper` | POST | `{action, width?, speed?, force?}` | `move`, `grasp`, `open`, `close`, `stop`, `homing` |
| `/cmd/reset` | POST | `{fraction?: 1.0}` | Reverse trajectory (0.0–1.0) |

### Example session

```bash
# Acquire lease
LEASE=$(curl -s -X POST localhost:8080/lease/acquire \
  -H 'Content-Type: application/json' \
  -d '{"holder":"my-agent"}' | jq -r .lease_id)

# Move the base
curl -X POST localhost:8080/cmd/base/move \
  -H "Content-Type: application/json" \
  -H "X-Lease-Id: $LEASE" \
  -d '{"x":1, "y":0, "theta":0}'

# Check trajectory
curl localhost:8080/trajectory

# Undo last 50% of moves
curl -X POST localhost:8080/cmd/reset \
  -H "Content-Type: application/json" \
  -H "X-Lease-Id: $LEASE" \
  -d '{"fraction": 0.5}'

# Release lease
curl -X POST localhost:8080/lease/release \
  -H "Content-Type: application/json" \
  -H "X-Lease-Id: $LEASE" \
  -d "{\"lease_id\": \"$LEASE\"}"
```

## Architecture

```
hardware_server/
├── server.py              # FastAPI app wiring
├── config.py              # All configuration dataclasses
├── state.py               # StateAggregator — polls backends
├── trajectory.py          # TrajectoryRecorder — waypoint history
├── lease.py               # LeaseManager — queue + idle detection
├── safety.py              # SafetyEnvelope — bounds checking
├── backends/
│   ├── base.py            # Mobile base RPC client
│   ├── franka.py          # Franka arm ZMQ client
│   └── cameras.py         # Camera capture
├── routes/
│   ├── commands.py        # POST /cmd/* endpoints
│   ├── state_routes.py    # GET /state, /trajectory, /health
│   ├── lease_routes.py    # Lease management endpoints
│   └── ws.py              # WebSocket handlers
└── requirements.txt
```
