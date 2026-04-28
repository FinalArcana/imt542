// index.js — Final version (CommonJS, no native modules)

// ---------- Imports ----------
const fetch = require("node-fetch");        // MUST be v2
const cheerio = require("cheerio");
const Datastore = require("nedb-promises");

// ---------- 1. Open Food Facts Prices API ----------
async function fetchPricesApi() {
  const url = "https://prices.openfoodfacts.org/api/v1/prices?page=1&page_size=1";

  const res = await fetch(url);
  if (!res.ok) throw new Error(`API error: ${res.status}`);

  const data = await res.json();
  console.log("\n=== Prices API Sample ===");
  console.log(data);
}

// ---------- 2. NeDB database (file-backed, pure JS) ----------
async function useNedb() {
  const db = Datastore.create({
    filename: "products.db",
    autoload: true
  });

  // Insert sample doc if DB is empty
  const count = await db.count({});
  if (count === 0) {
    await db.insert({ name: "Sample Product", createdAt: new Date() });
  }

  const doc = await db.findOne({});
  console.log("\n=== NeDB Sample ===");
  console.log(doc);
}

// ---------- 3. Scrape scrapethissite.com ----------
async function scrapeSimpleSite() {
  const url = "https://www.scrapethissite.com/pages/simple/";
  const html = await fetch(url).then(r => r.text());
  const $ = cheerio.load(html);

  const countries = [];

  $(".country").each((_, el) => {
    const name = $(el).find(".country-name").text().trim();
    const capital = $(el).find(".country-capital").text().trim();
    countries.push({ name, capital });
  });

  console.log("\n=== Scraped Countries (first 5) ===");
  console.log(countries.slice(0, 5));
}

// ---------- Run all three ----------
async function main() {
  await fetchPricesApi();
  await useNedb();
  await scrapeSimpleSite();
}

main().catch(err => {
  console.error("Error in main:", err);
});
