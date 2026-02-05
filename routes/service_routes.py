"""Service management endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from services import ServiceManager

router = APIRouter(prefix="/services", tags=["services"])

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Service Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a2e; color: #eee; padding: 24px; }
  h1 { margin-bottom: 8px; }
  .subtitle { color: #888; margin-bottom: 20px; font-size: 14px; }
  .dry-run-badge { background: #ff9800; color: #000; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-left: 10px; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 24px; background: #16213e; border-radius: 8px; overflow: hidden; }
  th, td { padding: 14px 18px; text-align: left; border-bottom: 1px solid #1a1a2e; }
  th { background: #0f3460; color: #aaa; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
  tr:last-child td { border-bottom: none; }
  tr:hover { background: #1a2744; }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
  .dot.on  { background: #4caf50; box-shadow: 0 0 8px #4caf50; }
  .dot.off { background: #f44336; }
  button { padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; color: #fff; font-weight: 500; transition: all 0.2s; }
  .btn-start { background: #2e7d32; }
  .btn-start:hover { background: #388e3c; }
  .btn-stop  { background: #c62828; }
  .btn-stop:hover { background: #d32f2f; }
  .btn-restart { background: #1565c0; margin-left: 8px; }
  .btn-restart:hover { background: #1976d2; }
  button:disabled { opacity: .5; cursor: not-allowed; }
  .logs-section { margin-top: 24px; }
  .log-box { background: #0d1117; padding: 14px; border-radius: 8px; margin-bottom: 20px;
             max-height: 250px; overflow-y: auto; font-family: 'SF Mono', Monaco, monospace; font-size: 12px;
             white-space: pre-wrap; color: #8b949e; border: 1px solid #30363d; }
  .log-title { font-weight: 600; margin-bottom: 8px; font-size: 14px; color: #c9d1d9; }
  .status-text { font-size: 13px; }
  .status-text.on { color: #4caf50; }
  .status-text.off { color: #f44336; }
  .uptime { color: #888; font-size: 12px; }
  .actions { display: flex; gap: 8px; }
  .refresh-info { color: #666; font-size: 12px; margin-top: 16px; }
  .state-section { margin-bottom: 24px; }
  .state-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
  .state-card { background: #16213e; border-radius: 8px; padding: 16px; }
  .state-card h3 { font-size: 14px; color: #aaa; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }
  .state-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #1a1a2e; }
  .state-row:last-child { border-bottom: none; }
  .state-label { color: #888; font-size: 13px; }
  .state-value { font-family: 'SF Mono', Monaco, monospace; font-size: 13px; color: #4caf50; }
  .state-value.disconnected { color: #f44336; }
  /* Robot Control Section */
  .control-section { margin-bottom: 24px; }
  .control-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
  .control-card { background: #16213e; border-radius: 8px; padding: 16px; }
  .control-card h3 { font-size: 14px; color: #aaa; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
  .control-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #1a1a2e; }
  .control-row:last-child { border-bottom: none; }
  .control-label { color: #888; font-size: 13px; }
  .control-input { width: 80px; padding: 6px 10px; border: 1px solid #30363d; border-radius: 4px; background: #0d1117; color: #eee; font-size: 13px; text-align: center; }
  .control-input:focus { outline: none; border-color: #1565c0; }
  .toggle-switch { position: relative; width: 48px; height: 24px; }
  .toggle-switch input { opacity: 0; width: 0; height: 0; }
  .toggle-slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background: #444; border-radius: 24px; transition: 0.3s; }
  .toggle-slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background: #fff; border-radius: 50%; transition: 0.3s; }
  .toggle-switch input:checked + .toggle-slider { background: #4caf50; }
  .toggle-switch input:checked + .toggle-slider:before { transform: translateX(24px); }
  .btn-action { padding: 10px 24px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; color: #fff; font-weight: 500; transition: all 0.2s; width: 100%; margin-top: 8px; }
  .btn-rewind { background: #ff9800; }
  .btn-rewind:hover { background: #ffa726; }
  .btn-home { background: #9c27b0; }
  .btn-home:hover { background: #ab47bc; }
  .btn-action:disabled { opacity: .5; cursor: not-allowed; }
  .status-badge { font-size: 11px; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; }
  .status-badge.enabled { background: #4caf50; color: #fff; }
  .status-badge.disabled { background: #666; color: #ccc; }
  .status-badge.active { background: #ff9800; color: #000; animation: pulse 1s infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
  .boundary-status { font-size: 12px; padding: 4px 8px; border-radius: 4px; }
  .boundary-status.safe { background: #1b5e20; color: #4caf50; }
  .boundary-status.warning { background: #e65100; color: #ff9800; }
  /* Trajectory Visualization */
  .trajectory-section { margin-bottom: 24px; }
  .trajectory-card { background: #16213e; border-radius: 8px; padding: 16px; }
  .trajectory-card h3 { font-size: 14px; color: #aaa; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }
  .trajectory-canvas-container { position: relative; width: 100%; aspect-ratio: 1; max-width: 500px; margin: 0 auto; }
  #trajectory-canvas { width: 100%; height: 100%; background: #0d1117; border-radius: 8px; border: 1px solid #30363d; }
  .trajectory-legend { display: flex; gap: 16px; margin-top: 12px; justify-content: center; flex-wrap: wrap; }
  .legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #888; }
  .legend-dot { width: 12px; height: 12px; border-radius: 50%; }
  .legend-dot.current { background: #4caf50; box-shadow: 0 0 8px #4caf50; }
  .legend-dot.path { background: #1976d2; }
  .legend-dot.start { background: #9c27b0; }
  .legend-line { width: 20px; height: 2px; }
  .legend-line.boundary { background: #f44336; border: 1px dashed #f44336; }
  .trajectory-info { display: flex; gap: 24px; margin-top: 12px; justify-content: center; font-size: 12px; color: #888; }
  .trajectory-info span { font-family: 'SF Mono', Monaco, monospace; color: #4caf50; }
</style></head><body>
<h1>Service Dashboard<span id="dry-run-badge" class="dry-run-badge" style="display:none">DRY-RUN</span></h1>
<p class="subtitle">TidyBot Agent Server — Backend Service Manager</p>

<div class="control-section">
  <div class="control-grid">
    <div class="control-card">
      <h3>Safety Monitor <span id="auto-rewind-badge" class="status-badge disabled">Disabled</span></h3>
      <div class="control-row">
        <span class="control-label">Auto-Rewind</span>
        <label class="toggle-switch">
          <input type="checkbox" id="auto-rewind-toggle" onchange="toggleAutoRewind(this.checked)">
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="control-row">
        <span class="control-label">Auto-Rewind %</span>
        <input type="number" id="auto-rewind-pct" class="control-input" min="0.1" max="100" step="0.1" value="10" onchange="updateAutoRewindPct(this.value)">
      </div>
      <div class="control-row">
        <span class="control-label">Boundary Status</span>
        <span id="boundary-status" class="boundary-status safe">Safe</span>
      </div>
      <div class="control-row">
        <span class="control-label">Trajectory Length</span>
        <span class="state-value" id="trajectory-length">0</span>
      </div>
      <button class="btn-action" style="background: #666; margin-top: 8px;" onclick="clearTrajectory(this)">
        Clear Trajectory
      </button>
    </div>
    <div class="control-card">
      <h3>Manual Rewind</h3>
      <div class="control-row">
        <span class="control-label">Rewind %</span>
        <input type="number" id="manual-rewind-pct" class="control-input" min="0.1" max="100" step="0.1" value="5" onchange="updateManualRewindPct(this.value)">
      </div>
      <div class="control-row">
        <span class="control-label">Current Status</span>
        <span id="rewind-status" class="state-value">Idle</span>
      </div>
      <button id="btn-manual-rewind" class="btn-action btn-rewind" onclick="triggerManualRewind(this)">
        Rewind
      </button>
    </div>
    <div class="control-card">
      <h3>Reset to Home</h3>
      <div class="control-row">
        <span class="control-label">Rewinds 100%</span>
        <span class="state-value">of trajectory</span>
      </div>
      <div class="control-row">
        <span class="control-label">Current Status</span>
        <span id="reset-status" class="state-value">Idle</span>
      </div>
      <button id="btn-reset-home" class="btn-action btn-home" onclick="resetToHome(this)">
        Reset to Home
      </button>
    </div>
  </div>
</div>

<div class="logs-section">
  <div class="control-card">
    <h3>Rewind Logs</h3>
    <div id="rewind-logs" class="log-box" style="height: 200px; font-size: 11px;"></div>
  </div>
</div>

<div class="trajectory-section">
  <div class="trajectory-card">
    <h3>Base Trajectory</h3>
    <div class="trajectory-canvas-container">
      <canvas id="trajectory-canvas"></canvas>
    </div>
    <div class="trajectory-legend">
      <div class="legend-item"><div class="legend-dot current"></div>Current Position</div>
      <div class="legend-item"><div class="legend-dot path"></div>Trajectory Path</div>
      <div class="legend-item"><div class="legend-dot start"></div>Start Position</div>
      <div class="legend-item"><div class="legend-line boundary"></div>Workspace Boundary</div>
    </div>
    <div class="trajectory-info">
      <div>Points: <span id="traj-points">0</span></div>
      <div>Duration: <span id="traj-duration">0.0s</span></div>
      <div>X: <span id="traj-x">—</span></div>
      <div>Y: <span id="traj-y">—</span></div>
    </div>
  </div>
</div>

<div class="state-section">
  <div class="state-grid">
    <div class="state-card">
      <h3>Base Odometry</h3>
      <div class="state-row"><span class="state-label">X</span><span class="state-value" id="base-x">—</span></div>
      <div class="state-row"><span class="state-label">Y</span><span class="state-value" id="base-y">—</span></div>
      <div class="state-row"><span class="state-label">Theta</span><span class="state-value" id="base-theta">—</span></div>
    </div>
    <div class="state-card">
      <h3>Arm EE (Base Frame)</h3>
      <div class="state-row"><span class="state-label">X</span><span class="state-value" id="ee-x">—</span></div>
      <div class="state-row"><span class="state-label">Y</span><span class="state-value" id="ee-y">—</span></div>
      <div class="state-row"><span class="state-label">Z</span><span class="state-value" id="ee-z">—</span></div>
    </div>
    <div class="state-card">
      <h3>Arm EE (World Frame)</h3>
      <div class="state-row"><span class="state-label">X</span><span class="state-value" id="ee-world-x">—</span></div>
      <div class="state-row"><span class="state-label">Y</span><span class="state-value" id="ee-world-y">—</span></div>
      <div class="state-row"><span class="state-label">Z</span><span class="state-value" id="ee-world-z">—</span></div>
    </div>
    <div class="state-card">
      <h3>Gripper</h3>
      <div class="state-row"><span class="state-label">Width</span><span class="state-value" id="gripper-width">—</span></div>
      <div class="state-row"><span class="state-label">Grasped</span><span class="state-value" id="gripper-grasped">—</span></div>
    </div>
  </div>
</div>

<table>
  <thead><tr><th>Service</th><th>Status</th><th>PID</th><th>Uptime</th><th>Actions</th></tr></thead>
  <tbody id="tbl"><tr><td colspan="5" style="text-align:center;color:#666">Loading...</td></tr></tbody>
</table>
<div class="logs-section" id="logs-section"></div>
<p class="refresh-info">Auto-refreshes every 2 seconds</p>
<script>
let serviceKeys = [];
function fmt(s) {
  if (s == null) return "—";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return h + "h " + m + "m";
  return m + "m " + sec + "s";
}

async function act(method, url, btn) {
  if (btn) btn.disabled = true;
  try {
    await fetch(url, { method });
    await poll();
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function poll() {
  try {
    const data = await (await fetch("/services")).json();
    let rows = "";
    let isDryRun = false;
    const newKeys = [];

    for (const s of data) {
      newKeys.push(s.key);
      const on = s.running;
      if (s.dry_run) isDryRun = true;

      // Special handling for unlock service - single toggle button
      let actionBtns;
      if (s.key === "unlock") {
        actionBtns = on
          ? `<button class="btn-stop" onclick="act('POST','/services/unlock/lock',this)">Lock</button>`
          : `<button class="btn-start" onclick="act('POST','/services/unlock/start',this)">Unlock</button>`;
      } else {
        actionBtns = on
          ? `<button class="btn-stop" onclick="act('POST','/services/${s.key}/stop',this)">Stop</button>
             <button class="btn-restart" onclick="act('POST','/services/${s.key}/restart',this)">Restart</button>`
          : `<button class="btn-start" onclick="act('POST','/services/${s.key}/start',this)">Start</button>`;
      }

      rows += `<tr>
        <td><span class="dot ${on ? "on" : "off"}"></span>${s.name}</td>
        <td><span class="status-text ${on ? "on" : "off"}">${on ? (s.key === "unlock" ? "Unlocked" : "Running") : (s.key === "unlock" ? "Locked" : "Stopped")}</span></td>
        <td>${s.pid || "—"}</td>
        <td class="uptime">${fmt(s.uptime)}</td>
        <td class="actions">${actionBtns}</td></tr>`;
    }

    document.getElementById("tbl").innerHTML = rows;
    document.getElementById("dry-run-badge").style.display = isDryRun ? "inline" : "none";

    // Update log sections if keys changed
    if (JSON.stringify(newKeys) !== JSON.stringify(serviceKeys)) {
      serviceKeys = newKeys;
      let logsHtml = "";
      for (const s of data) {
        logsHtml += `<div class="log-title">${s.name}</div><div class="log-box" id="log-${s.key}">(no output)</div>`;
      }
      document.getElementById("logs-section").innerHTML = logsHtml;
    }

    // Fetch logs for each service
    for (const s of data) {
      const logsResp = await fetch(`/services/${s.key}/logs?lines=50`);
      const logsData = await logsResp.json();
      const el = document.getElementById("log-" + s.key);
      if (el && logsData.lines) {
        // Color code log lines based on error patterns
        const coloredLines = logsData.lines.map(line => {
          const escaped = line.replace(/</g, "&lt;");
          // Check for error patterns (case-insensitive)
          const lower = line.toLowerCase();
          if (lower.includes("error") || lower.includes("exception") || lower.includes("critical") ||
              lower.includes("failed") || lower.includes("traceback") || lower.includes("fatal")) {
            return `<span style="color: #f85149;">${escaped}</span>`;  // Red for errors
          } else if (lower.includes("warning") || lower.includes("warn")) {
            return `<span style="color: #d29922;">${escaped}</span>`;  // Orange for warnings
          }
          return escaped;
        });
        const content = coloredLines.join("\n") || "(no output)";
        const wasAtBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 10;
        el.innerHTML = content;
        if (wasAtBottom) el.scrollTop = el.scrollHeight;
      }
    }
  } catch (e) {
    console.error("Poll error:", e);
  }
}

async function pollState() {
  try {
    const resp = await fetch("/state");
    const state = await resp.json();

    // Base odometry
    const base = state.base || {};
    const pose = base.pose || [0, 0, 0];
    document.getElementById("base-x").textContent = pose[0].toFixed(3) + " m";
    document.getElementById("base-y").textContent = pose[1].toFixed(3) + " m";
    document.getElementById("base-theta").textContent = (pose[2] * 180 / Math.PI).toFixed(1) + "°";

    // Arm EE pose (4x4 matrix stored column-major, position is indices 12,13,14)
    const arm = state.arm || {};
    const ee = arm.ee_pose || [];
    if (ee.length >= 15) {
      document.getElementById("ee-x").textContent = ee[12].toFixed(3) + " m";
      document.getElementById("ee-y").textContent = ee[13].toFixed(3) + " m";
      document.getElementById("ee-z").textContent = ee[14].toFixed(3) + " m";
      document.getElementById("ee-x").classList.remove("disconnected");
      document.getElementById("ee-y").classList.remove("disconnected");
      document.getElementById("ee-z").classList.remove("disconnected");
    } else {
      document.getElementById("ee-x").textContent = "—";
      document.getElementById("ee-y").textContent = "—";
      document.getElementById("ee-z").textContent = "—";
      document.getElementById("ee-x").classList.add("disconnected");
      document.getElementById("ee-y").classList.add("disconnected");
      document.getElementById("ee-z").classList.add("disconnected");
    }

    // Arm EE pose in world frame
    const eeWorld = arm.ee_pose_world || [];
    if (eeWorld.length >= 15) {
      document.getElementById("ee-world-x").textContent = eeWorld[12].toFixed(3) + " m";
      document.getElementById("ee-world-y").textContent = eeWorld[13].toFixed(3) + " m";
      document.getElementById("ee-world-z").textContent = eeWorld[14].toFixed(3) + " m";
      document.getElementById("ee-world-x").classList.remove("disconnected");
      document.getElementById("ee-world-y").classList.remove("disconnected");
      document.getElementById("ee-world-z").classList.remove("disconnected");
    } else {
      document.getElementById("ee-world-x").textContent = "—";
      document.getElementById("ee-world-y").textContent = "—";
      document.getElementById("ee-world-z").textContent = "—";
      document.getElementById("ee-world-x").classList.add("disconnected");
      document.getElementById("ee-world-y").classList.add("disconnected");
      document.getElementById("ee-world-z").classList.add("disconnected");
    }

    // Gripper
    const gripper = state.gripper || {};
    document.getElementById("gripper-width").textContent = ((gripper.width || 0) * 1000).toFixed(1) + " mm";
    document.getElementById("gripper-grasped").textContent = gripper.is_grasped ? "Yes" : "No";

  } catch (e) {
    console.error("State poll error:", e);
  }
}

// Lease ID for commands (acquire one automatically)
let leaseId = null;
let leaseHeartbeatInterval = null;

async function ensureLease() {
  if (leaseId) {
    // Verify cached lease is still valid
    try {
      const statusResp = await fetch("/lease/status");
      const status = await statusResp.json();
      if (status.holder !== "dashboard") {
        leaseId = null; // Lease was revoked, clear cache
      }
    } catch (e) {
      leaseId = null;
    }
  }

  if (leaseId) return leaseId;

  try {
    const resp = await fetch("/lease/acquire", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ holder: "dashboard", timeout_sec: 300 })
    });
    const data = await resp.json();
    if (data.lease_id) {
      leaseId = data.lease_id;
      // Clear any existing heartbeat interval
      if (leaseHeartbeatInterval) {
        clearInterval(leaseHeartbeatInterval);
      }
      // Heartbeat to keep lease alive (extend every 10 seconds)
      leaseHeartbeatInterval = setInterval(async () => {
        if (leaseId) {
          try {
            const extResp = await fetch("/lease/extend", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ lease_id: leaseId })
            });
            const extData = await extResp.json();
            if (extData.status === "not_found") {
              leaseId = null; // Lease expired, clear cache
            }
          } catch (e) {
            leaseId = null; // Connection error, clear cache
          }
        }
      }, 10000);
    }
    return leaseId;
  } catch (e) {
    console.error("Failed to acquire lease:", e);
    return null;
  }
}

async function toggleAutoRewind(enabled) {
  try {
    const endpoint = enabled ? "/rewind/monitor/enable" : "/rewind/monitor/disable";
    await fetch(endpoint, { method: "POST" });
    await pollRewind();
  } catch (e) {
    console.error("Failed to toggle auto-rewind:", e);
  }
}

async function updateAutoRewindPct(pct) {
  try {
    await fetch("/rewind/monitor/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ auto_rewind_percentage: parseFloat(pct) })
    });
  } catch (e) {
    console.error("Failed to update auto-rewind percentage:", e);
  }
}

async function updateManualRewindPct(pct) {
  try {
    await fetch("/rewind/monitor/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manual_rewind_percentage: parseFloat(pct) })
    });
  } catch (e) {
    console.error("Failed to update manual-rewind percentage:", e);
  }
}

async function clearTrajectory(btn) {
  if (!confirm("Clear all trajectory waypoints?")) return;
  btn.disabled = true;
  try {
    const resp = await fetch("/rewind/trajectory/clear", { method: "POST" });
    const result = await resp.json();
    if (result.success) {
      document.getElementById("trajectory-length").textContent = "0";
      await pollRewind();
      await pollTrajectory();
    } else {
      alert("Failed to clear trajectory");
    }
  } catch (e) {
    console.error("Failed to clear trajectory:", e);
    alert("Error: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function triggerManualRewind(btn) {
  btn.disabled = true;
  try {
    const lease = await ensureLease();
    if (!lease) {
      alert("Failed to acquire lease for rewind");
      return;
    }
    const resp = await fetch("/rewind/manual", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Lease-Id": lease
      },
      body: JSON.stringify({ dry_run: false })
    });
    if (resp.status === 403) {
      leaseId = null; // Clear invalid lease
      alert("Lease expired. Please try again.");
      return;
    }
    const result = await resp.json();
    if (!result.success && result.error) {
      alert("Rewind failed: " + result.error);
    }
    await pollRewind();
  } catch (e) {
    console.error("Failed to trigger manual rewind:", e);
    alert("Error: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function resetToHome(btn) {
  btn.disabled = true;
  try {
    const lease = await ensureLease();
    if (!lease) {
      alert("Failed to acquire lease");
      return;
    }
    const resp = await fetch("/rewind/reset-to-home", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Lease-Id": lease
      },
      body: JSON.stringify({ dry_run: false })
    });
    if (resp.status === 403) {
      leaseId = null; // Clear invalid lease
      alert("Lease expired. Please try again.");
      return;
    }
    const result = await resp.json();
    if (!result.success && result.error) {
      alert("Reset failed: " + result.error);
    }
    await pollRewind();
  } catch (e) {
    console.error("Failed to reset to home:", e);
    alert("Error: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function pollRewind() {
  try {
    // Get rewind status
    const statusResp = await fetch("/rewind/status");
    const status = await statusResp.json();

    // Update trajectory length
    document.getElementById("trajectory-length").textContent = status.trajectory_length || 0;

    // Update rewind status
    const rewindStatusEl = document.getElementById("rewind-status");
    const resetStatusEl = document.getElementById("reset-status");
    if (status.is_rewinding) {
      rewindStatusEl.textContent = "Rewinding...";
      rewindStatusEl.style.color = "#ff9800";
      resetStatusEl.textContent = "Rewinding...";
      resetStatusEl.style.color = "#9c27b0";
    } else {
      rewindStatusEl.textContent = "Idle";
      rewindStatusEl.style.color = "#4caf50";
      resetStatusEl.textContent = "Idle";
      resetStatusEl.style.color = "#4caf50";
    }

    // Update boundary status
    const boundaryEl = document.getElementById("boundary-status");
    const boundaryStatus = status.base_boundary_status || {};
    if (boundaryStatus.out_of_bounds) {
      boundaryEl.textContent = "OUT OF BOUNDS";
      boundaryEl.className = "boundary-status warning";
    } else {
      boundaryEl.textContent = "Safe";
      boundaryEl.className = "boundary-status safe";
    }

    // Get monitor status
    const monitorResp = await fetch("/rewind/monitor/status");
    const monitor = await monitorResp.json();

    // Update auto-rewind toggle
    const toggle = document.getElementById("auto-rewind-toggle");
    if (toggle && toggle !== document.activeElement) {
      toggle.checked = monitor.auto_rewind_enabled;
    }

    // Update badge
    const badge = document.getElementById("auto-rewind-badge");
    if (monitor.auto_rewind_enabled) {
      badge.textContent = "Enabled";
      badge.className = "status-badge enabled";
    } else {
      badge.textContent = "Disabled";
      badge.className = "status-badge disabled";
    }

    // Update percentage inputs (only if not focused)
    const autoPctEl = document.getElementById("auto-rewind-pct");
    if (autoPctEl && autoPctEl !== document.activeElement) {
      autoPctEl.value = monitor.auto_rewind_percentage || 10;
    }
    const manualPctEl = document.getElementById("manual-rewind-pct");
    if (manualPctEl && manualPctEl !== document.activeElement) {
      manualPctEl.value = monitor.manual_rewind_percentage || 5;
    }

  } catch (e) {
    console.error("Rewind poll error:", e);
  }
}

// Trajectory visualization
let trajectoryCanvas = null;
let trajectoryCtx = null;
let workspaceBounds = { x_min: -5, x_max: 5, y_min: -5, y_max: 5 };

function initTrajectoryCanvas() {
  trajectoryCanvas = document.getElementById("trajectory-canvas");
  if (!trajectoryCanvas) return;

  // Set actual pixel size for sharp rendering
  const container = trajectoryCanvas.parentElement;
  const size = Math.min(container.clientWidth, container.clientHeight) || 400;
  trajectoryCanvas.width = size;
  trajectoryCanvas.height = size;
  trajectoryCtx = trajectoryCanvas.getContext("2d");
}

function worldToCanvas(x, y) {
  // Map world coordinates to canvas coordinates
  // Add padding around workspace bounds
  const padding = 1.0; // 1 meter padding
  const xMin = workspaceBounds.x_min - padding;
  const xMax = workspaceBounds.x_max + padding;
  const yMin = workspaceBounds.y_min - padding;
  const yMax = workspaceBounds.y_max + padding;

  const xRange = xMax - xMin;
  const yRange = yMax - yMin;
  const scale = Math.min(trajectoryCanvas.width / xRange, trajectoryCanvas.height / yRange);

  const cx = (x - xMin) * scale;
  const cy = trajectoryCanvas.height - (y - yMin) * scale; // Flip Y axis
  return { x: cx, y: cy };
}

function drawTrajectory(waypoints, currentPose) {
  if (!trajectoryCtx || !trajectoryCanvas) {
    initTrajectoryCanvas();
    if (!trajectoryCtx) return;
  }

  const ctx = trajectoryCtx;
  const w = trajectoryCanvas.width;
  const h = trajectoryCanvas.height;

  // Clear canvas
  ctx.fillStyle = "#0d1117";
  ctx.fillRect(0, 0, w, h);

  // Draw grid
  ctx.strokeStyle = "#1a2744";
  ctx.lineWidth = 1;
  const padding = 1.0;
  const xMin = workspaceBounds.x_min - padding;
  const xMax = workspaceBounds.x_max + padding;
  const yMin = workspaceBounds.y_min - padding;
  const yMax = workspaceBounds.y_max + padding;

  // Draw 1m grid lines
  for (let x = Math.ceil(xMin); x <= Math.floor(xMax); x++) {
    const p = worldToCanvas(x, 0);
    ctx.beginPath();
    ctx.moveTo(p.x, 0);
    ctx.lineTo(p.x, h);
    ctx.stroke();
  }
  for (let y = Math.ceil(yMin); y <= Math.floor(yMax); y++) {
    const p = worldToCanvas(0, y);
    ctx.beginPath();
    ctx.moveTo(0, p.y);
    ctx.lineTo(w, p.y);
    ctx.stroke();
  }

  // Draw origin axes
  ctx.strokeStyle = "#30363d";
  ctx.lineWidth = 2;
  const origin = worldToCanvas(0, 0);
  ctx.beginPath();
  ctx.moveTo(0, origin.y);
  ctx.lineTo(w, origin.y);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(origin.x, 0);
  ctx.lineTo(origin.x, h);
  ctx.stroke();

  // Draw workspace boundary
  ctx.strokeStyle = "#f44336";
  ctx.lineWidth = 2;
  ctx.setLineDash([8, 4]);
  const bl = worldToCanvas(workspaceBounds.x_min, workspaceBounds.y_min);
  const tr = worldToCanvas(workspaceBounds.x_max, workspaceBounds.y_max);
  ctx.strokeRect(bl.x, tr.y, tr.x - bl.x, bl.y - tr.y);
  ctx.setLineDash([]);

  // Draw trajectory path
  if (waypoints && waypoints.length > 1) {
    ctx.strokeStyle = "#1976d2";
    ctx.lineWidth = 2;
    ctx.beginPath();

    for (let i = 0; i < waypoints.length; i++) {
      const wp = waypoints[i];
      const pose = wp.base_pose || [0, 0, 0];
      const p = worldToCanvas(pose[0], pose[1]);

      if (i === 0) {
        ctx.moveTo(p.x, p.y);
      } else {
        ctx.lineTo(p.x, p.y);
      }
    }
    ctx.stroke();

    // Draw start position
    if (waypoints.length > 0) {
      const startPose = waypoints[0].base_pose || [0, 0, 0];
      const startP = worldToCanvas(startPose[0], startPose[1]);
      ctx.fillStyle = "#9c27b0";
      ctx.beginPath();
      ctx.arc(startP.x, startP.y, 6, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // Draw current position
  if (currentPose && currentPose.length >= 2) {
    const p = worldToCanvas(currentPose[0], currentPose[1]);

    // Draw direction indicator
    const theta = currentPose[2] || 0;
    const arrowLen = 15;
    ctx.strokeStyle = "#4caf50";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    ctx.lineTo(p.x + arrowLen * Math.cos(-theta + Math.PI/2), p.y + arrowLen * Math.sin(-theta + Math.PI/2));
    ctx.stroke();

    // Draw position dot
    ctx.fillStyle = "#4caf50";
    ctx.shadowColor = "#4caf50";
    ctx.shadowBlur = 10;
    ctx.beginPath();
    ctx.arc(p.x, p.y, 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // Draw axis labels
  ctx.fillStyle = "#666";
  ctx.font = "11px sans-serif";
  ctx.fillText("X", w - 15, origin.y - 5);
  ctx.fillText("Y", origin.x + 5, 15);
}

async function pollTrajectory() {
  try {
    // Get trajectory data
    const trajResp = await fetch("/trajectory");
    const trajData = await trajResp.json();
    const waypoints = trajData.waypoints || [];

    // Get workspace bounds from rewind status
    const statusResp = await fetch("/rewind/status");
    const status = await statusResp.json();
    const boundary = status.base_boundary_status || {};

    if (boundary.x_min !== undefined) {
      workspaceBounds = {
        x_min: boundary.x_min,
        x_max: boundary.x_max,
        y_min: boundary.y_min,
        y_max: boundary.y_max
      };
    }

    // Get current pose from state
    const stateResp = await fetch("/state");
    const state = await stateResp.json();
    const currentPose = state.base?.pose || [0, 0, 0];

    // Update info display
    document.getElementById("traj-points").textContent = waypoints.length;

    // Calculate duration
    if (waypoints.length > 1) {
      const duration = waypoints[waypoints.length - 1].t - waypoints[0].t;
      document.getElementById("traj-duration").textContent = duration.toFixed(1) + "s";
    } else {
      document.getElementById("traj-duration").textContent = "0.0s";
    }

    document.getElementById("traj-x").textContent = currentPose[0].toFixed(3) + " m";
    document.getElementById("traj-y").textContent = currentPose[1].toFixed(3) + " m";

    // Draw trajectory
    drawTrajectory(waypoints, currentPose);

  } catch (e) {
    console.error("Trajectory poll error:", e);
  }
}

// Initialize canvas on load
window.addEventListener("load", initTrajectoryCanvas);
window.addEventListener("resize", initTrajectoryCanvas);

// Rewind logs polling
async function pollRewindLogs() {
  try {
    const resp = await fetch("/rewind/logs?limit=50");
    const data = await resp.json();
    const logsEl = document.getElementById("rewind-logs");
    if (!logsEl) return;

    const logs = data.logs || [];
    if (logs.length === 0) {
      logsEl.innerHTML = '<span style="color: #666;">No logs yet...</span>';
      return;
    }

    // Format logs with colors based on level
    const html = logs.map(log => {
      const time = log.timestamp.split("T")[1].split(".")[0];  // HH:MM:SS
      let color = "#8b949e";  // Default gray
      if (log.level === "ERROR" || log.level === "CRITICAL") {
        color = "#f85149";  // Red for errors
      } else if (log.level === "WARNING") {
        color = "#d29922";  // Orange for warnings
      } else if (log.level === "INFO") {
        color = "#8b949e";  // Gray for info
      }
      return `<div style="color: ${color};">[${time}] ${log.message}</div>`;
    }).join("");

    logsEl.innerHTML = html;
    // Auto-scroll to bottom
    logsEl.scrollTop = logsEl.scrollHeight;
  } catch (e) {
    console.error("Rewind logs poll error:", e);
  }
}

poll();
pollState();
pollRewind();
pollTrajectory();
pollRewindLogs();
setInterval(poll, 2000);
setInterval(pollState, 200);
setInterval(pollRewind, 500);
setInterval(pollTrajectory, 500);
setInterval(pollRewindLogs, 1000);
</script></body></html>"""


