# WC Grid

Daily World Cup Immaculate Grid game. Men's WC 1990–2026.

## Regenerating data

```bash
# From repo root (activate venv first)

# 1. Fetch squad data from Wikipedia (caches HTML to data/wc_grid/raw/)
python -m ingestion.wc_grid.fetch_wikipedia all

# 2. Transform raw data -> normalized entities
python -m ingestion.wc_grid.transform all

# 3. Generate 400-day grid schedule (outputs to wc-grid/public/data/bundle.json)
python -m ingestion.wc_grid.generate_grids --days 400 --start 2026-06-01

# 4. Build the React app (outputs to static/wc-grid/)
cd wc-grid && npm run build
```

After `npm run build`, the Flask app at `/wc-grid` serves the updated game.

## Dev server

```bash
cd wc-grid
npm run dev
# Open http://localhost:5173/static/wc-grid/
```

## Running tests

```bash
# From repo root (with venv active)
python -m pytest tests/wc_grid/ -v
```

## Notes

- Bundle: ~3.8 MB JSON, gzips to ~900 KB. Re-generate after each new WC edition.
- Player IDs use `WP_<name>` format (Wikipedia-sourced). If the Wikidata SPARQL endpoint
  is available, run `python -m ingestion.wc_grid.fetch all` + re-transform for Wikidata QID-based IDs.
- See `DESIGN.md` in repo root for full data model and criterion catalog.
