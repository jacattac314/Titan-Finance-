import asyncio
import redis.asyncio as redis
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("TitanExplanationVerifier")

async def verify_explanations():
    r = redis.from_url("redis://localhost:6379")
    pubsub = r.pubsub()
    await pubsub.subscribe("execution_filled")
    
    logger.info("Listening for 'execution_filled' events to verify explanations...")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            explanation = data.get("explanation")
            
            if explanation and len(explanation) > 0:
                logger.info(f"✅ EXPLANATION DETECTED for {data['symbol']} ({data['model_id']})")
                logger.info(f"   Category: {explanation}")
                # We can exit after finding one valid explanation
                # But let's keep listening for a few more to see variety
            else:
                logger.warning(f"⚠️ No explanation found for {data['symbol']} ({data['model_id']})")

if __name__ == "__main__":
    try:
        asyncio.run(verify_explanations())
    except KeyboardInterrupt:
        pass
