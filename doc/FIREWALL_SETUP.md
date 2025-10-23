# UFW Firewall Setup for ASCII Sky

## 🔥 Overview

Firewall configuration for the multi-host production deployment.

### Port overview

| Server | Port | Service | Access | Description |
|--------|------|---------|---------|--------------|
| **$RABBITMQ_MAIN** | 22 | SSH | Already configured | Server administration |
| | 80/443 | Web UI (nginx) | Public | ASCII Sky web interface |
| | 8000 | FastAPI | Internal (nginx) | Backend (not public) |
| | 5672 | RabbitMQ AMQP | ONLY Worker-B/C IPs | Message queue |
| | 5432 | PostgreSQL | ONLY Worker-B/C IPs | Database |
| | 15672 | RabbitMQ UI | ONLY localhost | Management interface (SSH tunnel) |
| **$RABBITMQ_B** | 22 | SSH | Already configured | Server administration |
| **$RABBITMQ_C** | 22 | SSH | Already configured | Server administration |

---

## 🚀 Quick start

### Automatic setup (recommended)

**Run ONLY on $RABBITMQ_MAIN:**

```bash
chmod +x scripts/setup-firewall.sh
sudo ./scripts/setup-firewall.sh
```

The script:
- ✅ Automatically discovers IPs via DNS
- ✅ Restricts port 5672 (RabbitMQ) to Worker-B/C IPs
- ✅ Restricts port 5432 (PostgreSQL) to Worker-B/C IPs
- ✅ Restricts port 15672 (RabbitMQ UI) to localhost
- ✅ Worker servers require NO firewall changes

**Important:** Ports 80/443 (nginx) and SSH are assumed to be already configured!

---

## 🔧 Manual configuration

### On $RABBITMQ_MAIN (main server)

**Recommendation:** Use the automatic script (see above)!

**Manual configuration:**

```bash
# Discover IPs
WORKER_B_IP=$(dig +short $RABBITMQ_B | tail -n1)
WORKER_C_IP=$(dig +short $RABBITMQ_C | tail -n1)

echo "Worker-B IP: $WORKER_B_IP"
echo "Worker-C IP: $WORKER_C_IP"

# RabbitMQ AMQP (ONLY from worker servers)
sudo ufw allow from $WORKER_B_IP to any port 5672 proto tcp comment 'RabbitMQ from Worker-B'
sudo ufw allow from $WORKER_C_IP to any port 5672 proto tcp comment 'RabbitMQ from Worker-C'

# PostgreSQL (ONLY from worker servers)
sudo ufw allow from $WORKER_B_IP to any port 5432 proto tcp comment 'PostgreSQL from Worker-B'
sudo ufw allow from $WORKER_C_IP to any port 5432 proto tcp comment 'PostgreSQL from Worker-C'

# RabbitMQ Management UI (ONLY localhost)
sudo ufw allow from 127.0.0.1 to any port 15672 proto tcp comment 'RabbitMQ UI localhost'

# Reload UFW
sudo ufw reload

# Check status
sudo ufw status verbose
```

**Note:** Ports 80/443 (nginx), SSH, and other ports are assumed to be already configured.

### On $RABBITMQ_B and $RABBITMQ_C (worker servers)

**No firewall changes required!**

Worker servers:
- ✅ Outbound connections are already allowed (`default allow outgoing`)
- ✅ Connect to $RABBITMQ_MAIN:5672 (RabbitMQ)
- ✅ Connect to $RABBITMQ_MAIN:5432 (PostgreSQL)
- ✅ Do not require inbound ports (except SSH)

**If UFW is not yet configured:**
```bash
# Only if UFW is not yet active
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw enable
```

---

## 🔐 Security recommendations

### 1. Restrict RabbitMQ and PostgreSQL to worker IPs

**Status:** ✅ Automatically configured by `setup-firewall.sh`!

