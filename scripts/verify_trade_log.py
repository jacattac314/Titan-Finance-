import redis
import json
import uuid
import datetime
import os
import sys

# Connect to Redis
redis_host = os.getenv('REDIS_HOST', 'localhost')
try:
    r = redis.from_url(f"redis://{redis_host}:6379")
    r.ping()
    print(f"Connected to Redis at {redis_host}")
except Exception as e:
    print(f"Failed to connect to Redis: {e}")
    sys.exit(1)

# Create a fake execution event
execution_event = {
    "id": str(uuid.uuid4()),
    "symbol": "TEST-SYM",
    "side": "BUY",
    "qty": 100,
    "price": 150.25,
    "timestamp": datetime.datetime.now().isoformat(),
    "status": "FILLED"
}

# Publish to relevant channel
channel = "execution_filled"
r.publish(channel, json.dumps(execution_event))
print(f"Published event to '{channel}':")
print(json.dumps(execution_event, indent=2))
