# i4 - Node.js Project

A Node.js application that fetches product prices from the Open Food Facts API, stores data in a local NeDB database, and scrapes country information from a website.

## Features

- **Open Food Facts Prices API** — Fetches product pricing data from the Open Food Facts API
- **NeDB Database** — File-backed NoSQL database for local data storage
- **Web Scraping** — Scrapes country data from scrapethissite.com using Cheerio

## Prerequisites

- Node.js 16.x or higher
- npm

## Installation

```bash
cd i4
npm install
```

## Usage

```bash
npm start
```

## Dependencies

- `node-fetch` — HTTP requests (v2)
- `cheerio` — HTML parsing and scraping
- `nedb-promises` — Local file-based database

## Project Structure

```
i4/
├── index.js      # Main application entry point
├── db.js         # Database initialization
├── package.json  # Project dependencies
└── products.db   # NeDB database file (created on run)
```