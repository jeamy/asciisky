#!/bin/bash
# Setup RabbitMQ Queues für ASCII Sky
# Verwendung: ./scripts/setup-rabbitmq-queues.sh

set -e

CONTAINER_NAME="${RABBITMQ_CONTAINER:-asciisky-rabbitmq}"
RABBITMQ_USER="${RABBITMQ_USER:-admin}"
RABBITMQ_PASS="${RABBITMQ_PASSWORD:-changeme}"

echo "🐰 Setting up RabbitMQ queues in container: $CONTAINER_NAME"

# Warten bis RabbitMQ bereit ist
echo "⏳ Waiting for RabbitMQ to be ready..."
until docker exec $CONTAINER_NAME rabbitmqctl status > /dev/null 2>&1; do
    echo "   Waiting..."
    sleep 2
done
echo "✅ RabbitMQ is ready!"

# Exchange erstellen
echo "📦 Creating exchange: computation.direct"
docker exec $CONTAINER_NAME rabbitmqadmin -u $RABBITMQ_USER -p $RABBITMQ_PASS declare exchange \
  name=computation.direct \
  type=direct \
  durable=true

# Asteroid Queue
echo "🌑 Creating queue: asteroid.compute"
docker exec $CONTAINER_NAME rabbitmqadmin -u $RABBITMQ_USER -p $RABBITMQ_PASS declare queue \
  name=asteroid.compute \
  durable=true \
  arguments='{"x-queue-type":"quorum","x-message-ttl":3600000}'

docker exec $CONTAINER_NAME rabbitmqadmin -u $RABBITMQ_USER -p $RABBITMQ_PASS declare binding \
  source=computation.direct \
  destination=asteroid.compute \
  routing_key=compute.asteroid

# Comet Queue
echo "☄️  Creating queue: comet.compute"
docker exec $CONTAINER_NAME rabbitmqadmin -u $RABBITMQ_USER -p $RABBITMQ_PASS declare queue \
  name=comet.compute \
  durable=true \
  arguments='{"x-queue-type":"quorum","x-message-ttl":3600000}'

docker exec $CONTAINER_NAME rabbitmqadmin -u $RABBITMQ_USER -p $RABBITMQ_PASS declare binding \
  source=computation.direct \
  destination=comet.compute \
  routing_key=compute.comet


# Precompute Queue (Priority Queue für Coordinator/Worker)
echo "🔄 Creating queue: precompute.tasks"
docker exec $CONTAINER_NAME rabbitmqadmin -u $RABBITMQ_USER -p $RABBITMQ_PASS declare queue \
  name=precompute.tasks \
  durable=true \
  arguments='{"x-max-priority":10,"x-queue-type":"quorum"}'

# Results & Status Queues (durable für RabbitMQ 4.1 Kompatibilität)
echo "📊 Creating results and status queues"
docker exec $CONTAINER_NAME rabbitmqadmin -u $RABBITMQ_USER -p $RABBITMQ_PASS declare queue \
  name=computation.results \
  durable=true

docker exec $CONTAINER_NAME rabbitmqadmin -u $RABBITMQ_USER -p $RABBITMQ_PASS declare queue \
  name=computation.status \
  durable=true

echo ""
echo "✅ All queues created successfully!"
echo ""
echo "🔍 Queue overview:"
docker exec $CONTAINER_NAME rabbitmqctl list_queues name messages consumers

echo ""
echo "🌐 RabbitMQ Management UI: http://localhost:15672"
echo "   Username: $RABBITMQ_USER"
echo "   Password: [from .env]"
echo ""
echo "📋 Created queues:"
echo "   - asteroid.compute (Quorum, TTL 1h)"
echo "   - comet.compute (Quorum, TTL 1h)"
echo "   - precompute.tasks (Quorum, Priority 0-10)"
echo "   - computation.results"
echo "   - computation.status"
