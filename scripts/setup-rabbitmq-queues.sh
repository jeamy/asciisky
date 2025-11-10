#!/bin/bash
# Setup RabbitMQ queues for ASCII Sky
# Usage: ./scripts/setup-rabbitmq-queues.sh
#
# NOTE: With RabbitMQ 4.x, the old Erlang API (rabbit_exchange:declare, rabbit_amqqueue:declare)
# no longer works. Instead, queues are automatically created by the workers when they start.
# This script just waits for RabbitMQ to be ready.

set -e

CONTAINER_NAME="${RABBITMQ_CONTAINER:-asciisky-rabbitmq}"

echo "🐰 Checking RabbitMQ in container: $CONTAINER_NAME"

# Wait until RabbitMQ is ready
echo "⏳ Waiting for RabbitMQ to be ready..."
until docker exec $CONTAINER_NAME rabbitmqctl status > /dev/null 2>&1; do
    echo "   Waiting..."
    sleep 2
done
echo "✅ RabbitMQ is ready!"

echo ""
echo "📦 Queue Setup Information:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "ℹ️  RabbitMQ 4.x Note:"
echo "   Queues are automatically created by workers when they start."
echo "   The old Erlang API (rabbit_exchange:declare) no longer works."
echo ""
echo "📋 Expected Queues (created by workers):"
echo "   - asteroid.compute (durable)"
echo "   - comet.compute (durable)"
echo "   - precompute.tasks (durable, Priority 0-10)"
echo "   - computation.results (durable)"
echo "   - computation.status (durable)"
echo ""
echo "🔗 Expected Exchange:"
echo "   - computation.direct (direct, durable)"
echo ""
echo "🚀 Next Steps:"
echo "   1. Start the workers: docker compose up -d"
echo "   2. Workers will automatically create all queues"
echo "   3. Check queue status: docker exec $CONTAINER_NAME rabbitmqctl list_queues"
echo ""
echo "🌐 RabbitMQ Management UI: http://localhost:15672"
echo "   Username: admin"
echo "   Password: [from .env]"
echo ""
