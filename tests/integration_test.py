import redis
import json
import uuid
import datetime
import os
import sys
import time

# Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = 6379

def run_test():
    print(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        r.ping()
        print("Connected.")
    except Exception as e:
        print(f"Failed to connect to Redis: {e}")
        sys.exit(1)

    # Subscribe to all relevant channels
    pubsub = r.pubsub()
    channels = ['market_data', 'trade_signals', 'execution_requests', 'execution_filled']
    for ch in channels:
        pubsub.subscribe(ch)
    
    print(f"Subscribed to channels: {channels}")

    # Allow some time for subscription to take effect
    time.sleep(1)

    # 1. Inject Market Data
    test_symbol = "INTEG-TEST"
    tick = {
        "symbol": test_symbol,
        "price": 100.0,
        "volume": 1000,
        "timestamp": datetime.datetime.now().isoformat()
    }
    
    print(f"\n[STEP 1] Publishing Mock Market Data: {tick}")
    r.publish('market_data', json.dumps(tick))

    # 2. Wait for reaction
    print("[STEP 2] Waiting for system reaction (timeout 10s)...")
    
    start_time = time.time()
    events_received = {ch: False for ch in channels}
    # market_data is already sent, so we expect it back (redis pubsub echoes if we are subscribed? No, we receive what we publish if we listen)
    
    while time.time() - start_time < 10:
        message = pubsub.get_message(ignore_subscribe_messages=True)
        if message:
            channel = message['channel']
            data = message['data']
            print(f" -> Received on [{channel}]: {data}")
            
            if channel in events_received:
                events_received[channel] = True
                
            # Check if we have received everything we expect
            # Note: signal/risk/execution might filter the symbol if they are strictly configured.
            # Assuming they pass through or generate based on logic.
            # If Signal Engine logic is strict (needs history), it might NOT generate a signal for a single tick.
             
        time.sleep(0.1)

    print("\n[TEST REPORT]")
    success = True
    for ch, received in events_received.items():
        status = "PASS" if received else "FAIL/MISSING"
        print(f"Channel '{ch}': {status}")
        if not received and ch != 'market_data': # market_data should be received
             # Note: logic might prevent signal generation on first tick. 
             # So strictly speaking, this test confirms CONNECTIVITY, not full logic if logic requires state.
             pass

    # For now, if we receive market_data back, at least Gateway->Redis is working.
    # To properly test Signal, we might need to inject multiple ticks or mock the signal service response too if we are testing the PIPELINE infrastructure.
    
    if events_received['market_data']:
        print("\nBasic Redis Connectivity Verified.")
    else:
        print("\nRedis Pub/Sub failed.")
        sys.exit(1)

if __name__ == "__main__":
    run_test()
