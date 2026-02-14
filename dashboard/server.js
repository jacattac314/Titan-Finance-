const { createServer } = require("http");
const { parse } = require("url");
const next = require("next");
const { Server } = require("socket.io");
const { createClient } = require("redis");

const dev = process.env.NODE_ENV !== "production";
const app = next({ dev });
const handle = app.getRequestHandler();

const REDIS_URL = process.env.REDIS_URL || "redis://redis:6379";

app.prepare().then(async () => {
    const server = createServer((req, res) => {
        const parsedUrl = parse(req.url, true);
        handle(req, res, parsedUrl);
    });

    const io = new Server(server, {
        path: "/api/socket/io",
        addTrailingSlash: false,
    });

    io.on("connection", (socket) => {
        console.log("Client connected:", socket.id);

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
            const subscriber = createClient({
                url: REDIS_URL,
                socket: {
                    reconnectStrategy: (retries) => {
                        if (retries > 5) {
                            console.warn("Redis: Max retries reached. Stopping reconnection attempts.");
                            return new Error("Max retries reached");
                        }
                        return Math.min(retries * 50, 2000);
                    }
                }
            });

            subscriber.on('error', (err) => {
                // Suppress excessive error logs
                if (err.code === 'ENOTFOUND' || err.code === 'ECONNREFUSED') {
                    // console.warn('Redis unavailable (running in standalone mode)');
                } else {
                    console.error('Redis Client Error:', err.message);
                }
            });

            try {
                await subscriber.connect();
                console.log(`Connected to Redis at ${REDIS_URL}`);

                // Subscribe to trade signals
                await subscriber.subscribe("trade_signals", (message) => {
                    try {
                        const signal = JSON.parse(message);
                        console.log("Emitting signal:", signal.symbol, signal.signal);
                        io.emit("signal", signal);
                    } catch (e) {
                        console.error("Failed to parse signal:", e);
                    }
                });
            } catch (err) {
                console.warn("⚠️ Failed to connect to Redis. Dashboard running in standalone mode.");
            }
        })();
    });
});
