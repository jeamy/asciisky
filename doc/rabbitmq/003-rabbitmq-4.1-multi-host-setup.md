# ASCII Sky - RabbitMQ 4.1 Multi-Host Setup Guide

## Übersicht

Dieser Guide beschreibt das Setup von RabbitMQ 4.1 Cluster auf 2-3 separaten Hosts in getrennten Netzwerken mit Docker.

## RabbitMQ 4.1 Neuerungen

### Was ist neu in RabbitMQ 4.1?

1. **Quorum Queue Performance**: Bis zu 2x schnellerer Durchsatz
2. **AMQP 1.0 Filter Expressions**: Selektives Message-Filtering
3. **Feature Flags Auto-Enable**: Automatische Aktivierung bei Cluster-Upgrade
4. **rabbitmqadmin v2**: Verbessertes CLI-Tool mit mehr Features
5. **Streams Performance**: Optimiert für hohen Durchsatz
6. **Erlang/OTP 27 Support**: Bessere Performance und Stabilität

### Vorteile von RabbitMQ 4.1

- ✅ **Schnellere Quorum Queues**: Bessere CPU-Auslastung
- ✅ **Niedrigere Latenz**: Optimierte Message-Delivery
- ✅ **Einfacheres Management**: Verbesserte UI und CLI
- ✅ **Bessere Observability**: Mehr Metriken und Tracing
- ✅ **Höhere Stabilität**: Weniger Memory-Leaks

## Architektur-Übersicht

### 3-Host Setup (Empfohlen)

```
┌─────────────────────────────────────────────────────────────┐
│                    Netzwerk 1 (192.168.1.0/24)              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Host 1 (192.168.1.10) - rabbitmq-1                  │   │
│  │  - Disc Node (Master)                                │   │
│  │  - Port 5672: AMQP                                   │   │
│  │  - Port 15672: Management UI                         │   │
│  │  - Port 25672: Inter-Node Communication              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Cluster Communication
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Netzwerk 2 (192.168.2.0/24)              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Host 2 (192.168.2.10) - rabbitmq-2                  │   │
│  │  - Disc Node                                         │   │
│  │  - Port 5672: AMQP                                   │   │
│  │  - Port 15672: Management UI                         │   │
│  │  - Port 25672: Inter-Node Communication              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Cluster Communication
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Netzwerk 3 (192.168.3.0/24)              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Host 3 (192.168.3.10) - rabbitmq-3                  │   │
│  │  - Disc Node                                         │   │
│  │  - Port 5672: AMQP                                   │   │
│  │  - Port 15672: Management UI                         │   │
│  │  - Port 25672: Inter-Node Communication              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Voraussetzungen

### Netzwerk-Anforderungen

#### Firewall-Regeln

```bash
# Port 5672: AMQP (Client-Kommunikation)
# Port 15672: Management UI
# Port 25672: Inter-Node Communication (Erlang Distribution)
# Port 4369: EPMD (Erlang Port Mapper Daemon)

# Beispiel: iptables auf jedem Host
# Host 1 erlaubt Zugriff von Host 2 und 3
iptables -A INPUT -p tcp --dport 5672 -s 192.168.2.10 -j ACCEPT
iptables -A INPUT -p tcp --dport 25672 -s 192.168.2.10 -j ACCEPT
iptables -A INPUT -p tcp --dport 4369 -s 192.168.2.10 -j ACCEPT
iptables -A INPUT -p tcp --dport 5672 -s 192.168.3.10 -j ACCEPT
iptables -A INPUT -p tcp --dport 25672 -s 192.168.3.10 -j ACCEPT
iptables -A INPUT -p tcp --dport 4369 -s 192.168.3.10 -j ACCEPT

# Management UI für alle (optional)
iptables -A INPUT -p tcp --dport 15672 -j ACCEPT

