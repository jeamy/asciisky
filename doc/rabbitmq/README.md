# ASCII Sky - RabbitMQ 4.1 Migration Dokumentation

## Übersicht

Diese Dokumentation beschreibt die Migration von ASCII Sky zu einer RabbitMQ 4.1-basierten Message-Queue-Architektur als **Alternative zu Kafka**.

## Warum RabbitMQ statt Kafka?

### RabbitMQ ist besser für ASCII Sky geeignet

✅ **Niedrigere Latenz**: < 10ms vs. 50-100ms (Kafka)  
✅ **Einfachere Architektur**: Weniger Komplexität  
✅ **Priority Queues**: Native Unterstützung für Task-Priorisierung  
✅ **RPC-Pattern**: Perfekt für Request/Reply (Web Service ↔ Worker)  
✅ **Geringere Ressourcen**: ~50% weniger RAM/CPU als Kafka  
✅ **Management UI**: Eingebautes Web-Interface  
✅ **Task-Queue-Pattern**: Ideal für Berechnungs-Tasks  

### Kafka wäre besser für

❌ Event-Sourcing (Replay von Events)  
❌ Analytics (Auswertung von Nutzungsmustern)  
❌ Stream Processing (Echtzeit-Aggregationen)  
❌ Sehr hoher Durchsatz (> 1M msg/s)  

**Für ASCII Sky**: RabbitMQ ist die pragmatischere Wahl.

## Dokumente

### 1. [Architektur-Analyse](001-architektur-analyse.md)
**Inhalt**: Analyse der aktuellen Architektur + Vergleich Kafka vs. RabbitMQ
- Aktuelle Komponenten und Datenfluss
- Skalierungsprobleme
- Warum RabbitMQ besser passt als Kafka
- Vergleichstabelle

**Zielgruppe**: Architekten, Entscheider  
**Lesedauer**: 10 Minuten

### 2. [RabbitMQ 4.1 Zielarchitektur](002-rabbitmq-zielarchitektur.md)
**Inhalt**: Design der RabbitMQ-basierten Architektur
- Architektur-Diagramm
- RabbitMQ 4.1 Cluster-Konfiguration
- Exchanges, Queues und Routing
- Worker-Services (Asteroid, Comet, Celestial, Constellation)
- Web Service Integration
- Scheduler Service
- Datenfluss-Szenarien
- Vorteile und Herausforderungen
- Vergleichstabelle: RabbitMQ vs. Kafka

**Zielgruppe**: Architekten, Entwickler, DevOps  
**Lesedauer**: 25 Minuten

### 3. [RabbitMQ 4.1 Multi-Host Setup](003-rabbitmq-4.1-multi-host-setup.md) ⭐
**Inhalt**: Praktischer Setup-Guide für RabbitMQ 4.1 Cluster
- RabbitMQ 4.1 Neuerungen
- 3-Host Cluster Setup in getrennten Netzwerken
- Voraussetzungen (Firewall, Hardware)
- Schritt-für-Schritt Installation:
  - Erlang Cookie generieren
  - Docker Compose Dateien für jeden Host
  - Cluster bilden und verifizieren
  - Queues und Policies erstellen
- HAProxy Load Balancer Setup
- Troubleshooting
- Performance-Tuning
- Monitoring & Backup

**Zielgruppe**: DevOps, System-Administratoren  
**Lesedauer**: 35 Minuten

### 4. [Migrationsplan](004-migrationsplan.md)
**Inhalt**: Schrittweiser Plan für die RabbitMQ-Migration
- Migrationsstrategie
- 6 Phasen (10-14 Wochen):
  - Phase 0: Vorbereitung (2 Wochen)
  - Phase 1: RabbitMQ-Infrastruktur (1-2 Wochen)
  - Phase 2: Erste Worker (Asteroids) (2-3 Wochen)
  - Phase 3: Weitere Worker (2-3 Wochen)
  - Phase 4: Web Service Integration (2 Wochen)
  - Phase 5: Scheduler & Optimierung (1-2 Wochen)
- Code-Beispiele (Python + pika)
- Docker-Integration
- Rollback-Plan

**Zielgruppe**: Projektmanager, Entwickler  
**Lesedauer**: 30 Minuten

### 5. [Technologie-Vergleich](005-technologie-vergleich.md)
**Inhalt**: Bewertung verschiedener Technologien
- Python Client Libraries (pika vs. aio-pika)
- Serialisierung (JSON vs. MessagePack)
- Queue-Typen (Classic vs. Quorum vs. Streams)
- Deployment-Optionen
- Performance-Metriken
- Entwicklungsaufwand

**Zielgruppe**: Architekten, Entwickler  
**Lesedauer**: 20 Minuten

### 6. [Voraussetzungen](006-voraussetzungen.md)
**Inhalt**: Alle erforderlichen Voraussetzungen
- Hardware-Anforderungen (niedriger als Kafka!)
- Software-Anforderungen
- Netzwerk-Anforderungen
- Team-Struktur
- Budget (günstiger als Kafka)
- Zeitplan (schneller als Kafka)