**Manual verification:**
```bash
# On $RABBITMQ_MAIN
sudo ufw status numbered | grep -E '5672|5432'

# Should show:
# [X] 5672/tcp ALLOW IN <Worker-B-IP>
# [Y] 5672/tcp ALLOW IN <Worker-C-IP>
# [Z] 5432/tcp ALLOW IN <Worker-B-IP>
# [W] 5432/tcp ALLOW IN <Worker-C-IP>
```

**If you need to configure manually:**
```bash
# IPs automatisch ermitteln
WORKER_B_IP=$(dig +short $RABBITMQ_B | tail -n1)
WORKER_C_IP=$(dig +short $RABBITMQ_C | tail -n1)

# Regeln hinzufügen
sudo ufw allow from $WORKER_B_IP to any port 5672 proto tcp comment 'RabbitMQ from Worker-B'
sudo ufw allow from $WORKER_C_IP to any port 5672 proto tcp comment 'RabbitMQ from Worker-C'
sudo ufw allow from $WORKER_B_IP to any port 5432 proto tcp comment 'PostgreSQL from Worker-B'
sudo ufw allow from $WORKER_C_IP to any port 5432 proto tcp comment 'PostgreSQL from Worker-C'
```

### 2. Secure RabbitMQ Management UI

**Status:** ✅ Automatically restricted to localhost by `setup-firewall.sh`!

**Access via SSH tunnel (recommended):**
```bash
# From your local machine
ssh -L 15672:localhost:15672 $RABBITMQ_MAIN

# Then open in the browser:
http://localhost:15672

User: admin
Password: <RABBITMQ_PASSWORD from .env>
```

**Check:**
```bash
# Auf $RABBITMQ_MAIN
sudo ufw status | grep 15672

# Should show:
# 15672/tcp ALLOW IN 127.0.0.1
```

### 3. Secure SSH (optional)

**Note:** SSH is assumed to be already configured!

**Optional improvements:**
```bash
# Enable rate limiting
sudo ufw limit 22/tcp comment 'SSH with rate limiting'

# Only from trusted IPs (if desired)
sudo ufw delete allow 22/tcp
sudo ufw allow from <admin-IP> to any port 22 proto tcp comment 'SSH from Admin'
```

### 4. Port 8000 (FastAPI) not public

**Status:** ✅ Port 8000 should NOT be publicly reachable!

**Prüfung:**
```bash
# Auf $RABBITMQ_MAIN
sudo ufw status | grep 8000

# Should show NOTHING or only localhost
```

**Why?**
- Web UI runs via nginx (ports 80/443)
- nginx forwards internally to port 8000
- Port 8000 does not need to be public

---

## 📊 Monitoring

### Check UFW status

```bash
# Verbose status
sudo ufw status verbose

# Numbered rules
sudo ufw status numbered

# Enable logging
sudo ufw logging on

# Show logs
sudo tail -f /var/log/ufw.log
```

### Check open ports

```bash
# All open ports
sudo netstat -tulpn | grep LISTEN

# Or with ss
sudo ss -tulpn | grep LISTEN

# Only Docker containers
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

---

## 🛠️ Troubleshooting

### Issue: No access to Web UI

```bash
# Check nginx
sudo systemctl status nginx

# Check nginx configuration
sudo nginx -t

# Check if ports 80/443 are open
sudo ufw status | grep -E '80|443'

# Check if web container is running
docker ps | grep asciisky-web

# Check if port 8000 is reachable internally
curl http://localhost:8000/api/celestial?lat=48.2&lon=16.3
```

### Issue: Workers cannot connect

```bash
# On $RABBITMQ_MAIN: Check ports 5672 and 5432
sudo ufw status | grep -E '5672|5432'

# Test connection from worker server
# On $RABBITMQ_B:
telnet $RABBITMQ_MAIN 5672
telnet $RABBITMQ_MAIN 5432

# Check RabbitMQ logs
docker logs asciisky-rabbitmq | tail -50

# Check PostgreSQL logs
docker logs asciisky-postgres | tail -50
```

### Issue: UFW blocks Docker containers

Docker manipulates iptables directly and can bypass UFW rules.

**Solution:** Configure UFW for Docker:

```bash
# Edit /etc/ufw/after.rules
sudo nano /etc/ufw/after.rules