# Oder mit ufw (Ubuntu)
ufw allow from 192.168.2.10 to any port 5672 proto tcp
ufw allow from 192.168.2.10 to any port 25672 proto tcp
ufw allow from 192.168.2.10 to any port 4369 proto tcp
ufw allow 15672/tcp
```

### Hardware-Anforderungen

**Minimum (pro Host)**
- CPU: 2 Cores
- RAM: 4 GB
- Disk: 100 GB SSD
- Network: 1 Gbit/s

**Empfohlen (pro Host)**
- CPU: 4 Cores
- RAM: 8 GB
- Disk: 200 GB SSD
- Network: 10 Gbit/s

### Software-Anforderungen

- Docker 24.x oder höher
- Docker Compose 2.x oder höher
- Linux Kernel 5.x oder höher

## Installation

### Schritt 1: Erlang Cookie generieren

**Wichtig**: Der Erlang Cookie muss auf allen Hosts identisch sein!

```bash
# Auf einem beliebigen Host (nur einmal ausführen)
ERLANG_COOKIE=$(openssl rand -base64 32)
echo "ERLANG_COOKIE: $ERLANG_COOKIE"

# Beispiel-Ausgabe:
# ERLANG_COOKIE: xYz123AbC456DeF789GhI012JkL345Mn==
```

**Diesen Cookie in allen docker-compose Dateien verwenden!**

### Schritt 2: Docker Compose Dateien erstellen

#### Host 1 (192.168.1.10)

**Datei**: `docker-compose.rabbitmq.yml`

```yaml
version: '3.8'

services:
  rabbitmq-1:
    image: rabbitmq:4.1-management
    container_name: rabbitmq-1
    hostname: rabbitmq-1
    ports:
      - "5672:5672"    # AMQP
      - "15672:15672"  # Management UI
      - "25672:25672"  # Inter-Node
      - "4369:4369"    # EPMD
    environment:
      # ===== Cluster Configuration =====
      # WICHTIG: Erlang Cookie muss auf allen Hosts identisch sein!
      RABBITMQ_ERLANG_COOKIE: 'xYz123AbC456DeF789GhI012JkL345Mn=='
      
      # Node Name (muss eindeutig sein)
      RABBITMQ_NODENAME: 'rabbit@rabbitmq-1'
      
      # ===== Default User =====
      RABBITMQ_DEFAULT_USER: 'admin'
      RABBITMQ_DEFAULT_PASS: 'your-secure-password-here'
      
      # ===== VM Configuration =====
      RABBITMQ_VM_MEMORY_HIGH_WATERMARK: '0.6'  # 60% RAM
      RABBITMQ_DISK_FREE_LIMIT: '2GB'
      
      # ===== Logging =====
      RABBITMQ_LOGS: '-'
      RABBITMQ_LOG_LEVEL: 'info'
    
    volumes:
      - rabbitmq-1-data:/var/lib/rabbitmq
      - ./rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf:ro
      - ./enabled_plugins:/etc/rabbitmq/enabled_plugins:ro
    
    networks:
      - rabbitmq-network
    
    restart: unless-stopped
    
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

volumes:
  rabbitmq-1-data:
    driver: local

networks:
  rabbitmq-network:
    driver: bridge
```

**Datei**: `rabbitmq.conf`

```ini
# ===== Cluster Configuration =====
cluster_formation.peer_discovery_backend = classic_config
cluster_formation.classic_config.nodes.1 = rabbit@rabbitmq-1
cluster_formation.classic_config.nodes.2 = rabbit@rabbitmq-2
cluster_formation.classic_config.nodes.3 = rabbit@rabbitmq-3

# ===== Network Configuration =====
listeners.tcp.default = 5672
management.tcp.port = 15672

# ===== Quorum Queue Configuration =====
quorum_queue.default_replication_factor = 3

# ===== Memory Configuration =====
vm_memory_high_watermark.relative = 0.6
vm_memory_high_watermark_paging_ratio = 0.75

