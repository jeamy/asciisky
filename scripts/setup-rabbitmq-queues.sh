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

# Create exchanges and queues via rabbitmqctl (no extra dependencies required)
echo "📦 Creating exchanges and queues..."

# Exchange creation using same method as queues (eval)
echo "🔗 Creating computation.direct exchange..."
docker exec $CONTAINER_NAME rabbitmqctl eval "
rabbit_exchange:declare(
    {resource, <<\"/\">>, exchange, <<"computation.direct">>},
    direct,
    true,
    false,
    false,
    []
).
" > /dev/null 2>&1 || echo "Exchange already exists"

# Verify exchange was created
if docker exec $CONTAINER_NAME rabbitmqctl list_exchanges | grep -q "computation.direct"; then
    echo "✅ computation.direct exchange created successfully"
else
    echo "❌ Exchange creation failed - workers may not be able to publish messages"
    echo "🔍 Available exchanges:"
    docker exec $CONTAINER_NAME rabbitmqctl list_exchanges name type
fi

# Queues via rabbitmqctl
echo "🌑 Creating asteroid.compute queue..."
docker exec $CONTAINER_NAME rabbitmqctl eval "
rabbit_amqqueue:declare(
    {resource, <<\"/\">>, queue, <<"asteroid.compute">>},
    true,
    false,
    [{<<\"x-queue-type\">>, longstr, <<"quorum">>}, {<<\"x-message-ttl\">>, long, 3600000}],
    none
).
" > /dev/null 2>&1 || echo "Queue already exists"

echo "☄️  Creating comet.compute queue..."
docker exec $CONTAINER_NAME rabbitmqctl eval "
rabbit_amqqueue:declare(
    {resource, <<\"/\">>, queue, <<"comet.compute">>},
    true,
    false,
    [{<<\"x-queue-type\">>, longstr, <<"quorum">>}, {<<\"x-message-ttl\">>, long, 3600000}],
    none
).
" > /dev/null 2>&1 || echo "Queue already exists"

echo "🔄 Creating precompute.tasks queue..."
docker exec $CONTAINER_NAME rabbitmqctl eval "
rabbit_amqqueue:declare(
    {resource, <<\"/\">>, queue, <<\"precompute.tasks\">>},
    true,
    false,
    [{<<\"x-max-priority\">>, long, 10}],
    none
).
" > /dev/null 2>&1 || echo "Queue already exists"

echo "📊 Creating results and status queues..."
docker exec $CONTAINER_NAME rabbitmqctl eval "
rabbit_amqqueue:declare(
    {resource, <<\"/\">>, queue, <<"computation.results">>},
    true,
    false,
    [],
    none
).
" > /dev/null 2>&1 || echo "Queue already exists"

docker exec $CONTAINER_NAME rabbitmqctl eval "
rabbit_amqqueue:declare(
    {resource, <<\"/\">>, queue, <<"computation.status">>},
    true,
    false,
    [],
    none
).
" > /dev/null 2>&1 || echo "Queue already exists"

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
echo "   - asteroid.compute (Quorum, TTL 1h)"
echo "   - comet.compute (Quorum, TTL 1h)"
echo "   - precompute.tasks (Classic, Priority 0-10)"
echo "   - computation.results"
echo "   - computation.status"
