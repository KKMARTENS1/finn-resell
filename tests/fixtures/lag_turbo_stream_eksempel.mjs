// Lager tests/fixtures/finn_turbo_stream.html: en søkeside i samme format som Finn bruker.
// Kjør: npm install turbo-stream@2 && node lag_turbo_stream_eksempel.mjs > finn_turbo_stream.html
import { encode } from "turbo-stream";

const ts = 1758600000000; // fast tidspunkt
const doc = (id, heading, amount, location, extra = {}) => ({
  type: "bap", id: String(id), ad_id: id, main_search_key: "SEARCH_ID_BAP_COMMON",
  heading, location,
  image: { url: `https://images.finncdn.no/dynamic/default/2025/9/vertical-0/23/${id}.jpg`, path: "x", height: 900, width: 1200, aspect_ratio: 1.33 },
  flags: ["private"], timestamp: ts - id % 7 * 3600000,
  canonical_url: `https://www.finn.no/recommerce/forsale/item/${id}`,
  price: { amount, currency_code: "NOK", price_unit: "kr" },
  trade_type: "Til salgs", labels: [], ...extra,
});

const loaderData = {
  root: { user: null, locale: "nb", featureFlags: { a: true, b: false } },
  "routes/recommerce+/forsale+/search": {
    results: {
      docs: [
        doc(412345671, "Scotty Cameron Newport 2 putter 34\"", 2500, "Oslo"),
        doc(412345672, "Titleist TSR3 driver 10.0 Tensei skaft", 3200, "Bergen"),
        doc(412345673, "Ønskes kjøpt: Scotty Cameron", 0, "Trondheim", { trade_type: "Ønskes kjøpt" }),
        doc(412345674, "Scotty Cameron Special Select Newport 2", 3900, "Oslo"),
      ],
      metadata: { result_size: { match_count: 4 }, sort: "PUBLISHED_DESC" },
    },
    recommendations: Promise.resolve([
      { heading: "Anbefalt: Ping G425 driver", ad_id: 499999999, price: { amount: 1500 }, canonical_url: "https://www.finn.no/recommerce/forsale/item/499999999" },
    ]),
    when: new Date(ts),
  },
};

const stream = encode(loaderData);
const reader = stream.getReader();
const chunks = [];
for (;;) { const { value, done } = await reader.read(); if (done) break; chunks.push(typeof value === "string" ? value : new TextDecoder().decode(value)); }
const esc = (s) => s.replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/&/g, "\\u0026").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
const scripts = chunks.map((c) => `<script>window.__reactRouterContext.streamController.enqueue(${esc(JSON.stringify(c))});</script>`).join("\n");
const html = `<!DOCTYPE html><html lang="nb"><head><meta charset="utf-8"><title>Scotty cameron | FINN torget</title></head>
<body><main><h1>Scotty cameron</h1><div id="app"><p>Laster …</p></div></main>
<script>window.__reactRouterContext = {"basename":"/","future":{},"isSpaMode":false};window.__reactRouterContext.stream = new ReadableStream({start(controller){window.__reactRouterContext.streamController = controller;}}).pipeThrough(new TextEncoderStream());</script>
${scripts}
<script>window.__reactRouterContext.streamController.close();</script>
</body></html>`;
process.stdout.write(html);