# ===== Disk Configuration =====
disk_free_limit.absolute = 2GB

# ===== Performance Tuning =====
channel_max = 2048
heartbeat = 60
frame_max = 131072

# ===== Management Plugin =====
management.load_definitions = /etc/rabbitmq/definitions.json
```

**Datei**: `enabled_plugins`

```
[rabbitmq_management,rabbitmq_prometheus,rabbitmq_shovel,rabbitmq_shovel_management].
```

**Datei**: `definitions.json` (optional, für Queues/Exchanges)

```json
{
  "rabbit_version": "4.1.0",
  "rabbitmq_version": "4.1.0",
  "users": [
    {
      "name": "admin",
      "password_hash": "...",
      "hashing_algorithm": "rabbit_password_hashing_sha256",
      "tags": ["administrator"]
    }
  ],
  "vhosts": [
    {"name": "/"}
  ],
  "permissions": [
    {
      "user": "admin",
      "vhost": "/",
      "configure": ".*",
      "write": ".*",
      "read": ".*"
    }
  ],
  "policies": [
    {
      "vhost": "/",
      "name": "ha-all",
      "pattern": ".*",
      "apply-to": "queues",
      "definition": {
        "ha-mode": "all",
        "ha-sync-mode": "automatic"
      },
      "priority": 0
    }
  ]
}
```

#### Host 2 (192.168.2.10)

**Datei**: `docker-compose.rabbitmq.yml`

```yaml
version: '3.8'

services:
  rabbitmq-2:
    image: rabbitmq:4.1-management
    container_name: rabbitmq-2
    hostname: rabbitmq-2
    ports:
      - "5672:5672"
      - "15672:15672"
      - "25672:25672"
      - "4369:4369"
    environment:
      RABBITMQ_ERLANG_COOKIE: 'xYz123AbC456DeF789GhI012JkL345Mn=='  # IDENTISCH!
      RABBITMQ_NODENAME: 'rabbit@rabbitmq-2'  # Unterschiedlich!
      RABBITMQ_DEFAULT_USER: 'admin'
      RABBITMQ_DEFAULT_PASS: 'your-secure-password-here'
      RABBITMQ_VM_MEMORY_HIGH_WATERMARK: '0.6'
      RABBITMQ_DISK_FREE_LIMIT: '2GB'
      RABBITMQ_LOGS: '-'
      RABBITMQ_LOG_LEVEL: 'info'
    
    volumes:
      - rabbitmq-2-data:/var/lib/rabbitmq
      - ./rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf:ro
      - ./enabled_plugins:/etc/rabbitmq/enabled_plugins:ro
    
    networks:
      - rabbitmq-network
    
    restart: unless-stopped
    
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

volumes:
  rabbitmq-2-data:
    driver: local

networks:
  rabbitmq-network:
    driver: bridge
```

#### Host 3 (192.168.3.10)

**Analog zu Host 2, mit `rabbitmq-3` und `rabbit@rabbitmq-3`**

### Schritt 3: Hosts-Datei konfigurieren

**Auf allen Hosts** `/etc/hosts` bearbeiten:

```bash
# /etc/hosts
192.168.1.10  rabbitmq-1
192.168.2.10  rabbitmq-2
192.168.3.10  rabbitmq-3
```

### Schritt 4: Cluster starten

```bash
# Host 1 (Master)
ssh user@192.168.1.10
cd /opt/rabbitmq
docker compose -f docker-compose.rabbitmq.yml up -d

# Warten bis Node 1 ready ist
docker logs rabbitmq-1 | grep "Server startup complete"

# Host 2
ssh user@192.168.2.10
cd /opt/rabbitmq
docker compose -f docker-compose.rabbitmq.yml up -d

