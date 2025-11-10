#!/bin/bash
# Diagnose RabbitMQ setup issues
# Usage: ./scripts/diagnose-rabbitmq.sh

CONTAINER_NAME="${RABBITMQ_CONTAINER:-asciisky-rabbitmq}"
RABBITMQ_USER="${RABBITMQ_USER:-admin}"
RABBITMQ_PASS="${RABBITMQ_PASSWORD:-changeme}"

echo "🔍 RabbitMQ Diagnostics"
echo "======================="
echo ""

# Check if container is running
echo "1️⃣ Container Status:"
if docker ps | grep -q $CONTAINER_NAME; then
    echo "✅ Container $CONTAINER_NAME is running"
else
    echo "❌ Container $CONTAINER_NAME is NOT running"
    exit 1
fi
echo ""

# Check RabbitMQ status
echo "2️⃣ RabbitMQ Status:"
docker exec $CONTAINER_NAME rabbitmqctl status > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ RabbitMQ is running"
else
    echo "❌ RabbitMQ is NOT running"
    exit 1
fi
echo ""

# Check if rabbitmqadmin is available
echo "3️⃣ rabbitmqadmin availability:"
if docker exec $CONTAINER_NAME which rabbitmqadmin > /dev/null 2>&1; then
    echo "✅ rabbitmqadmin is available"
else
    echo "❌ rabbitmqadmin is NOT available"
    echo "   This is required for queue creation"
fi
echo ""

# List all exchanges
echo "4️⃣ Current Exchanges:"
docker exec $CONTAINER_NAME rabbitmqctl list_exchanges name type durable
echo ""

# List all queues
echo "5️⃣ Current Queues:"
docker exec $CONTAINER_NAME rabbitmqctl list_queues name durable messages consumers
echo ""

# List all bindings
echo "6️⃣ Current Bindings:"
docker exec $CONTAINER_NAME rabbitmqctl list_bindings source_name destination_name routing_key
echo ""

# Check feature flags
echo "7️⃣ Feature Flags:"
docker exec $CONTAINER_NAME rabbitmqctl list_feature_flags | grep -E "deprecated|disabled"
echo ""

# Test rabbitmqadmin command
echo "8️⃣ Testing rabbitmqadmin command:"
echo "   Attempting to list queues with rabbitmqadmin..."
if docker exec $CONTAINER_NAME rabbitmqadmin -u ${RABBITMQ_USER} -p ${RABBITMQ_PASS} list queues 2>&1 | head -5; then
    echo "✅ rabbitmqadmin works"
else
    echo "❌ rabbitmqadmin failed"
fi
echo ""

# Check if computation.direct exchange exists
echo "9️⃣ Checking for computation.direct exchange:"
if docker exec $CONTAINER_NAME rabbitmqctl list_exchanges | grep -q "computation.direct"; then
    echo "✅ computation.direct exchange exists"
else
    echo "❌ computation.direct exchange NOT found"
fi
echo ""

# Check if required queues exist
echo "🔟 Checking for required queues:"
REQUIRED_QUEUES=("asteroid.compute" "comet.compute" "precompute.tasks" "computation.results" "computation.status")
for queue in "${REQUIRED_QUEUES[@]}"; do
    if docker exec $CONTAINER_NAME rabbitmqctl list_queues | grep -q "$queue"; then
        echo "✅ $queue exists"
    else
        echo "❌ $queue NOT found"
    fi
done
echo ""

echo "📋 Diagnosis complete!"
echo ""
echo "💡 If queues are missing, run:"
echo "   ./scripts/setup-rabbitmq-queues.sh"
