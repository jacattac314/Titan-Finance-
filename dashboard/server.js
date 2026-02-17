const { createServer } = require("http");
const { parse } = require("url");
const next = require("next");
const { Server } = require("socket.io");
const { createClient } = require("redis");

const dev = process.env.NODE_ENV !== "production";
const app = next({ dev });
const handle = app.getRequestHandler();

const defaultRedisUrl = dev ? "redis://localhost:6379" : "redis://redis:6379";
const EXECUTION_MODE = process.env.EXECUTION_MODE || "paper";

function buildRedisCandidates() {
    const candidates = [];
    if (process.env.REDIS_URL) {
        candidates.push(process.env.REDIS_URL);
    }
    candidates.push(defaultRedisUrl);
    candidates.push(dev ? "redis://redis:6379" : "redis://localhost:6379");
    return [...new Set(candidates)];
}

async function connectRedisWithFallback() {
    const candidates = buildRedisCandidates();

    for (const url of candidates) {
        const client = createClient({
            url,
            socket: {
                connectTimeout: 3000,
                reconnectStrategy: (retries) => {
                    if (retries > 5) {
                        console.warn("Redis: Max retries reached. Stopping reconnection attempts.");
                        return new Error("Max retries reached");
                    }
                    return Math.min(retries * 50, 2000);
                },
            },
        });

        try {
            await client.connect();
            return { client, url };
        } catch (err) {
            console.warn(`Redis unavailable at ${url}: ${err.message}`);
            try {
                await client.disconnect();
            } catch (_) {
                // no-op
            }
        }
    }

    throw new Error("No Redis candidates were reachable.");
}

app.prepare().then(async () => {
    const server = createServer((req, res) => {
        const parsedUrl = parse(req.url, true);
        handle(req, res, parsedUrl);
    });

    const io = new Server(server, {
        path: "/api/socket/io",
        addTrailingSlash: false,
    });

    let redisConnected = false;

    const broadcastStatus = () => {
        io.emit("server_status", {
            redisConnected,
            executionMode: EXECUTION_MODE,
            serverTime: Date.now(),
        });
    };

    io.on("connection", (socket) => {
        console.log("Client connected:", socket.id);
        socket.emit("server_status", {
            redisConnected,
            executionMode: EXECUTION_MODE,
            serverTime: Date.now(),
        });

        socket.on("latency_ping", (clientSentAt, callback) => {
            if (typeof callback === "function") {
                callback({
                    clientSentAt,
                    serverSentAt: Date.now(),
                });
            }
        });

        socket.on("disconnect", () => {
            console.log("Client disconnected:", socket.id);
        });
    });

    const PORT = process.env.PORT || 3000;
    server.listen(PORT, (err) => {
        if (err) throw err;
        console.log(`> Ready on http://localhost:${PORT}`);

        // Connect to Redis after server starts
        (async () => {
            let subscriber = null;
            let connectedRedisUrl = null;

            try {
                const result = await connectRedisWithFallback();
                subscriber = result.client;
                connectedRedisUrl = result.url;
            } catch (err) {
                redisConnected = false;
                broadcastStatus();
                console.warn("Failed to connect to Redis. Dashboard running in standalone mode.");
                return;
            }

            subscriber.on("error", (err) => {
                redisConnected = false;
                broadcastStatus();
                if (err.code !== "ENOTFOUND" && err.code !== "ECONNREFUSED") {
                    console.error("Redis Client Error:", err.message);
                }
            });

            subscriber.on("ready", () => {
                redisConnected = true;
                broadcastStatus();
            });

            subscriber.on("end", () => {
                redisConnected = false;
                broadcastStatus();
            });

            try {
                console.log(`Connected to Redis at ${connectedRedisUrl}`);
                redisConnected = true;
                broadcastStatus();

                // Subscribe to trade signals and market data
                await subscriber.subscribe("trade_signals", (message) => {
                    try {
                        const signal = JSON.parse(message);
                        console.log("Emitting signal:", signal.symbol, signal.signal);
                        io.emit("signal", signal);
                    } catch (e) {
                        console.error("Failed to parse signal:", e);
                    }
                });

                await subscriber.subscribe("market_data", (message) => {
                    try {
                        const tick = JSON.parse(message);
                        // Lightweight emit for high frequency
                        io.emit("price_update", tick);
                    } catch (e) {
                        // console.error("Failed to parse tick:", e);
                    }
                });

                await subscriber.subscribe("execution_filled", (message) => {
                    try {
                        const trade = JSON.parse(message);
                        console.log("Emitting trade update:", trade.symbol, trade.side);
                        io.emit("trade_update", trade);
                    } catch (e) {
                        console.error("Failed to parse trade:", e);
                    }
                });

                await subscriber.subscribe("paper_portfolio_updates", (message) => {
                    try {
                        const portfolios = JSON.parse(message);
                        io.emit("paper_portfolios", portfolios);
                    } catch (e) {
                        console.error("Failed to parse paper portfolios:", e);
                    }
                });
            } catch (err) {
                redisConnected = false;
                broadcastStatus();
                console.warn("Redis subscriptions failed. Dashboard running in standalone mode.");
            }
        })();
    });
});
