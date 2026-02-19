/**
 * Shared helpers for TitanFlow E2E tests.
 *
 * mockSocketIO() intercepts all HTTP requests to the Socket.IO polling
 * endpoint and returns a minimal engine.io / socket.io handshake so that
 * components initialise without a live Redis instance.  Callers can pass an
 * array of additional socket.io event frames to inject after the handshake.
 *
 * Socket.IO v4 (engine.io v4) HTTP-polling protocol recap:
 *   1. Client GET (no sid)  → server: 0{...handshake JSON}
 *   2. Client POST           → server: ok
 *   3. Client GET (with sid) → server: 40{...namespace ACK}  (first poll)
 *   4. Subsequent GETs       → server: event frames or ping (2)
 *
 * Multiple frames in a single response are separated by the ASCII Record
 * Separator character \x1e (0x1e, decimal 30).
 */

import type { Page } from "@playwright/test";

/** One Socket.IO event to push to the browser */
export interface MockEvent {
  /** Socket.IO event name, e.g. "signal" */
  name: string;
  /** Serialisable payload */
  data: unknown;
}

/**
 * Register a route-level mock for the Socket.IO polling endpoint.
 *
 * @param page     Playwright page handle
 * @param events   Optional events to inject after the handshake
 */
export async function mockSocketIO(page: Page, events: MockEvent[] = []): Promise<void> {
  const SID = "playwright-test-sid";

  /** Convert a list of frames (already serialised) into a single polling body */
  const joinFrames = (...frames: string[]) => frames.join("\x1e");

  /** Build a socket.io EVENT frame: 42["name", data] */
  const eventFrame = (name: string, data: unknown) =>
    `42[${JSON.stringify(name)},${JSON.stringify(data)}]`;

  // Build the queue of poll responses after the namespace handshake.
  const pollQueue: string[] = [];

  // First poll: namespace connect ACK + optional server_status
  const firstPollFrames: string[] = [
    `40{"sid":"${SID}"}`, // namespace connect ack
    eventFrame("server_status", { redisConnected: true, executionMode: "paper" }),
  ];
  pollQueue.push(joinFrames(...firstPollFrames));

  // Subsequent polls: one event per poll, then keep-alive pings
  for (const ev of events) {
    pollQueue.push(eventFrame(ev.name, ev.data));
  }

  await page.route(/\/api\/socket\/io/, async (route) => {
    const method = route.request().method();
    const url = route.request().url();

    if (method === "GET" && !url.includes("sid=")) {
      // Step 1 – Initial engine.io handshake
      await route.fulfill({
        status: 200,
        contentType: "text/plain; charset=UTF-8",
        body: `0{"sid":"${SID}","upgrades":[],"pingInterval":25000,"pingTimeout":20000,"maxPayload":1000000}`,
      });
    } else if (method === "POST") {
      // Step 2 – Client sending namespace connect / ack frames
      await route.fulfill({
        status: 200,
        contentType: "text/plain; charset=UTF-8",
        body: "ok",
      });
    } else if (method === "GET" && url.includes(`sid=${SID}`)) {
      // Step 3+ – Long-poll responses
      const frame = pollQueue.shift() ?? "2"; // fall back to ping
      await route.fulfill({
        status: 200,
        contentType: "text/plain; charset=UTF-8",
        body: frame,
      });
    } else {
      await route.continue();
    }
  });
}

/** Navigate to the dashboard root and wait for the shell to be visible */
export async function gotoAndWait(page: Page): Promise<void> {
  await page.goto("/");
  // Wait for the TitanFlow heading which confirms the shell has mounted
  await page.waitForSelector("h1", { timeout: 15_000 });
}
