#!/usr/bin/env python3
"""
Worker Performance Monitor
==========================

Real-time Monitoring für alle Worker-Instanzen mit
Performance-Metriken, Health Checks und Optimierungsempfehlungen.

Features:
- ✅ Real-time Worker Monitoring
- ✅ Performance-Analyse
- ✅ Resource-Usage Tracking
- ✅ Optimierungsempfehlungen
- ✅ Alerting bei Problemen
"""

import os
import sys
import time
import json
import logging
import psutil
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from collections import deque
import pika

# ASCII Sky Imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.interpolation_config import get_config_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class WorkerStats:
    """Statistiken für einen einzelnen Worker"""
    worker_id: str
    worker_type: str
    status: str
    uptime_seconds: float
    tasks_processed: int
    tasks_failed: int
    success_rate: float
    avg_processing_time: float
    memory_usage_mb: float
    cpu_usage_percent: float
    last_heartbeat: datetime
    queue_name: str
    current_task: Optional[str] = None


@dataclass
class SystemStats:
    """System-weite Statistiken"""
    total_workers: int
    active_workers: int
    total_tasks_processed: int
    total_tasks_failed: int
    system_memory_usage_mb: float
    system_cpu_usage_percent: float
    queue_sizes: Dict[str, int]
    avg_worker_success_rate: float
    recommendations: List[str]


