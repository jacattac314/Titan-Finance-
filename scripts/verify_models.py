import asyncio
import redis.asyncio as redis
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("TitanVerifier")

MODELS_TO_VERIFY = ["lgb_spy_v1", "lstm_spy_v1", "tft_spy_v1"]
VERIFIED_MODELS = set()

async def verify_models():
    r = redis.from_url("redis://localhost:6379")
    pubsub = r.pubsub()
    await pubsub.subscribe("trade_signals")
    
    logger.info(f"Listening for signals from: {MODELS_TO_VERIFY}")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            model_id = data.get("model_id")
            
            if model_id in MODELS_TO_VERIFY:
                logger.info(f"✅ Verified Model: {model_id} | Signal: {data['signal']} | Conf: {data['confidence']}")
                VERIFIED_MODELS.add(model_id)
                
            if len(VERIFIED_MODELS) == len(MODELS_TO_VERIFY):
                logger.info("🎉 All models verified!")
                break

if __name__ == "__main__":
    try:
        asyncio.run(verify_models())
    except KeyboardInterrupt:
        pass
