#!/usr/bin/env python3
"""
Worker Monitor Web Dashboard
============================

Web-basiertes Dashboard für Worker-Monitoring mit:
- Real-time Performance Metriken
- Health Status Übersicht
- Optimierungsempfehlungen
- Worker Management Interface
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn

# Web Framework
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

# ASCII Sky Imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # For worker modules
from worker_monitor import WorkerMonitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global Monitor Instance
monitor = None

# WebSocket Connections
websocket_connections = set()


class ConnectionManager:
    """Manager für WebSocket Verbindungen"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                # Remove dead connections
                self.active_connections.remove(connection)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan Context Manager für Startup und Shutdown"""
    global monitor

    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://admin:changeme@localhost:5672/')
    monitor = WorkerMonitor(rabbitmq_url)
    monitor.start_monitoring()

    logger.info("Worker Monitor Dashboard started")

    yield

    if monitor:
        monitor.stop_monitoring()

    logger.info("Worker Monitor Dashboard stopped")


# FastAPI App
app = FastAPI(
    title="Worker Monitor Dashboard",
    description="Real-time monitoring for ASCII Sky workers",
    version="2.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Worker Monitor Dashboard - using existing ASCII Sky styles"""
    try:
        return FileResponse("templates/worker_monitor.html")
    except FileNotFoundError:
        # Fallback: Einfaches HTML wenn Template fehlt
        return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head>
    <title>Worker Monitor</title>
    <style>
        body { font-family: monospace; max-width: 1200px; margin: 50px auto; padding: 20px; background: #0a0a0a; color: #00ff00; }
        .status { padding: 20px; border: 1px solid #00ff00; margin: 20px 0; }
        .error { border-color: #ff0000; color: #ff0000; }
        .success { border-color: #00ff00; }
        h1 { text-align: center; }
        pre { background: #1a1a1a; padding: 15px; overflow-x: auto; }
        .refresh { text-align: center; margin: 20px 0; }
        button { background: #00ff00; color: #0a0a0a; border: none; padding: 10px 20px; cursor: pointer; font-family: monospace; }
    </style>
</head>
<body>
    <h1>🔧 Worker Monitor Dashboard</h1>
    <div class="status" id="status">
        <h2>Loading...</h2>
    </div>
    <div class="refresh">
        <button onclick="location.reload()">Refresh</button>
    </div>
    <script>
        async function loadStatus() {
            try {
                const response = await fetch('/api/dashboard');
                const data = await response.json();

                const statusDiv = document.getElementById('status');
                statusDiv.className = 'status success';
                statusDiv.innerHTML = `
                    <h2>✅ Monitor Active</h2>
                    <pre>${JSON.stringify(data, null, 2)}</pre>
                `;
            } catch (error) {
                const statusDiv = document.getElementById('status');
                statusDiv.className = 'status error';
                statusDiv.innerHTML = `
                    <h2>❌ Monitor Error</h2>
                    <p>Error: ${error.message}</p>
                    <p>Check if:</p>
                    <ul>
                        <li>RabbitMQ is running</li>
                        <li>Workers are sending status messages</li>
                        <li>computation.status queue exists</li>
                    </ul>
                `;
            }
        }

        loadStatus();
        setInterval(loadStatus, 5000);
    </script>
</body>
</html>
        """, status_code=200)


@app.get("/api/dashboard")
async def get_dashboard_data():
    """Gibt Dashboard-Daten zurück"""
    if not monitor:
        return JSONResponse(
            status_code=503,
            content={
                "error": "Monitor not available",
                "status": "unhealthy",
                "message": "Worker monitor is not initialized. Check RabbitMQ connection."
            }
        )

    try:
        return monitor.get_dashboard_data()
    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "status": "error",
                "message": "Failed to retrieve dashboard data"
            }
        )


@app.get("/api/workers/{worker_id}")
async def get_worker_details(worker_id: str):
    """Gibt Worker-Details zurück"""
    if not monitor:
        raise HTTPException(status_code=503, detail="Monitor not available")

    details = monitor.get_worker_details(worker_id)
    if not details:
        raise HTTPException(status_code=404, detail="Worker not found")

    return details


@app.get("/api/optimization-report")
async def get_optimization_report():
    """Gibt Optimierungs-Report zurück"""
    if not monitor:
        raise HTTPException(status_code=503, detail="Monitor not available")

    return monitor.get_optimization_report()


@app.get("/api/health")
async def health_check():
    """Health Check Endpoint"""
    if not monitor:
        return {"status": "unhealthy", "error": "Monitor not initialized"}

    try:
        dashboard_data = monitor.get_dashboard_data()
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workers": dashboard_data["system_stats"]["total_workers"],
            "active_workers": dashboard_data["system_stats"]["active_workers"]
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket für Real-time Updates"""
    await manager.connect(websocket)
    websocket_connections.add(websocket)

    try:
        while True:
            # Sende aktuelle Daten alle 5 Sekunden
            if monitor:
                data = monitor.get_dashboard_data()
                await websocket.send_text(json.dumps(data))

            await asyncio.sleep(5)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        websocket_connections.discard(websocket)


@app.post("/api/workers/{worker_id}/restart")
async def restart_worker(worker_id: str):
    """Worker neustarten (Admin Funktion)"""
    # TODO: Implement worker restart via Docker/RabbitMQ
    return {"message": f"Worker {worker_id} restart requested", "status": "pending"}


@app.post("/api/workers/scale")
async def scale_workers(worker_type: str, count: int):
    """Worker skalieren (Admin Funktion)"""
    # TODO: Implement worker scaling via Docker
    return {"message": f"Scaling {worker_type} workers to {count}", "status": "pending"}


def main():
    """Starte Dashboard Server"""
    host = os.getenv('MONITOR_HOST', '0.0.0.0')
    port = int(os.getenv('MONITOR_PORT', '8080'))

    print(f"Starting Worker Monitor Dashboard on http://{host}:{port}")
    print("=" * 60)
    print("Dashboard Features:")
    print("  • Real-time worker monitoring")
    print("  • Performance metrics and charts")
    print("  • Health status and alerts")
    print("  • Optimization recommendations")
    print("  • WebSocket live updates")
    print("=" * 60)

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == '__main__':
    main()
