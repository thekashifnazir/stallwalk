// Forwards every request to the Cloud Run app, passing the visitor's IP on so the app's
// per-visitor rate limit still works behind the proxy.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const target = new URL(url.pathname + url.search, env.ORIGIN);
    const headers = new Headers(request.headers);
    const ip = request.headers.get("cf-connecting-ip") || "";
    headers.set("x-forwarded-for", ip);
    headers.set("x-stallwalk-client-ip", ip);
    headers.delete("host");
    const init = { method: request.method, headers, redirect: "manual" };
    if (!["GET", "HEAD"].includes(request.method)) init.body = request.body;
    const res = await fetch(target, init);
    const out = new Response(res.body, res);
    if (url.pathname.startsWith("/api/")) out.headers.set("cache-control", "no-store");
    return out;
  },
};
