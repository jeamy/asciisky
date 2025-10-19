# ASCII Sky - Kafka 4.1 Multi-Host Setup Guide

## Übersicht

Dieser Guide beschreibt das Setup von Apache Kafka 4.1 mit KRaft Mode auf 2-3 separaten Hosts in getrennten Netzwerken mit Docker.

## Kafka 4.1 Neuerungen

### Was ist neu in Kafka 4.1?

1. **Zookeeper vollständig entfernt**: KRaft ist der einzige unterstützte Modus
2. **Verbesserte KRaft Performance**: Schnellere Metadata-Operationen
3. **Vereinfachte Konfiguration**: Weniger Parameter, klarere Defaults
4. **Native Docker Images**: `apache/kafka:4.1.0` und `apache/kafka-native:4.1.0`
5. **Bessere Multi-Datacenter Unterstützung**: Optimiert für WAN-Latenz

### Vorteile von KRaft

- ✅ **Einfachere Architektur**: Keine separate Zookeeper-Infrastruktur
- ✅ **Schnellere Metadata-Updates**: Direkter Zugriff ohne Zookeeper-Overhead
- ✅ **Bessere Skalierung**: Bis zu 1 Million Partitionen pro Cluster
- ✅ **Schnelleres Recovery**: Controller-Failover in Millisekunden statt Sekunden
- ✅ **Weniger Ressourcen**: Keine Zookeeper-JVMs mehr nötig

## Architektur-Übersicht

### 2-Host Setup (Minimum)

```
┌─────────────────────────────────────────────────────────────┐
│                    Netzwerk 1 (192.168.1.0/24)              │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Host 1 (192.168.1.10)                               │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │  Docker Container: kafka-1                     │  │   │
│  │  │  - Node ID: 1                                  │  │   │
│  │  │  - Role: broker,controller                     │  │   │
│  │  │  - Port 9092: Client-Zugriff                   │  │   │
│  │  │  - Port 9093: Controller (KRaft)               │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Inter-Broker Communication
                              │ (Port 9092, 9093)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Netzwerk 2 (192.168.2.0/24)              │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Host 2 (192.168.2.10)                               │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │  Docker Container: kafka-2                     │  │   │
│  │  │  - Node ID: 2                                  │  │   │
│  │  │  - Role: broker,controller                     │  │   │
│  │  │  - Port 9092: Client-Zugriff                   │  │   │
│  │  │  - Port 9093: Controller (KRaft)               │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 3-Host Setup (Empfohlen)

Fügt einen dritten Host hinzu für bessere Fehlertoleranz:
- **Quorum**: 2 von 3 Nodes müssen verfügbar sein
- **Replication Factor**: 3 (alle Daten auf allen Nodes)
- **Failover**: Cluster bleibt verfügbar bei Ausfall eines Nodes

## Voraussetzungen

### Netzwerk-Anforderungen

#### Firewall-Regeln

Zwischen allen Kafka-Hosts müssen folgende Ports offen sein:

```bash
# Port 9092: Client-Kommunikation (Producer/Consumer)
# Port 9093: Controller-Kommunikation (KRaft Quorum)

# Beispiel: iptables auf jedem Host
# Host 1 erlaubt Zugriff von Host 2 und 3
iptables -A INPUT -p tcp --dport 9092 -s 192.168.2.10 -j ACCEPT  # Host 2
iptables -A INPUT -p tcp --dport 9093 -s 192.168.2.10 -j ACCEPT
iptables -A INPUT -p tcp --dport 9092 -s 192.168.3.10 -j ACCEPT  # Host 3
iptables -A INPUT -p tcp --dport 9093 -s 192.168.3.10 -j ACCEPT

