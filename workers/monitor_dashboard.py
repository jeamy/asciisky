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
from fastapi.responses import HTMLResponse, JSONResponse
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
    """Haupt-Dashboard HTML"""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>ASCII Sky - Worker Monitor</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .status-healthy { color: #10b981; }
        .status-warning { color: #f59e0b; }
        .status-error { color: #ef4444; }
        .metric-card { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            transition: transform 0.2s;
        }
        .metric-card:hover { transform: translateY(-2px); }
    </style>
</head>
<body class="bg-gray-900 text-white">
    <div class="container mx-auto px-4 py-8">
        <!-- Header -->
        <div class="text-center mb-8">
            <h1 class="text-4xl font-bold mb-2">🚀 ASCII Sky Worker Monitor</h1>
            <p class="text-gray-400">Real-time Performance Monitoring & Optimization</p>
        </div>

        <!-- System Overview -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div class="metric-card rounded-lg p-6 text-center">
                <div class="text-3xl font-bold" id="active-workers">-</div>
                <div class="text-sm opacity-75">Active Workers</div>
            </div>
            <div class="metric-card rounded-lg p-6 text-center">
                <div class="text-3xl font-bold" id="success-rate">-</div>
                <div class="text-sm opacity-75">Success Rate</div>
            </div>
            <div class="metric-card rounded-lg p-6 text-center">
                <div class="text-3xl font-bold" id="memory-usage">-</div>
                <div class="text-sm opacity-75">Memory (MB)</div>
            </div>
            <div class="metric-card rounded-lg p-6 text-center">
                <div class="text-3xl font-bold" id="cpu-usage">-</div>
                <div class="text-sm opacity-75">CPU Usage</div>
            </div>
        </div>

        <!-- Performance Charts -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            <div class="bg-gray-800 rounded-lg p-6">
                <h3 class="text-xl font-semibold mb-4">Task Processing Trend</h3>
                <canvas id="taskChart" width="400" height="200"></canvas>
            </div>
            <div class="bg-gray-800 rounded-lg p-6">
                <h3 class="text-xl font-semibold mb-4">Resource Usage</h3>
                <canvas id="resourceChart" width="400" height="200"></canvas>
            </div>
        </div>

        <!-- Worker Details -->
        <div class="bg-gray-800 rounded-lg p-6 mb-8">
            <h3 class="text-xl font-semibold mb-4">Worker Details</h3>
            <div class="overflow-x-auto">
                <table class="w-full text-sm">
                    <thead>
                        <tr class="border-b border-gray-700">
                            <th class="text-left py-2">Worker ID</th>
                            <th class="text-left py-2">Type</th>
                            <th class="text-left py-2">Status</th>
                            <th class="text-left py-2">Tasks</th>
                            <th class="text-left py-2">Success Rate</th>
                            <th class="text-left py-2">Memory (MB)</th>
                            <th class="text-left py-2">CPU %</th>
                            <th class="text-left py-2">Last Heartbeat</th>
                        </tr>
                    </thead>
                    <tbody id="worker-table">
                        <!-- Dynamically populated -->
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Queue Status -->
        <div class="bg-gray-800 rounded-lg p-6 mb-8">
            <h3 class="text-xl font-semibold mb-4">Queue Status</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4" id="queue-status">
                <!-- Dynamically populated -->
            </div>
        </div>

        <!-- Recommendations -->
        <div class="bg-gray-800 rounded-lg p-6 mb-8">
            <h3 class="text-xl font-semibold mb-4">🎯 Optimization Recommendations</h3>
            <div id="recommendations" class="space-y-2">
                <!-- Dynamically populated -->
            </div>
        </div>

        <!-- Actions -->
        <div class="text-center">
            <button onclick="refreshData()" class="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded-lg mr-2">
                🔄 Refresh
            </button>
            <button onclick="toggleAutoRefresh()" id="auto-refresh-btn" class="bg-green-600 hover:bg-green-700 px-6 py-2 rounded-lg">
                ⏸️ Auto Refresh
            </button>
        </div>
    </div>

    <script>
        // WebSocket Connection
        const ws = new WebSocket('ws://localhost:8080/ws');
        let autoRefresh = true;
        let refreshInterval;

        // Chart instances
        let taskChart, resourceChart;

        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            updateDashboard(data);
        };

        function initCharts() {
            // Task Processing Chart
            const taskCtx = document.getElementById('taskChart').getContext('2d');
            taskChart = new Chart(taskCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Tasks Processed',
                        data: [],
                        borderColor: 'rgb(59, 130, 246)',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: { beginAtZero: true }
                    }
                }
            });

            // Resource Usage Chart
            const resourceCtx = document.getElementById('resourceChart').getContext('2d');
            resourceChart = new Chart(resourceCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Memory (MB)',
                        data: [],
                        borderColor: 'rgb(239, 68, 68)',
                        backgroundColor: 'rgba(239, 68, 68, 0.1)',
                        tension: 0.4
                    }, {
                        label: 'CPU %',
                        data: [],
                        borderColor: 'rgb(34, 197, 94)',
                        backgroundColor: 'rgba(34, 197, 94, 0.1)',
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: { beginAtZero: true }
                    }
                }
            });
        }

        function updateDashboard(data) {
            // Update metrics
            document.getElementById('active-workers').textContent = data.system_stats.active_workers;
            document.getElementById('success-rate').textContent = (data.system_stats.avg_worker_success_rate * 100).toFixed(1) + '%';
            document.getElementById('memory-usage').textContent = data.system_stats.system_memory_usage_mb.toFixed(1);
            document.getElementById('cpu-usage').textContent = data.system_stats.system_cpu_usage_percent.toFixed(1);

            // Update worker table
            const workerTable = document.getElementById('worker-table');
            workerTable.innerHTML = '';
            
            Object.values(data.workers).forEach(worker => {
                const row = document.createElement('tr');
                row.className = 'border-b border-gray-700';
                
                const statusClass = worker.status === 'active' ? 'status-healthy' : 
                                  worker.status === 'timeout' ? 'status-warning' : 'status-error';
                
                row.innerHTML = `
                    <td class="py-2">${worker.worker_id}</td>
                    <td class="py-2">${worker.worker_type}</td>
                    <td class="py-2 ${statusClass}">${worker.status}</td>
                    <td class="py-2">${worker.tasks_processed}</td>
                    <td class="py-2">${(worker.success_rate * 100).toFixed(1)}%</td>
                    <td class="py-2">${worker.memory_usage_mb.toFixed(1)}</td>
                    <td class="py-2">${worker.cpu_usage_percent.toFixed(1)}</td>
                    <td class="py-2">${new Date(worker.last_heartbeat).toLocaleTimeString()}</td>
                `;
                workerTable.appendChild(row);
            });

            // Update queue status
            const queueStatus = document.getElementById('queue-status');
            queueStatus.innerHTML = '';
            
            Object.entries(data.system_stats.queue_sizes).forEach(([queue, size]) => {
                const queueDiv = document.createElement('div');
                queueDiv.className = 'bg-gray-700 rounded p-4 text-center';
                
                const color = size > 100 ? 'text-red-400' : size > 50 ? 'text-yellow-400' : 'text-green-400';
                
                queueDiv.innerHTML = `
                    <div class="text-2xl font-bold ${color}">${size}</div>
                    <div class="text-sm opacity-75">${queue}</div>
                `;
                queueStatus.appendChild(queueDiv);
            });

            // Update recommendations
            const recommendations = document.getElementById('recommendations');
            recommendations.innerHTML = '';
            
            if (data.system_stats.recommendations.length === 0) {
                recommendations.innerHTML = '<div class="text-green-400">✅ All systems running optimally!</div>';
            } else {
                data.system_stats.recommendations.forEach(rec => {
                    const recDiv = document.createElement('div');
                    recDiv.className = 'flex items-center space-x-2 text-yellow-400';
                    recDiv.innerHTML = `<span>⚠️</span><span>${rec}</span>`;
                    recommendations.appendChild(recDiv);
                });
            }

            // Update charts
            updateCharts(data);
        }

        function updateCharts(data) {
            const now = new Date().toLocaleTimeString();
            
            // Update task chart
            if (taskChart.data.labels.length > 20) {
                taskChart.data.labels.shift();
                taskChart.data.datasets[0].data.shift();
            }
            taskChart.data.labels.push(now);
            taskChart.data.datasets[0].data.push(data.system_stats.total_tasks_processed);
            taskChart.update();

            // Update resource chart
            if (resourceChart.data.labels.length > 20) {
                resourceChart.data.labels.shift();
                resourceChart.data.datasets[0].data.shift();
                resourceChart.data.datasets[1].data.shift();
            }
            resourceChart.data.labels.push(now);
            resourceChart.data.datasets[0].data.push(data.system_stats.system_memory_usage_mb);
            resourceChart.data.datasets[1].data.push(data.system_stats.system_cpu_usage_percent);
            resourceChart.update();
        }

        function refreshData() {
            fetch('/api/dashboard')
                .then(response => response.json())
                .then(data => updateDashboard(data))
                .catch(error => console.error('Error refreshing data:', error));
        }

        function toggleAutoRefresh() {
            autoRefresh = !autoRefresh;
            const btn = document.getElementById('auto-refresh-btn');
            
            if (autoRefresh) {
                btn.textContent = '⏸️ Auto Refresh';
                btn.className = 'bg-green-600 hover:bg-green-700 px-6 py-2 rounded-lg';
                refreshInterval = setInterval(refreshData, 5000);
            } else {
                btn.textContent = '▶️ Auto Refresh';
                btn.className = 'bg-gray-600 hover:bg-gray-700 px-6 py-2 rounded-lg';
                clearInterval(refreshInterval);
            }
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            initCharts();
            refreshData();
            toggleAutoRefresh(); // Start auto-refresh
        });
    </script>
</body>
</html>
    """


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