**Zielgruppe**: Projektmanager, Entscheider  
**Lesedauer**: 20 Minuten

### 7. [Multi-Host Storage](007-multi-host-storage.md) ⭐ WICHTIG
**Inhalt**: Shared Storage für Multi-Host Deployments
- **Problem**: Worker auf verschiedenen Hosts schreiben in lokale DBs
- **Lösung 1**: NFS/GlusterFS für Shared Storage (einfach)
- **Lösung 2**: PostgreSQL/MySQL statt SQLite (beste Performance)
- **Lösung 3**: Hybrid (PostgreSQL + NFS) - empfohlen
- **Setup-Guides**: NFS Server/Client, PostgreSQL, Docker Compose
- **Troubleshooting**: SQLite Locks, NFS Performance
- **Empfehlungen**: Dev vs. Produktion

**Zielgruppe**: DevOps, Architekten  
**Lesedauer**: 20 Minuten

## Schnellvergleich: RabbitMQ vs. Kafka

| Kriterium | RabbitMQ 4.1 | Kafka 4.1 | Gewinner |
|-----------|--------------|-----------|----------|
| **Latenz** | < 10ms | 50-100ms | ⭐ RabbitMQ |
| **Durchsatz** | 100k msg/s | 1M msg/s | Kafka |
| **Komplexität** | Mittel | Hoch | ⭐ RabbitMQ |
| **Ressourcen** | 4 GB RAM | 8 GB RAM | ⭐ RabbitMQ |
| **Priority Queues** | Native | Workaround | ⭐ RabbitMQ |
| **RPC-Pattern** | Native | Komplex | ⭐ RabbitMQ |
| **Replay** | Nein | Ja | Kafka |
| **Management UI** | Eingebaut | Extern (Kafdrop) | ⭐ RabbitMQ |
| **Setup-Zeit** | 10-14 Wochen | 12-18 Wochen | ⭐ RabbitMQ |
| **Kosten** | $30-50/Monat | $50-100/Monat | ⭐ RabbitMQ |
| **Use Case Fit** | Perfekt | Gut | ⭐ RabbitMQ |

**Ergebnis**: RabbitMQ gewinnt 9:2 für ASCII Sky Use Case

## Schnellstart

### Für Entscheider

1. Lesen Sie [Architektur-Analyse](001-architektur-analyse.md) (Abschnitt "Vergleich")
2. Lesen Sie [RabbitMQ-Zielarchitektur](002-rabbitmq-zielarchitektur.md) (Abschnitt "Vorteile")
3. Vergleichen Sie mit Kafka-Dokumentation (`/doc/kafka/`)
4. Entscheidung: RabbitMQ vs. Kafka vs. Status Quo

**Lesedauer**: 15 Minuten

### Für DevOps

1. Lesen Sie [RabbitMQ 4.1 Multi-Host Setup](003-rabbitmq-4.1-multi-host-setup.md)
2. Testen Sie Setup lokal (Docker Compose)
3. Planen Sie Produktion-Deployment

**Lesedauer**: 40 Minuten

### Für Entwickler

1. Lesen Sie [RabbitMQ-Zielarchitektur](002-rabbitmq-zielarchitektur.md)
2. Lesen Sie [Migrationsplan](004-migrationsplan.md) (Code-Beispiele)
3. Lesen Sie [Technologie-Vergleich](005-technologie-vergleich.md)
4. Setup lokale Entwicklungsumgebung

**Lesedauer**: 75 Minuten

## Wichtigste Erkenntnisse

### RabbitMQ 4.1 Vorteile

**Performance**
- ✅ Quorum Queues 2x schneller als 3.x
- ✅ Niedrige Latenz (< 10ms)
- ✅ Geringere Ressourcen als Kafka

**Features**
- ✅ Priority Queues (0-10)
- ✅ RPC-Pattern (Request/Reply)
- ✅ Dead Letter Queues
- ✅ Message TTL
- ✅ Management UI eingebaut

**Betrieb**
- ✅ Einfacheres Setup als Kafka
- ✅ Weniger Komponenten
- ✅ Bessere Observability
- ✅ Schnellere Fehlerdiagnose

### Empfohlener Ansatz

**Phase 1: Minimal (10-14 Wochen)**
- Python für Worker (Skyfield beibehalten)
- Python für Web Service (FastAPI)
- pika Client Library
- JSON Serialisierung
- **RabbitMQ 4.1 auf 2-3 Hosts** (Docker)
- **Kosten**: ~$30-50/Monat (eigene Hardware) oder ~$150-200/Monat (VPS)
- **Performance**: Sehr gut (<1000 Nutzer)

**Phase 2: Optimal (+ 4 Wochen)**
- Python Worker (unverändert)
- aio-pika (Async) für bessere Performance
- MessagePack Serialisierung
- Redis Cache Integration
- **Kosten**: ~$300-500/Monat
- **Performance**: Exzellent (>5.000 Nutzer)