# Oder mit ufw (Ubuntu)
ufw allow from 192.168.2.10 to any port 9092 proto tcp
ufw allow from 192.168.2.10 to any port 9093 proto tcp
ufw allow from 192.168.3.10 to any port 9092 proto tcp
ufw allow from 192.168.3.10 to any port 9093 proto tcp
```

#### DNS oder /etc/hosts (optional)

Für einfachere Konfiguration können Hostnamen verwendet werden:

```bash
# /etc/hosts auf allen Hosts
192.168.1.10  kafka-host-1
192.168.2.10  kafka-host-2
192.168.3.10  kafka-host-3
```

### Hardware-Anforderungen

**Minimum (pro Host)**
- CPU: 4 Cores
- RAM: 8 GB
- Disk: 500 GB SSD
- Network: 1 Gbit/s

**Empfohlen (pro Host)**
- CPU: 8 Cores
- RAM: 16 GB
- Disk: 1 TB NVMe SSD
- Network: 10 Gbit/s

### Software-Anforderungen

- Docker 24.x oder höher
- Docker Compose 2.x oder höher
- Linux Kernel 5.x oder höher

## Installation

### Schritt 1: CLUSTER_ID generieren

**Wichtig**: Die CLUSTER_ID muss auf allen Hosts identisch sein!

```bash
# Auf einem beliebigen Host (nur einmal ausführen)
CLUSTER_ID=$(docker run --rm apache/kafka:4.1.0 kafka-storage.sh random-uuid)
echo "CLUSTER_ID: $CLUSTER_ID"

# Beispiel-Ausgabe:
# CLUSTER_ID: MkU3OEVBNTcwNTJENDM2Qk
```

**Diese ID in allen docker-compose Dateien verwenden!**

### Schritt 2: Docker Compose Dateien erstellen

#### Host 1 (192.168.1.10)

**Datei**: `docker-compose.kafka.yml`

```yaml
version: '3.8'

