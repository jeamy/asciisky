#!/bin/bash
# Setup RabbitMQ queues for ASCII Sky
# Usage: ./scripts/setup-rabbitmq-queues.sh

set -e

CONTAINER_NAME="${RABBITMQ_CONTAINER:-asciisky-rabbitmq}"
RABBITMQ_USER="${RABBITMQ_USER:-admin}"
RABBITMQ_PASS="${RABBITMQ_PASSWORD:-changeme}"

echo "🐰 Setting up RabbitMQ queues in container: $CONTAINER_NAME"

# Wait until RabbitMQ is ready
echo "⏳ Waiting for RabbitMQ to be ready..."
until docker exec $CONTAINER_NAME rabbitmqctl status > /dev/null 2>&1; do
    echo "   Waiting..."
    sleep 2
done
echo "✅ RabbitMQ is ready!"

# Create exchanges and queues via rabbitmqadmin
echo "📦 Creating exchanges and queues..."
echo ""

# Exchange creation
echo "🔗 Creating computation.direct exchange..."
if docker exec $CONTAINER_NAME rabbitmqadmin -u ${RABBITMQ_USER} -p ${RABBITMQ_PASS} declare exchange name=computation.direct type=direct durable=true 2>&1; then
    echo "✅ computation.direct exchange created"
else
    echo "⚠️ Exchange may already exist"
fi
echo ""

# Queues via rabbitmqadmin
echo "🌑 Creating asteroid.compute queue..."
if docker exec $CONTAINER_NAME rabbitmqadmin -u ${RABBITMQ_USER} -p ${RABBITMQ_PASS} declare queue name=asteroid.compute durable=true 2>&1; then
    echo "✅ asteroid.compute queue created"
else
    echo "⚠️ Queue may already exist"
fi
echo ""

echo "☄️  Creating comet.compute queue..."
if docker exec $CONTAINER_NAME rabbitmqadmin -u ${RABBITMQ_USER} -p ${RABBITMQ_PASS} declare queue name=comet.compute durable=true 2>&1; then
    echo "✅ comet.compute queue created"
else
    echo "⚠️ Queue may already exist"
fi
echo ""

echo "🔄 Creating precompute.tasks queue..."
if docker exec $CONTAINER_NAME rabbitmqadmin -u ${RABBITMQ_USER} -p ${RABBITMQ_PASS} declare queue name=precompute.tasks durable=true arguments='{"x-max-priority":10}' 2>&1; then
    echo "✅ precompute.tasks queue created with priority"
else
    echo "⚠️ Queue may already exist"
fi
echo ""

echo "📊 Creating computation.results queue..."
if docker exec $CONTAINER_NAME rabbitmqadmin -u ${RABBITMQ_USER} -p ${RABBITMQ_PASS} declare queue name=computation.results durable=true 2>&1; then
    echo "✅ computation.results queue created"
else
    echo "⚠️ Queue may already exist"
fi
echo ""

echo "📊 Creating computation.status queue..."
if docker exec $CONTAINER_NAME rabbitmqadmin -u ${RABBITMQ_USER} -p ${RABBITMQ_PASS} declare queue name=computation.status durable=true 2>&1; then
    echo "✅ computation.status queue created"
else
    echo "⚠️ Queue may already exist"
fi
echo ""

echo "🔗 Binding queues to computation.direct exchange..."
if docker exec $CONTAINER_NAME rabbitmqadmin -u ${RABBITMQ_USER} -p ${RABBITMQ_PASS} declare binding source=computation.direct destination=asteroid.compute routing_key=asteroid.compute 2>&1; then
    echo "✅ asteroid.compute bound to exchange"
else
    echo "⚠️ Binding may already exist"
fi

if docker exec $CONTAINER_NAME rabbitmqadmin -u ${RABBITMQ_USER} -p ${RABBITMQ_PASS} declare binding source=computation.direct destination=comet.compute routing_key=comet.compute 2>&1; then
    echo "✅ comet.compute bound to exchange"
else
    echo "⚠️ Binding may already exist"
fi
echo ""

echo ""
echo "✅ All queues created successfully!"
echo ""
echo "🔍 Queue overview:"
docker exec $CONTAINER_NAME rabbitmqctl list_queues name messages consumers

echo ""
echo "🔗 Exchange overview:"
docker exec $CONTAINER_NAME rabbitmqctl list_exchanges name type durable

echo ""
echo "🌐 RabbitMQ Management UI: http://localhost:15672"
echo "   Username: $RABBITMQ_USER"
echo "   Password: [from .env]"
echo ""
echo "📋 Created queues:"
echo "   - asteroid.compute (durable)"
echo "   - comet.compute (durable)"
echo "   - precompute.tasks (durable, Priority 0-10)"
echo "   - computation.results (durable)"
echo "   - computation.status (durable)"
echo ""
echo "⚠️  Deprecated Features Warning:"
echo "   RabbitMQ may show deprecated feature warnings."
echo "   This is normal and doesn't affect functionality."
echo "   To fix: Enable all feature flags in RabbitMQ management UI."