**Phase 3: Enterprise (+ 2 Wochen)**
- Kubernetes Deployment
- RabbitMQ Cluster Operator
- Auto-Scaling
- **Kosten**: ~$500-1000/Monat
- **Performance**: Maximal (>20.000 Nutzer)

## Entscheidungshilfe

### ✅ JA zu RabbitMQ, wenn:

- Task-Queue-Pattern benötigt
- Niedrige Latenz wichtig (< 50ms)
- Priority Queues erforderlich
- RPC/Request-Reply Pattern
- Einfachheit wichtiger als Features
- Budget begrenzt (<$500/Monat)
- Team < 5 Entwickler
- Schnelle Migration gewünscht (< 4 Monate)

### ✅ JA zu Kafka, wenn:

- Event-Sourcing erforderlich
- Replay-Fähigkeit wichtig
- Analytics/Stream Processing
- Sehr hoher Durchsatz (> 500k msg/s)
- Event-Log als Single Source of Truth
- Budget vorhanden (>$1000/Monat)
- Team > 5 Entwickler mit Kafka-Expertise

### ❌ NEIN zu Message-Broker, wenn:

- Weniger als 100 Nutzer
- Aktuelle Architektur ausreichend
- Keine Zeit für Migration (< 2 Monate)
- Team zu klein (< 2 Entwickler)

## Nächste Schritte

### 1. Entscheidung treffen

- [ ] RabbitMQ-Dokumentation gelesen
- [ ] Kafka-Dokumentation gelesen (zum Vergleich)
- [ ] Vergleichstabelle analysiert
- [ ] Team-Meeting durchgeführt
- [ ] Entscheidung: RabbitMQ vs. Kafka vs. Status Quo

### 2. Proof of Concept (RabbitMQ)

- [ ] RabbitMQ 4.1 Cluster lokal aufsetzen
- [ ] Einfachen Worker implementieren (Asteroid)
- [ ] Web Service Integration testen
- [ ] Performance messen
- [ ] Mit Kafka PoC vergleichen (optional)

### 3. Migration starten

- [ ] Team zusammenstellen
- [ ] Migrationsplan anpassen
- [ ] Phase 1 starten
- [ ] Regelmäßige Reviews

## Externe Ressourcen

### RabbitMQ-Dokumentation
- [RabbitMQ 4.1 Docs](https://www.rabbitmq.com/docs)
- [RabbitMQ Tutorials](https://www.rabbitmq.com/tutorials)
- [RabbitMQ Best Practices](https://www.rabbitmq.com/best-practices)

### Python Client Libraries
- [pika Documentation](https://pika.readthedocs.io/)
- [aio-pika Documentation](https://aio-pika.readthedocs.io/)

### Tools
- [RabbitMQ Management UI](https://www.rabbitmq.com/docs/management) - Eingebaut
- [rabbitmqadmin v2](https://www.rabbitmq.com/docs/management-cli) - CLI Tool
- [HAProxy](http://www.haproxy.org/) - Load Balancer

### Community
- [RabbitMQ Mailing List](https://groups.google.com/g/rabbitmq-users)
- [RabbitMQ Discord](https://www.rabbitmq.com/discord/)
- [Stack Overflow](https://stackoverflow.com/questions/tagged/rabbitmq)

## Kostenvergleich

### RabbitMQ (eigene Hardware, 3 Hosts)
- **Hardware**: 3x (4 Cores, 8 GB RAM, 200 GB SSD) = ~$30/Monat (Strom)
- **Gesamt**: ~$30-50/Monat

### RabbitMQ (VPS, 3 Hosts)
- **VPS**: 3x $50/Monat = $150/Monat
- **Gesamt**: ~$150-200/Monat

### RabbitMQ (Managed, CloudAMQP)
- **Cluster**: ~$300-500/Monat (Professional Plan)
- **Gesamt**: ~$300-500/Monat

### Kafka (eigene Hardware, 3 Hosts)
- **Hardware**: 3x (8 Cores, 16 GB RAM, 1 TB SSD) = ~$50/Monat
- **Gesamt**: ~$50-100/Monat

### Kafka (Managed, AWS MSK)
- **Cluster**: ~$500-1000/Monat
- **Gesamt**: ~$500-1000/Monat

**RabbitMQ ist 40-60% günstiger als Kafka!**

## Version History

- **v1.0** (2025-01-17): Initiale RabbitMQ-Dokumentation
  - Architektur-Analyse mit Kafka-Vergleich
  - RabbitMQ 4.1 Zielarchitektur
  - Multi-Host Setup Guide
  - Migrationsplan (kompakt)
  - Technologie-Vergleich
  - Voraussetzungen

## Lizenz

Diese Dokumentation ist Teil des ASCII Sky Projekts und unterliegt der MIT-Lizenz.
