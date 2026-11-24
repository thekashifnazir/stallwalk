// Thin Worker for the hosted stallwalk: rate-limits /api/*, then proxies everything to one container.
import { DurableObject } from "cloudflare:workers";

const PORT = 8787;
const INACTIVITY_TIMEOUT_MS = 15 * 60 * 1000; // keep it warm through a demo
const SECRETS = ["TOKENFACTORY_API_KEY", "TOKENFACTORY_BASE_URL", "TAVILY_API_KEY"];

export class StallwalkContainer extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    const c = ctx.container;
    if (c?.running) {
      void ctx.blockConcurrencyWhile(() => c.setInactivityTimeout(INACTIVITY_TIMEOUT_MS));
    }
  }

  async fetch(request) {
    this.starting ??= this.startAndWait().finally(() => { this.starting = undefined; });
    await this.starting;
    const url = new URL(request.url);
    url.protocol = "http:";
    url.host = "container";
    const fwd = new Request(url, request);
    fwd.headers.delete("host");
    return this.ctx.container.getTcpPort(PORT).fetch(fwd);
  }

  async startAndWait() {
    const c = this.ctx.container;
    if (!c.running) {
      const env = {};
      for (const k of SECRETS) env[k] = this.env[k];
      c.start({ image: c.images.base, instance: "standard-1", enableInternet: true, env });
      this.ctx.waitUntil(c.monitor().catch((e) => console.error("container exited:", e)));
    }
    await c.setInactivityTimeout(INACTIVITY_TIMEOUT_MS);
    const port = c.getTcpPort(PORT);
    for (let i = 0; i < 300; i++) { // up to ~60s+ for a cold start
      try {
        const r = await port.fetch("http://container/api/agent/id", { signal: AbortSignal.timeout(1000) });
        await r.body?.cancel();
        if (r.ok) return;
      } catch { /* not listening yet */ }
      await scheduler.wait(200);
    }
    throw new Error(`container did not become ready on port ${PORT}`);
  }
}

const json = (status, body) => new Response(JSON.stringify(body), {
  status, headers: { "content-type": "application/json", "cache-control": "no-store" },
});

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    // fail closed: no secrets, no container (it would start without them)
    if (SECRETS.some((k) => !env[k])) return json(503, { error: "not configured" });
    if (pathname.startsWith("/api/")) {
      const ip = request.headers.get("cf-connecting-ip") || "unknown";
      let ok = false;
      try { ok = (await env.API_LIMIT.limit({ key: `api:${ip}` })).success; } catch { ok = false; }
      if (!ok) return json(429, { answer: "Too many requests, give it a minute.", error: "rate limited" });
    }
    try {
      const res = await env.STALLWALK.getByName("main").fetch(request);
      if (!pathname.startsWith("/api/")) return res;
      const out = new Response(res.body, res);
      out.headers.set("cache-control", "no-store");
      return out;
    } catch (e) {
      console.error("proxy error:", e);
      return json(503, { answer: "Stallwalk is starting up, try again in a few seconds.", error: "unavailable" });
    }
  },
};