# Host 3
ssh user@192.168.3.10
cd /opt/rabbitmq
docker compose -f docker-compose.rabbitmq.yml up -d
```

### Schritt 5: Cluster bilden

```bash
# Auf Host 2: Node 2 zu Cluster hinzufügen
docker exec rabbitmq-2 rabbitmqctl stop_app
docker exec rabbitmq-2 rabbitmqctl reset
docker exec rabbitmq-2 rabbitmqctl join_cluster rabbit@rabbitmq-1
docker exec rabbitmq-2 rabbitmqctl start_app

# Auf Host 3: Node 3 zu Cluster hinzufügen
docker exec rabbitmq-3 rabbitmqctl stop_app
docker exec rabbitmq-3 rabbitmqctl reset
docker exec rabbitmq-3 rabbitmqctl join_cluster rabbit@rabbitmq-1
docker exec rabbitmq-3 rabbitmqctl start_app
```

### Schritt 6: Cluster-Status prüfen

```bash
# Auf Host 1
docker exec rabbitmq-1 rabbitmqctl cluster_status

# Erwartete Ausgabe:
# Cluster status of node rabbit@rabbitmq-1 ...
# Basics
# Cluster name: rabbit@rabbitmq-1
# Disk Nodes
# rabbit@rabbitmq-1
# rabbit@rabbitmq-2
# rabbit@rabbitmq-3
# Running Nodes
# rabbit@rabbitmq-1
# rabbit@rabbitmq-2
# rabbit@rabbitmq-3
```

### Schritt 7: Queues und Policies erstellen

```bash
# Quorum Queue erstellen
docker exec rabbitmq-1 rabbitmqadmin declare queue \
  name=asteroid.compute \
  durable=true \
  arguments='{"x-queue-type":"quorum","x-max-priority":10}'

# HA Policy setzen (für Classic Queues)
docker exec rabbitmq-1 rabbitmqctl set_policy ha-all \
  ".*" '{"ha-mode":"all","ha-sync-mode":"automatic"}' \
  --priority 0 --apply-to queues
```

## Management UI

Zugriff auf Management UI:
- Host 1: `http://192.168.1.10:15672`
- Host 2: `http://192.168.2.10:15672`
- Host 3: `http://192.168.3.10:15672`

**Login**: admin / your-secure-password-here

## HAProxy Load Balancer (optional)

Für Client-Verbindungen kann HAProxy als Load Balancer verwendet werden:

**Datei**: `docker-compose.haproxy.yml`

```yaml
version: '3.8'

services:
  haproxy:
    image: haproxy:2.9
    container_name: haproxy
    ports:
      - "5672:5672"
      - "15672:15672"
      - "8404:8404"  # Stats
    volumes:
      - ./haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro
    restart: unless-stopped
```

**Datei**: `haproxy.cfg`

```
global
    log stdout format raw local0
    maxconn 4096

defaults
    log global
    mode tcp
    option tcplog
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms

# AMQP Load Balancing
listen rabbitmq_amqp
    bind *:5672
    mode tcp
    balance roundrobin
    server rabbitmq-1 192.168.1.10:5672 check inter 5s
    server rabbitmq-2 192.168.2.10:5672 check inter 5s
    server rabbitmq-3 192.168.3.10:5672 check inter 5s

# Management UI Load Balancing
listen rabbitmq_management
    bind *:15672
    mode http
    balance roundrobin
    server rabbitmq-1 192.168.1.10:15672 check inter 5s
    server rabbitmq-2 192.168.2.10:15672 check inter 5s
    server rabbitmq-3 192.168.3.10:15672 check inter 5s

# Stats
listen stats
    bind *:8404
    stats enable
    stats uri /
    stats refresh 5s
```

## Troubleshooting

### Problem: Nodes verbinden sich nicht

```bash
# 1. Erlang Cookie prüfen
docker exec rabbitmq-1 cat /var/lib/rabbitmq/.erlang.cookie
docker exec rabbitmq-2 cat /var/lib/rabbitmq/.erlang.cookie

# 2. Netzwerk-Konnektivität testen
docker exec rabbitmq-1 ping rabbitmq-2
docker exec rabbitmq-1 nc -zv rabbitmq-2 25672

# 3. Firewall prüfen
telnet 192.168.2.10 25672

# 4. Logs prüfen
docker logs rabbitmq-1 | grep -i error
```