class WorkerMonitor:
    """
    Monitor für alle Worker-Instanzen
    """
    
    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url
        self.connection = None
        self.channel = None
        
        # Worker Registry
        self.workers: Dict[str, WorkerStats] = {}
        self.system_stats = SystemStats(
            total_workers=0,
            active_workers=0,
            total_tasks_processed=0,
            total_tasks_failed=0,
            system_memory_usage_mb=0.0,
            system_cpu_usage_percent=0.0,
            queue_sizes={},
            avg_worker_success_rate=0.0,
            recommendations=[]
        )
        
        # Performance History
        self.performance_history = deque(maxlen=1000)  # Letzte 1000 Datenpunkte
        
        # Monitoring Thread
        self.monitoring_active = False
        self.monitoring_thread = None
        
        logger.info("Worker Monitor initialized")
    
    def connect(self) -> bool:
        """Verbinde zu RabbitMQ"""
        try:
            params = pika.URLParameters(self.rabbitmq_url)
            params.heartbeat = 600
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
            
            # Status Queue deklarieren
            self.channel.queue_declare(
                queue='computation.status',
                durable=False,
                arguments={'x-message-ttl': 300000}
            )
            
            # Health Check Queue
            self.channel.queue_declare(
                queue='worker.health',
                durable=False,
                arguments={'x-message-ttl': 60000}
            )
            
            logger.info("Worker Monitor connected to RabbitMQ")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            return False
    
    def start_monitoring(self):
        """Starte das Monitoring"""
        if not self.connect():
            logger.error("Cannot start monitoring - connection failed")
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        logger.info("Worker Monitor started")
    
    def stop_monitoring(self):
        """Stoppe das Monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        if self.connection and not self.connection.is_closed:
            self.connection.close()
        
        logger.info("Worker Monitor stopped")
    
    def _monitoring_loop(self):
        """Haupt-Monitoring Loop"""
        status_consumer = None
        
        try:
            # Starte Status Consumer
            status_consumer = threading.Thread(target=self._status_consumer_loop, daemon=True)
            status_consumer.start()
            
            while self.monitoring_active:
                # System Stats aktualisieren
                self._update_system_stats()
                
                # Health Checks durchführen
                self._perform_health_checks()
                
                # Optimierungsempfehlungen generieren
                self._generate_recommendations()
                
                # Performance History speichern
                self._save_performance_snapshot()
                
                # Warte 30 Sekunden
                time.sleep(30)
        
        except Exception as e:
            logger.error(f"Monitoring loop error: {e}", exc_info=True)
        finally:
            self.monitoring_active = False
    
    def _status_consumer_loop(self):
        """Consumer für Worker Status Messages"""
        def callback(ch, method, properties, body):
            try:
                status_msg = json.loads(body)
                self._process_worker_status(status_msg)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception as e:
                logger.error(f"Error processing status message: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        try:
            self.channel.basic_consume(
                queue='computation.status',
                on_message_callback=callback,
                auto_ack=False
            )
            
            while self.monitoring_active:
                self.channel.process_data_events(time_limit=1)
        
        except Exception as e:
            logger.error(f"Status consumer error: {e}")
    
    def _process_worker_status(self, status_msg: Dict[str, Any]):
        """Verarbeite Worker Status Message"""
        try:
            worker_id = status_msg['worker_id']
            timestamp = datetime.fromisoformat(status_msg['timestamp'].replace('Z', '+00:00'))
            
            # Aktualisiere oder erstelle Worker Stats
            if worker_id not in self.workers:
                self.workers[worker_id] = WorkerStats(
                    worker_id=worker_id,
                    worker_type=status_msg.get('worker_type', 'unknown'),
                    status='active',
                    uptime_seconds=0,
                    tasks_processed=0,
                    tasks_failed=0,
                    success_rate=1.0,
                    avg_processing_time=0.0,
                    memory_usage_mb=0.0,
                    cpu_usage_percent=0.0,
                    last_heartbeat=timestamp,
                    queue_name='unknown'
                )
            
            worker = self.workers[worker_id]
            worker.last_heartbeat = timestamp
            worker.status = status_msg.get('status', 'active')
            
            # Update Metriken falls vorhanden
            if 'tasks_processed' in status_msg:
                worker.tasks_processed = status_msg['tasks_processed']
            if 'tasks_failed' in status_msg:
                worker.tasks_failed = status_msg['tasks_failed']
            if 'memory_usage_mb' in status_msg:
                worker.memory_usage_mb = status_msg['memory_usage_mb']
            if 'cpu_usage_percent' in status_msg:
                worker.cpu_usage_percent = status_msg['cpu_usage_percent']
            
            # Berechne Success Rate
            if worker.tasks_processed > 0:
                worker.success_rate = (worker.tasks_processed - worker.tasks_failed) / worker.tasks_processed
            
            logger.debug(f"Updated status for worker {worker_id}")
            
        except Exception as e:
            logger.error(f"Error processing worker status: {e}")
    
    def _update_system_stats(self):
        """Aktualisiere System-weite Statistiken"""
        try:
            # Worker Stats aggregieren
            self.system_stats.total_workers = len(self.workers)
            self.system_stats.active_workers = sum(1 for w in self.workers.values() 
                                                  if w.status == 'active')
            
            self.system_stats.total_tasks_processed = sum(w.tasks_processed for w in self.workers.values())
            self.system_stats.total_tasks_failed = sum(w.tasks_failed for w in self.workers.values())
            
            # Durchschnittliche Success Rate
            if self.system_stats.total_workers > 0:
                self.system_stats.avg_worker_success_rate = (
                    sum(w.success_rate for w in self.workers.values()) / self.system_stats.total_workers
                )
            
            # System Resource Usage
            self.system_stats.system_memory_usage_mb = psutil.virtual_memory().used / 1024 / 1024
            self.system_stats.system_cpu_usage_percent = psutil.cpu_percent(interval=1)
            
            # Queue Sizes
            self.system_stats.queue_sizes = self._get_queue_sizes()
            
        except Exception as e:
            logger.error(f"Error updating system stats: {e}")
    
    def _get_queue_sizes(self) -> Dict[str, int]:
        """Hole Queue Größen von RabbitMQ"""
        queue_sizes = {}
        
        try:
            queues = ['precompute.tasks', 'asteroid.compute', 'comet.compute']
            
            for queue_name in queues:
                try:
                    method = self.channel.queue_declare(queue=queue_name, passive=True)
                    queue_sizes[queue_name] = method.method.message_count
                except Exception:
                    queue_sizes[queue_name] = 0
        
        except Exception as e:
            logger.error(f"Error getting queue sizes: {e}")
        
        return queue_sizes
    
    def _perform_health_checks(self):
        """Führe Health Checks für alle Worker durch"""
        current_time = datetime.now(timezone.utc)
        timeout_threshold = timedelta(minutes=2)  # 2 Minuten Timeout
        
        for worker_id, worker in list(self.workers.items()):
            # Prüfe Heartbeat Timeout
            if current_time - worker.last_heartbeat > timeout_threshold:
                worker.status = 'timeout'
                logger.warning(f"Worker {worker_id} timeout - last heartbeat {worker.last_heartbeat}")
            
            # Prüfe Resource Limits
            if worker.memory_usage_mb > 512:  # 512MB Limit
                logger.warning(f"Worker {worker_id} high memory usage: {worker.memory_usage_mb:.1f}MB")
            
            if worker.cpu_usage_percent > 90:  # 90% CPU Limit
                logger.warning(f"Worker {worker_id} high CPU usage: {worker.cpu_usage_percent:.1f}%")
            
            # Prüfe Success Rate
            if worker.success_rate < 0.8 and worker.tasks_processed > 10:  # <80% Success Rate
                logger.warning(f"Worker {worker_id} low success rate: {worker.success_rate:.2%}")
    
    def _generate_recommendations(self):
        """Generiere Optimierungsempfehlungen"""
        recommendations = []
        
        try:
            # Worker Count Empfehlungen
            if self.system_stats.active_workers < self.system_stats.total_workers * 0.8:
                recommendations.append("Consider restarting failed workers")
            
            # Queue Size Empfehlungen
            for queue_name, size in self.system_stats.queue_sizes.items():
                if size > 100:
                    recommendations.append(f"Queue {queue_name} has {size} pending tasks - consider scaling workers")
            
            # Resource Usage Empfehlungen
            if self.system_stats.system_memory_usage_mb > 4096:  # 4GB
                recommendations.append("High system memory usage - consider optimizing or adding memory")
            
            if self.system_stats.system_cpu_usage_percent > 80:
                recommendations.append("High CPU usage - consider adding more worker instances")
            
            # Success Rate Empfehlungen
            if self.system_stats.avg_worker_success_rate < 0.9:
                recommendations.append("Low success rate detected - check for computation errors")
            
            self.system_stats.recommendations = recommendations
        
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
    
    def _save_performance_snapshot(self):
        """Speichere Performance Snapshot in History"""
        try:
            snapshot = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'system_stats': asdict(self.system_stats),
                'worker_count': len(self.workers)
            }
            
            self.performance_history.append(snapshot)
        
        except Exception as e:
            logger.error(f"Error saving performance snapshot: {e}")
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Gibt Dashboard-Daten zurück"""
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'system_stats': asdict(self.system_stats),
            'workers': {wid: asdict(w) for wid, w in self.workers.items()},
            'performance_trend': list(self.performance_history)[-10:]  # Letzte 10 Datenpunkte
        }
    
    def get_worker_details(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Gibt detaillierte Worker-Informationen zurück"""
        if worker_id in self.workers:
            return asdict(self.workers[worker_id])
        return None
    
    def get_optimization_report(self) -> Dict[str, Any]:
        """Gibt detaillierten Optimierungs-Report zurück"""
        # Analysiere Performance-Trends
        if len(self.performance_history) < 2:
            return {'error': 'Insufficient data for analysis'}
        
        recent_snapshots = list(self.performance_history)[-10:]
        
        # Trend-Analyse
        task_trend = []
        memory_trend = []
        
        for snapshot in recent_snapshots:
            task_trend.append(snapshot['system_stats']['total_tasks_processed'])
            memory_trend.append(snapshot['system_stats']['system_memory_usage_mb'])
        
        return {
            'analysis_period': f"{len(recent_snapshots)} snapshots",
            'task_processing_trend': 'increasing' if task_trend[-1] > task_trend[0] else 'decreasing',
            'memory_usage_trend': 'increasing' if memory_trend[-1] > memory_trend[0] else 'stable',
            'current_recommendations': self.system_stats.recommendations,
            'performance_score': self._calculate_performance_score(),
            'optimization_potential': self._assess_optimization_potential()
        }
    
    def _calculate_performance_score(self) -> float:
        """Berechne Performance Score (0-100)"""
        try:
            # Faktoren für Performance Score
            success_rate_weight = 0.4
            resource_efficiency_weight = 0.3
            throughput_weight = 0.3
            
            # Success Rate Score
            success_score = self.system_stats.avg_worker_success_rate * 100
            
            # Resource Efficiency Score (niedriger ist besser)
            memory_score = max(0, 100 - (self.system_stats.system_memory_usage_mb / 4096) * 100)
            cpu_score = max(0, 100 - self.system_stats.system_cpu_usage_percent)
            resource_score = (memory_score + cpu_score) / 2
            
            # Throughput Score (Tasks pro Minute)
            if len(self.performance_history) >= 2:
                first = self.performance_history[0]
                last = self.performance_history[-1]
                time_diff = (datetime.fromisoformat(last['timestamp']) - 
                           datetime.fromisoformat(first['timestamp'])).total_seconds() / 60
                if time_diff > 0:
                    task_diff = last['system_stats']['total_tasks_processed'] - first['system_stats']['total_tasks_processed']
                    throughput_score = min(100, (task_diff / time_diff) * 10)  # 10 Tasks/Minute = 100 Punkte
                else:
                    throughput_score = 0
            else:
                throughput_score = 0
            
            # Gesamtscore
            total_score = (
                success_score * success_rate_weight +
                resource_score * resource_efficiency_weight +
                throughput_score * throughput_weight
            )
            
            return round(total_score, 1)
        
        except Exception as e:
            logger.error(f"Error calculating performance score: {e}")
            return 0.0
    
    def _assess_optimization_potential(self) -> str:
        """Bewerte Optimierungspotential"""
        score = self._calculate_performance_score()
        
        if score >= 80:
            return "low"
        elif score >= 60:
            return "medium"
        else:
            return "high"


def main():
    """Hauptfunktion für Standalone Monitor"""
    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://admin:changeme@localhost:5672/')
    
    monitor = WorkerMonitor(rabbitmq_url)
    
    try:
        monitor.start_monitoring()
        
        # Periodische Dashboard-Ausgabe
        while True:
            time.sleep(60)  # Jede Minute
            
            dashboard = monitor.get_dashboard_data()
            print("\n" + "=" * 60)
            print(f"Worker Monitor Dashboard - {dashboard['timestamp']}")
            print("=" * 60)
            print(f"Active Workers: {dashboard['system_stats']['active_workers']}/{dashboard['system_stats']['total_workers']}")
            print(f"Tasks Processed: {dashboard['system_stats']['total_tasks_processed']}")
            print(f"Success Rate: {dashboard['system_stats']['avg_worker_success_rate']:.2%}")
            print(f"System Memory: {dashboard['system_stats']['system_memory_usage_mb']:.1f}MB")
            print(f"System CPU: {dashboard['system_stats']['system_cpu_usage_percent']:.1f}%")
            
            if dashboard['system_stats']['recommendations']:
                print("\nRecommendations:")
                for rec in dashboard['system_stats']['recommendations']:
                    print(f"  • {rec}")
            
            print("=" * 60)
    
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
    finally:
        monitor.stop_monitoring()


if __name__ == '__main__':
    main()