# Add at the end:
# BEGIN UFW AND DOCKER
*filter
:ufw-user-forward - [0:0]
:DOCKER-USER - [0:0]
-A DOCKER-USER -j RETURN -s 10.0.0.0/8
-A DOCKER-USER -j RETURN -s 172.16.0.0/12
-A DOCKER-USER -j RETURN -s 192.168.0.0/16
-A DOCKER-USER -j ufw-user-forward
-A DOCKER-USER -j DROP -p tcp -m tcp --tcp-flags FIN,SYN,RST,ACK SYN -d 192.168.0.0/16
-A DOCKER-USER -j DROP -p tcp -m tcp --tcp-flags FIN,SYN,RST,ACK SYN -d 10.0.0.0/8
-A DOCKER-USER -j DROP -p tcp -m tcp --tcp-flags FIN,SYN,RST,ACK SYN -d 172.16.0.0/12
-A DOCKER-USER -j DROP -p udp -m udp --dport 0:32767 -d 192.168.0.0/16
-A DOCKER-USER -j DROP -p udp -m udp --dport 0:32767 -d 10.0.0.0/8
-A DOCKER-USER -j DROP -p udp -m udp --dport 0:32767 -d 172.16.0.0/12
-A DOCKER-USER -j RETURN
COMMIT
# END UFW AND DOCKER

# UFW neu laden
sudo ufw reload
```

---

## 🔄 UFW commands cheat sheet

```bash
# Status
sudo ufw status                    # Simple status
sudo ufw status verbose            # Verbose status
sudo ufw status numbered           # With rule numbers

# Enable/Disable
sudo ufw enable                    # Enable UFW
sudo ufw disable                   # Disable UFW
sudo ufw reload                    # Reload UFW

# Add rules
sudo ufw allow 8000/tcp            # Allow port
sudo ufw allow from 1.2.3.4        # Allow IP
sudo ufw allow from 1.2.3.4 to any port 5432  # IP to port
sudo ufw limit 22/tcp              # Rate limiting

# Delete rules
sudo ufw delete allow 8000/tcp     # By rule
sudo ufw delete 5                  # By number
sudo ufw status numbered           # Show numbers

# Reset
sudo ufw reset                    # Delete all rules

# Logging
sudo ufw logging on                # Enable logging
sudo ufw logging off               # Disable logging
sudo tail -f /var/log/ufw.log      # Show logs

# Default Policies
sudo ufw default deny incoming     # Deny incoming
sudo ufw default allow outgoing    # Allow outgoing
```

---

## 📋 Production checklist

**Main server ($RABBITMQ_MAIN):**
- [ ] `setup-firewall.sh` executed
- [ ] Ports 80/443 (nginx) publicly reachable
- [ ] Port 8000 (FastAPI) NOT public
- [ ] RabbitMQ (port 5672) ONLY reachable from Worker-B/C IPs
- [ ] PostgreSQL (port 5432) ONLY reachable from Worker-B/C IPs
- [ ] RabbitMQ UI (port 15672) ONLY via SSH tunnel
- [ ] UFW status checked: `sudo ufw status verbose`

**Worker servers ($RABBITMQ_B and $RABBITMQ_C):**
- [ ] No firewall changes needed (outgoing connections allowed)
- [ ] Connection to RabbitMQ tested: `telnet $RABBITMQ_MAIN 5672`
- [ ] Connection to PostgreSQL tested: `telnet $RABBITMQ_MAIN 5432`

**Tests:**
- [ ] Web UI reachable externally: `http://$RABBITMQ_MAIN`
- [ ] RabbitMQ UI via SSH tunnel: `ssh -L 15672:localhost:15672 $RABBITMQ_MAIN`
- [ ] Workers can process tasks (check RabbitMQ UI)
- [ ] PostgreSQL reachable from workers

---

## 🔗 Further reading

- [UFW documentation](https://help.ubuntu.com/community/UFW)
- [Docker and UFW](https://github.com/chaifeng/ufw-docker)
- [iptables basics](https://www.netfilter.org/documentation/)