### Problem: Quorum Queue nicht repliziert

```bash
# Queue-Details anzeigen
docker exec rabbitmq-1 rabbitmqctl list_queues name type members

# Policy prüfen
docker exec rabbitmq-1 rabbitmqctl list_policies
```

### Problem: Hohe Memory-Nutzung

```bash
# Memory-Status
docker exec rabbitmq-1 rabbitmqctl status | grep memory

# Top Memory-Consumer
docker exec rabbitmq-1 rabbitmqctl list_queues name memory messages

# Memory Alarm löschen (falls gesetzt)
docker exec rabbitmq-1 rabbitmqctl set_vm_memory_high_watermark 0.7
```

## Performance-Tuning

### OS-Level

```bash
# File Descriptors
echo "* soft nofile 65536" >> /etc/security/limits.conf
echo "* hard nofile 65536" >> /etc/security/limits.conf

# TCP Tuning
sysctl -w net.ipv4.tcp_fin_timeout=30
sysctl -w net.ipv4.tcp_tw_reuse=1
sysctl -w net.core.somaxconn=4096
```

### RabbitMQ-Level

```ini
# In rabbitmq.conf
channel_max = 2048
heartbeat = 60
frame_max = 131072
vm_memory_high_watermark.relative = 0.7
```

## Monitoring

### Prometheus Integration

```bash
# Metriken abrufen
curl http://192.168.1.10:15692/metrics
```

### Wichtige Metriken

- `rabbitmq_queue_messages`: Anzahl Messages in Queue
- `rabbitmq_queue_messages_ready`: Messages bereit zum Konsum
- `rabbitmq_queue_consumers`: Anzahl Consumers
- `rabbitmq_connections`: Anzahl Verbindungen
- `rabbitmq_channels`: Anzahl Channels

## Backup & Recovery

```bash
# Definitions exportieren
docker exec rabbitmq-1 rabbitmqadmin export definitions.json

# Definitions importieren
docker exec rabbitmq-1 rabbitmqadmin import definitions.json

# Daten-Backup
docker compose stop rabbitmq-1
tar -czf rabbitmq-1-backup-$(date +%Y%m%d).tar.gz /var/lib/docker/volumes/rabbitmq-1-data
docker compose start rabbitmq-1
```

## Zusammenfassung

### Checkliste

- [ ] Erlang Cookie generiert und auf allen Hosts identisch
- [ ] Firewall-Regeln konfiguriert (Ports 5672, 15672, 25672, 4369)
- [ ] `/etc/hosts` auf allen Hosts konfiguriert
- [ ] docker-compose.yml auf allen Hosts erstellt
- [ ] Alle Nodes gestartet
- [ ] Cluster gebildet (join_cluster)
- [ ] Cluster-Status geprüft (alle Nodes running)
- [ ] Queues und Policies erstellt
- [ ] Management UI erreichbar
- [ ] HAProxy konfiguriert (optional)

### Wichtigste Parameter

| Parameter | Bedeutung | Wichtigkeit |
|-----------|-----------|-------------|
| RABBITMQ_ERLANG_COOKIE | Cluster-Authentifizierung | ⭐⭐⭐⭐⭐ |
| RABBITMQ_NODENAME | Eindeutiger Node-Name | ⭐⭐⭐⭐⭐ |
| cluster_formation.classic_config.nodes | Liste aller Cluster-Nodes | ⭐⭐⭐⭐⭐ |
| quorum_queue.default_replication_factor | Anzahl Replicas | ⭐⭐⭐⭐ |
| vm_memory_high_watermark | Memory-Limit | ⭐⭐⭐⭐ |
