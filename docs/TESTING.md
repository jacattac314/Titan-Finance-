# Testing Strategy

## Overview
TitanFlow employs a mix of unit testing for logic validation and integration testing for system flow verification.

## Manual Verification Scripts
Located in `scripts/`, these python scripts allow for isolated testing of service components within the Docker network.

### 1. Verify Signal Engine
Tests the generation of signals from mock market data.
**Usage**:
```bash
docker cp services/signal/verify_signal_engine.py titan_signal:/app/
docker exec titan_signal python /app/verify_signal_engine.py
```

### 2. Verify Trade Log (End-to-End Flow)
Simulates a trade execution to verify the Dashboard's Trade Log update mechanism.
**Usage**:
```bash
docker cp scripts/verify_trade_log.py titan_execution:/app/
docker exec -e REDIS_HOST=redis titan_execution python /app/verify_trade_log.py
```

## Unit Tests (Planned)
*   **Framework**: `pytest`
*   **Location**: `tests/` directory in each service.
*   **Coverage Goals**:
    *   `services/signal`: Feature engineering logic, Model inference mocking.
    *   `services/risk`: drawdown calculation, position sizing limits.
    *   `services/gateway`: API endpoint validation.

## Integration Tests (Planned)
*   **Goal**: Verify the full pipeline: Gateway -> Signal -> Risk -> Execution.
*   **Tools**: Docker Compose + Testcontainers.
*   **Scenario**:
    1.  Inject mock tick into `market_data`.
    2.  Assert `trade_signals` published.
    3.  Assert `execution_requests` published (if valid).
    4.  Assert `execution_filled` published.
