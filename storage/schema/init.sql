-- TitanFlow Transactional Schema
CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    broker_account_id VARCHAR(255) UNIQUE NOT NULL,
    current_equity NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    buying_power NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    is_live BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS trade_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) CHECK (side IN ('BUY', 'SELL')),
    qty NUMERIC(10, 4) NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    filled_at TIMESTAMP WITH TIME ZONE,
    rationale TEXT,
    -- XAI explanation
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);