services:
  kafka-1:
    image: apache/kafka:4.1.0
    container_name: kafka-1
    hostname: kafka-1
    ports:
      - "9092:9092"  # Client-Zugriff
      - "9093:9093"  # Controller (KRaft)
    environment:
      # ===== Node Identity =====
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: 'broker,controller'
      
      # ===== KRaft Cluster Configuration =====
      # WICHTIG: CLUSTER_ID muss auf allen Hosts identisch sein!
      CLUSTER_ID: 'MkU3OEVBNTcwNTJENDM2Qk'  # Hier deine generierte ID einsetzen
      
      # WICHTIG: Alle Controller-Nodes auflisten (IP:Port)
      # 2-Host Setup:
      KAFKA_CONTROLLER_QUORUM_VOTERS: '1@192.168.1.10:9093,2@192.168.2.10:9093'
      # 3-Host Setup (auskommentieren und obige Zeile löschen):
      # KAFKA_CONTROLLER_QUORUM_VOTERS: '1@192.168.1.10:9093,2@192.168.2.10:9093,3@192.168.3.10:9093'
      
      # ===== Listeners (KRITISCH für Multi-Host!) =====
      # BROKER: Für Client-Kommunikation (Producer/Consumer)
      # CONTROLLER: Für KRaft Quorum-Kommunikation
      KAFKA_LISTENERS: 'BROKER://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093'
      
      # WICHTIG: Externe IP verwenden, nicht localhost oder Container-Name!
      KAFKA_ADVERTISED_LISTENERS: 'BROKER://192.168.1.10:9092'
      
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: 'BROKER:PLAINTEXT,CONTROLLER:PLAINTEXT'
      KAFKA_INTER_BROKER_LISTENER_NAME: 'BROKER'
      KAFKA_CONTROLLER_LISTENER_NAMES: 'CONTROLLER'
      
      # ===== Storage =====
      KAFKA_LOG_DIRS: '/var/lib/kafka/data'
      
      # ===== Performance Tuning =====
      KAFKA_NUM_NETWORK_THREADS: 8
      KAFKA_NUM_IO_THREADS: 8
      KAFKA_SOCKET_SEND_BUFFER_BYTES: 102400
      KAFKA_SOCKET_RECEIVE_BUFFER_BYTES: 102400
      KAFKA_SOCKET_REQUEST_MAX_BYTES: 104857600
      
      # ===== Replication (2-Host Setup) =====
      KAFKA_DEFAULT_REPLICATION_FACTOR: 2
      KAFKA_MIN_INSYNC_REPLICAS: 1
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 2
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 2
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      
      # 3-Host Setup (auskommentieren für bessere Fehlertoleranz):
      # KAFKA_DEFAULT_REPLICATION_FACTOR: 3
      # KAFKA_MIN_INSYNC_REPLICAS: 2
      # KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 3
      # KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 3
      # KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 2
      
      # ===== Retention =====
      KAFKA_LOG_RETENTION_HOURS: 168  # 7 Tage
      KAFKA_LOG_SEGMENT_BYTES: 1073741824  # 1 GB
      KAFKA_LOG_RETENTION_CHECK_INTERVAL_MS: 300000  # 5 Minuten
      
      # ===== Compression =====
      KAFKA_COMPRESSION_TYPE: 'lz4'
      
      # ===== JVM Settings (optional) =====
      KAFKA_HEAP_OPTS: '-Xms4G -Xmx4G'
    
    volumes:
      - kafka-1-data:/var/lib/kafka/data
    
    networks:
      - kafka-network
    
    restart: unless-stopped
    
    # Health Check
    healthcheck:
      test: ["CMD", "kafka-broker-api-versions.sh", "--bootstrap-server", "localhost:9092"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

volumes:
  kafka-1-data:
    driver: local

networks:
  kafka-network:
    driver: bridge
```

#### Host 2 (192.168.2.10)

**Datei**: `docker-compose.kafka.yml`

```yaml
version: '3.8'

services:
  kafka-2:
    image: apache/kafka:4.1.0
    container_name: kafka-2
    hostname: kafka-2
    ports:
      - "9092:9092"
      - "9093:9093"
    environment:
      KAFKA_NODE_ID: 2  # Unterschiedlich!
      KAFKA_PROCESS_ROLES: 'broker,controller'
      CLUSTER_ID: 'MkU3OEVBNTcwNTJENDM2Qk'  # IDENTISCH zu Host 1!
      
      # 2-Host Setup:
      KAFKA_CONTROLLER_QUORUM_VOTERS: '1@192.168.1.10:9093,2@192.168.2.10:9093'
      # 3-Host Setup:
      # KAFKA_CONTROLLER_QUORUM_VOTERS: '1@192.168.1.10:9093,2@192.168.2.10:9093,3@192.168.3.10:9093'
      
      KAFKA_LISTENERS: 'BROKER://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093'
      KAFKA_ADVERTISED_LISTENERS: 'BROKER://192.168.2.10:9092'  # Eigene IP!
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: 'BROKER:PLAINTEXT,CONTROLLER:PLAINTEXT'
      KAFKA_INTER_BROKER_LISTENER_NAME: 'BROKER'
      KAFKA_CONTROLLER_LISTENER_NAMES: 'CONTROLLER'
      KAFKA_LOG_DIRS: '/var/lib/kafka/data'
      
      # Gleiche Settings wie Host 1
      KAFKA_NUM_NETWORK_THREADS: 8
      KAFKA_NUM_IO_THREADS: 8
      KAFKA_DEFAULT_REPLICATION_FACTOR: 2
      KAFKA_MIN_INSYNC_REPLICAS: 1
      KAFKA_LOG_RETENTION_HOURS: 168
      KAFKA_COMPRESSION_TYPE: 'lz4'
      KAFKA_HEAP_OPTS: '-Xms4G -Xmx4G'
    
    volumes:
      - kafka-2-data:/var/lib/kafka/data
    
    networks:
      - kafka-network
    
    restart: unless-stopped
    
    healthcheck:
      test: ["CMD", "kafka-broker-api-versions.sh", "--bootstrap-server", "localhost:9092"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

volumes:
  kafka-2-data:
    driver: local

networks:
  kafka-network:
    driver: bridge
```

#### Host 3 (192.168.3.10) - Optional

**Datei**: `docker-compose.kafka.yml`

```yaml
version: '3.8'

services:
  kafka-3:
    image: apache/kafka:4.1.0
    container_name: kafka-3
    hostname: kafka-3
    ports:
      - "9092:9092"
      - "9093:9093"
    environment:
      KAFKA_NODE_ID: 3  # Unterschiedlich!
      KAFKA_PROCESS_ROLES: 'broker,controller'
      CLUSTER_ID: 'MkU3OEVBNTcwNTJENDM2Qk'  # IDENTISCH!
      
      # 3-Host Setup:
      KAFKA_CONTROLLER_QUORUM_VOTERS: '1@192.168.1.10:9093,2@192.168.2.10:9093,3@192.168.3.10:9093'
      
      KAFKA_LISTENERS: 'BROKER://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093'
      KAFKA_ADVERTISED_LISTENERS: 'BROKER://192.168.3.10:9092'  # Eigene IP!
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: 'BROKER:PLAINTEXT,CONTROLLER:PLAINTEXT'
      KAFKA_INTER_BROKER_LISTENER_NAME: 'BROKER'
      KAFKA_CONTROLLER_LISTENER_NAMES: 'CONTROLLER'
      KAFKA_LOG_DIRS: '/var/lib/kafka/data'
      
      # 3-Host Settings
      KAFKA_NUM_NETWORK_THREADS: 8
      KAFKA_NUM_IO_THREADS: 8
      KAFKA_DEFAULT_REPLICATION_FACTOR: 3  # Alle 3 Nodes
      KAFKA_MIN_INSYNC_REPLICAS: 2
      KAFKA_LOG_RETENTION_HOURS: 168
      KAFKA_COMPRESSION_TYPE: 'lz4'
      KAFKA_HEAP_OPTS: '-Xms4G -Xmx4G'
    
    volumes:
      - kafka-3-data:/var/lib/kafka/data
    
    networks:
      - kafka-network
    
    restart: unless-stopped
    
    healthcheck:
      test: ["CMD", "kafka-broker-api-versions.sh", "--bootstrap-server", "localhost:9092"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

volumes:
  kafka-3-data:
    driver: local

networks:
  kafka-network:
    driver: bridge
```

### Schritt 3: Cluster starten

```bash
# Host 1
ssh user@192.168.1.10
cd /opt/kafka
docker compose -f docker-compose.kafka.yml up -d

# Host 2
ssh user@192.168.2.10
cd /opt/kafka
docker compose -f docker-compose.kafka.yml up -d

# Host 3 (optional)
ssh user@192.168.3.10
cd /opt/kafka
docker compose -f docker-compose.kafka.yml up -d
```

**Wichtig**: Alle Nodes sollten innerhalb von 1-2 Minuten gestartet werden, damit das KRaft Quorum sich bilden kann.

### Schritt 4: Cluster-Status prüfen

```bash
# Auf Host 1
docker exec kafka-1 kafka-broker-api-versions.sh --bootstrap-server localhost:9092

# Metadata anzeigen
docker exec kafka-1 kafka-metadata.sh --snapshot /var/lib/kafka/data/__cluster_metadata-0/00000000000000000000.log --print-contents

# Cluster-Beschreibung
docker exec kafka-1 kafka-metadata.sh --snapshot /var/lib/kafka/data/__cluster_metadata-0/00000000000000000000.log --print-contents | grep -i "broker\|controller"
```

**Erwartete Ausgabe**: Alle Broker sollten als "ALIVE" angezeigt werden.

### Schritt 5: Topics erstellen

```bash
# Auf Host 1
docker exec kafka-1 kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic test-topic \
  --partitions 12 \
  --replication-factor 2

# Topic-Liste anzeigen
docker exec kafka-1 kafka-topics.sh --list \
  --bootstrap-server localhost:9092

# Topic-Details anzeigen
docker exec kafka-1 kafka-topics.sh --describe \
  --bootstrap-server localhost:9092 \
  --topic test-topic
```

## Kafka UI (Kafdrop)

Für einfaches Monitoring kann Kafdrop auf einem beliebigen Host deployed werden:

```yaml
version: '3.8'

services:
  kafdrop:
    image: obsidiandynamics/kafdrop:latest
    container_name: kafdrop
    ports:
      - "9000:9000"
    environment:
      KAFKA_BROKERCONNECT: '192.168.1.10:9092,192.168.2.10:9092,192.168.3.10:9092'
      JVM_OPTS: '-Xms32M -Xmx64M'
      SERVER_SERVLET_CONTEXTPATH: '/'
    restart: unless-stopped
```

Zugriff: `http://<host-ip>:9000`

## Troubleshooting

### Problem: Broker verbinden sich nicht

**Symptom**: Logs zeigen "Connection refused" oder "Timeout"

**Lösung**:
```bash
# 1. Firewall prüfen
telnet 192.168.2.10 9092
telnet 192.168.2.10 9093

# 2. CLUSTER_ID prüfen (muss identisch sein!)
docker exec kafka-1 grep CLUSTER_ID /var/lib/kafka/data/meta.properties
docker exec kafka-2 grep CLUSTER_ID /var/lib/kafka/data/meta.properties

# 3. Logs prüfen
docker logs kafka-1 | grep -i error
docker logs kafka-2 | grep -i error
```

### Problem: Controller-Election schlägt fehl

**Symptom**: "No controller elected" in Logs

**Lösung**:
```bash
# 1. KAFKA_CONTROLLER_QUORUM_VOTERS prüfen
docker exec kafka-1 env | grep QUORUM

# 2. Alle Nodes müssen erreichbar sein
# 3. Cluster neu starten (alle Nodes gleichzeitig)
docker compose down
docker compose up -d
```

### Problem: Hohe Latenz zwischen Hosts

**Symptom**: Langsame Producer/Consumer

**Lösung**:
```bash
# 1. Netzwerk-Latenz messen
ping 192.168.2.10
mtr 192.168.2.10

# 2. Compression aktivieren (bereits in Config)
# 3. Batch-Size erhöhen (Producer-Seite)
# 4. Fetch-Size erhöhen (Consumer-Seite)
```

### Problem: Disk Space voll

**Symptom**: "No space left on device"

**Lösung**:
```bash
# 1. Retention reduzieren
docker exec kafka-1 kafka-configs.sh --alter \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name test-topic \
  --add-config retention.ms=86400000  # 1 Tag

# 2. Log Compaction aktivieren
docker exec kafka-1 kafka-configs.sh --alter \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name test-topic \
  --add-config cleanup.policy=compact

# 3. Alte Logs manuell löschen
docker exec kafka-1 rm -rf /var/lib/kafka/data/test-topic-*
```

## Performance-Tuning

### OS-Level (auf jedem Host)

```bash
# 1. File Descriptors erhöhen
echo "* soft nofile 100000" >> /etc/security/limits.conf
echo "* hard nofile 100000" >> /etc/security/limits.conf

# 2. TCP Tuning
sysctl -w net.core.rmem_max=134217728
sysctl -w net.core.wmem_max=134217728
sysctl -w net.ipv4.tcp_rmem="4096 87380 134217728"
sysctl -w net.ipv4.tcp_wmem="4096 65536 134217728"

# 3. Disk I/O Scheduler (für SSD)
echo "noop" > /sys/block/sda/queue/scheduler
```

### Kafka-Level

```yaml
# In docker-compose.yml hinzufügen:
environment:
  # Mehr Threads für hohen Durchsatz
  KAFKA_NUM_NETWORK_THREADS: 16
  KAFKA_NUM_IO_THREADS: 16
  
  # Größere Buffers
  KAFKA_SOCKET_SEND_BUFFER_BYTES: 1048576
  KAFKA_SOCKET_RECEIVE_BUFFER_BYTES: 1048576
  
  # Batch-Processing
  KAFKA_REPLICA_FETCH_MAX_BYTES: 10485760
  KAFKA_MESSAGE_MAX_BYTES: 10485760
```

## Backup & Recovery

### Backup

```bash
# 1. Kafka-Daten sichern (auf jedem Host)
docker compose stop kafka-1
tar -czf kafka-1-backup-$(date +%Y%m%d).tar.gz /var/lib/docker/volumes/kafka-1-data
docker compose start kafka-1

# 2. Topic-Konfigurationen exportieren
docker exec kafka-1 kafka-configs.sh --describe \
  --bootstrap-server localhost:9092 \
  --entity-type topics > topics-config-backup.txt
```

### Recovery

```bash
# 1. Daten wiederherstellen
docker compose stop kafka-1
rm -rf /var/lib/docker/volumes/kafka-1-data/*
tar -xzf kafka-1-backup-20250117.tar.gz -C /
docker compose start kafka-1

# 2. Topics neu erstellen (falls nötig)
# Siehe Schritt 5: Topics erstellen
```

## Monitoring

### Wichtige Metriken

```bash
# 1. Broker-Status
docker exec kafka-1 kafka-broker-api-versions.sh --bootstrap-server localhost:9092

# 2. Under-Replicated Partitions (sollte 0 sein)
docker exec kafka-1 kafka-topics.sh --describe \
  --bootstrap-server localhost:9092 \
  --under-replicated-partitions

# 3. Consumer Lag
docker exec kafka-1 kafka-consumer-groups.sh --describe \
  --bootstrap-server localhost:9092 \
  --group <consumer-group-name>

# 4. Disk Usage
docker exec kafka-1 du -sh /var/lib/kafka/data/*
```

### Prometheus Integration

```yaml
# JMX Exporter hinzufügen
services:
  kafka-1:
    environment:
      KAFKA_JMX_PORT: 9999
      KAFKA_JMX_HOSTNAME: 192.168.1.10
    ports:
      - "9999:9999"
```

## Sicherheit

### SSL/TLS aktivieren

```yaml
# Zertifikate generieren (auf jedem Host)
# ... (siehe Kafka SSL Documentation)

# In docker-compose.yml:
environment:
  KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: 'BROKER:SSL,CONTROLLER:PLAINTEXT'
  KAFKA_SSL_KEYSTORE_FILENAME: 'kafka.keystore.jks'
  KAFKA_SSL_KEYSTORE_CREDENTIALS: 'keystore_creds'
  KAFKA_SSL_KEY_CREDENTIALS: 'key_creds'
  KAFKA_SSL_TRUSTSTORE_FILENAME: 'kafka.truststore.jks'
  KAFKA_SSL_TRUSTSTORE_CREDENTIALS: 'truststore_creds'
```

### SASL Authentication

```yaml
environment:
  KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: 'BROKER:SASL_PLAINTEXT,CONTROLLER:PLAINTEXT'
  KAFKA_SASL_MECHANISM_INTER_BROKER_PROTOCOL: 'PLAIN'
  KAFKA_SASL_ENABLED_MECHANISMS: 'PLAIN'
```

## Zusammenfassung

### Checkliste für Deployment

- [ ] CLUSTER_ID generiert und dokumentiert
- [ ] Firewall-Regeln konfiguriert (Ports 9092, 9093)
- [ ] docker-compose.yml auf allen Hosts erstellt
- [ ] IP-Adressen in KAFKA_ADVERTISED_LISTENERS angepasst
- [ ] KAFKA_CONTROLLER_QUORUM_VOTERS auf allen Hosts identisch
- [ ] Alle Nodes gleichzeitig gestartet
- [ ] Cluster-Status geprüft (alle Broker ALIVE)
- [ ] Test-Topic erstellt und getestet
- [ ] Monitoring aufgesetzt (Kafdrop oder Prometheus)
- [ ] Backup-Strategie definiert

### Wichtigste Konfigurationsparameter

| Parameter | Bedeutung | Wichtigkeit |
|-----------|-----------|-------------|
| CLUSTER_ID | Eindeutige Cluster-ID (muss identisch sein!) | ⭐⭐⭐⭐⭐ |
| KAFKA_CONTROLLER_QUORUM_VOTERS | Liste aller Controller-Nodes | ⭐⭐⭐⭐⭐ |
| KAFKA_ADVERTISED_LISTENERS | Externe IP für Client-Zugriff | ⭐⭐⭐⭐⭐ |
| KAFKA_NODE_ID | Eindeutige Node-ID (1, 2, 3, ...) | ⭐⭐⭐⭐⭐ |
| KAFKA_DEFAULT_REPLICATION_FACTOR | Anzahl Replicas (2 oder 3) | ⭐⭐⭐⭐ |
| KAFKA_MIN_INSYNC_REPLICAS | Minimum Replicas für Writes | ⭐⭐⭐⭐ |
| KAFKA_LOG_RETENTION_HOURS | Wie lange Daten behalten werden | ⭐⭐⭐ |

### Nächste Schritte

1. Producer-Services implementieren (siehe `003-migrationsplan.md`)
2. Consumer-Services implementieren
3. Monitoring erweitern (Prometheus + Grafana)
4. SSL/TLS aktivieren (Produktion)
5. Backup-Automatisierung einrichten
