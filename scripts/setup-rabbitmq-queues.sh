#!/bin/bash
# Setup RabbitMQ Queues für ASCII Sky
# Verwendung: ./scripts/setup-rabbitmq-queues.sh

set -e

CONTAINER_NAME="${RABBITMQ_CONTAINER:-asciisky-rabbitmq}"

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
docker exec $CONTAINER_NAME rabbitmqadmin -u admin -p password declare exchange \
  name=computation.direct \
  type=direct \
  durable=true

# Asteroid Queue
echo "🌑 Creating queue: asteroid.compute"
docker exec $CONTAINER_NAME rabbitmqadmin -u admin -p password declare queue \
  name=asteroid.compute \
  durable=true \
  arguments='{"x-queue-type":"quorum","x-message-ttl":3600000}'

docker exec $CONTAINER_NAME rabbitmqadmin -u admin -p password declare binding \
  source=computation.direct \
  destination=asteroid.compute \
  routing_key=compute.asteroid

# Comet Queue
echo "☄️  Creating queue: comet.compute"
docker exec $CONTAINER_NAME rabbitmqadmin -u admin -p password declare queue \
  name=comet.compute \
  durable=true \
  arguments='{"x-queue-type":"quorum","x-message-ttl":3600000}'

docker exec $CONTAINER_NAME rabbitmqadmin -u admin -p password declare binding \
  source=computation.direct \
  destination=comet.compute \
  routing_key=compute.comet


# Results & Status Queues (durable für RabbitMQ 4.1 Kompatibilität)
echo "📊 Creating results and status queues"
docker exec $CONTAINER_NAME rabbitmqadmin -u admin -p password declare queue \
  name=computation.results \
  durable=true

docker exec $CONTAINER_NAME rabbitmqadmin -u admin -p password declare queue \
  name=computation.status \
  durable=true

echo ""
echo "✅ All queues created successfully!"
echo ""
echo "🔍 Queue overview:"
docker exec $CONTAINER_NAME rabbitmqctl list_queues name messages consumers

echo ""
echo "🌐 RabbitMQ Management UI: http://localhost:15672"
echo "   Username: admin"
echo "   Password: password"