def create_router(service_mgr: ServiceManager):
    """Create the service routes with injected dependencies."""

    @router.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        """Web dashboard for service management."""
        return DASHBOARD_HTML

    @router.get("")
    async def list_services():
        """List all services with status, PID, uptime."""
        return service_mgr.get_status()

    @router.post("/unlock/lock")
    async def lock_robot():
        """Lock the robot by stopping the unlock service.

        The unlock service runs with relock_on_exit=True and signal handlers,
        so stopping it will automatically: deactivate FCI, lock brakes, release token.
        """
        await service_mgr.stop_service("unlock")

        state = service_mgr._services.get("unlock")
        if state:
            state.logs.append("[lock: stopped unlock service, cleanup will lock robot]")

        return {"ok": True, "message": "Robot locked (unlock service stopped)"}

    @router.get("/{name}")
    async def get_service(name: str):
        """Get status of a specific service."""
        result = service_mgr.get_status(name)
        if "error" in result:
            return {"ok": False, **result}
        return result

    @router.post("/{name}/start")
    async def start_service(name: str):
        """Start a service."""
        return await service_mgr.start_service(name)

    @router.post("/{name}/stop")
    async def stop_service(name: str):
        """Stop a service."""
        return await service_mgr.stop_service(name)

    @router.post("/{name}/restart")
    async def restart_service(name: str):
        """Restart a service."""
        return await service_mgr.restart_service(name)

    @router.get("/{name}/logs")
    async def get_logs(name: str, lines: int = Query(default=50, ge=1, le=1000)):
        """Get recent log output for a service."""
        return service_mgr.get_logs(name, lines=lines)

    return router
