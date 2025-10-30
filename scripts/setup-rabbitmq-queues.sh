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

# Create exchanges and queues via rabbitmqctl (direct Erlang commands)
echo "📦 Creating exchanges and queues..."
echo ""

# Exchange creation via rabbitmqctl
echo "🔗 Creating computation.direct exchange..."
docker exec $CONTAINER_NAME rabbitmqctl eval 'rabbit_exchange:declare({resource, <<"/">>, exchange, <<"computation.direct">>}, direct, true, false, false, []).' 2>&1 | grep -v "already_exists" || echo "✅ Exchange created or already exists"
echo ""

# Queues via rabbitmqctl  
echo "🌑 Creating asteroid.compute queue..."
docker exec $CONTAINER_NAME rabbitmqctl eval 'rabbit_amqqueue:declare({resource, <<"/">>, queue, <<"asteroid.compute">>}, true, false, [], none).' 2>&1 | grep -v "already_exists" || echo "✅ Queue created or already exists"
echo ""

echo "☄️  Creating comet.compute queue..."
docker exec $CONTAINER_NAME rabbitmqctl eval 'rabbit_amqqueue:declare({resource, <<"/">>, queue, <<"comet.compute">>}, true, false, [], none).' 2>&1 | grep -v "already_exists" || echo "✅ Queue created or already exists"
echo ""

echo "🔄 Creating precompute.tasks queue..."
docker exec $CONTAINER_NAME rabbitmqctl eval 'rabbit_amqqueue:declare({resource, <<"/">>, queue, <<"precompute.tasks">>}, true, false, [{<<"x-max-priority">>, long, 10}], none).' 2>&1 | grep -v "already_exists" || echo "✅ Queue created or already exists"
echo ""

echo "📊 Creating computation.results queue..."
docker exec $CONTAINER_NAME rabbitmqctl eval 'rabbit_amqqueue:declare({resource, <<"/">>, queue, <<"computation.results">>}, true, false, [], none).' 2>&1 | grep -v "already_exists" || echo "✅ Queue created or already exists"
echo ""

echo "📊 Creating computation.status queue..."
docker exec $CONTAINER_NAME rabbitmqctl eval 'rabbit_amqqueue:declare({resource, <<"/">>, queue, <<"computation.status">>}, true, false, [], none).' 2>&1 | grep -v "already_exists" || echo "✅ Queue created or already exists"
echo ""

echo "🔗 Binding queues to computation.direct exchange..."
docker exec $CONTAINER_NAME rabbitmqctl eval 'rabbit_binding:add({resource, <<"/">>, exchange, <<"computation.direct">>}, <<"asteroid.compute">>, {resource, <<"/">>, queue, <<"asteroid.compute">>}, <<"asteroid.compute">>, []).' 2>&1 | grep -v "already_exists" || echo "✅ asteroid.compute bound"

docker exec $CONTAINER_NAME rabbitmqctl eval 'rabbit_binding:add({resource, <<"/">>, exchange, <<"computation.direct">>}, <<"comet.compute">>, {resource, <<"/">>, queue, <<"comet.compute">>}, <<"comet.compute">>, []).' 2>&1 | grep -v "already_exists" || echo "✅ comet.compute bound"
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
