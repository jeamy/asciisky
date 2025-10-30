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

import os
import sys
import json
import time
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from dataclasses import asdict

# Web Framework
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ASCII Sky Imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.worker_monitor import WorkerMonitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI App
app = FastAPI(
    title="Worker Monitor Dashboard",
    description="Real-time monitoring for ASCII Sky workers",
    version="2.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Monitor Instance
monitor = None

# WebSocket Connections
websocket_connections = set()


class ConnectionManager:
    """Manager für WebSocket Verbindungen"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
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
            except:
                # Remove dead connections
                self.active_connections.remove(connection)


manager = ConnectionManager()


@app.on_event("startup")
async def startup_event():
    """Initialisiere Monitor beim Startup"""
    global monitor
    
    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://admin:changeme@localhost:5672/')
    monitor = WorkerMonitor(rabbitmq_url)
    monitor.start_monitoring()
    
    logger.info("Worker Monitor Dashboard started")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup beim Shutdown"""
    global monitor
    
    if monitor:
        monitor.stop_monitoring()
    
    logger.info("Worker Monitor Dashboard stopped")


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Worker Monitor Dashboard - using existing ASCII Sky styles"""
    return FileResponse("templates/worker_monitor.html")


@app.get("/api/dashboard")
async def get_dashboard_data():
    """Gibt Dashboard-Daten zurück"""
    if not monitor:
        raise HTTPException(status_code=503, detail="Monitor not available")
    
    return monitor.get_dashboard_data()


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
