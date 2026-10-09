# Sc v21 - Responsive category pages

## Changes

- The existing Sc Telegram bot and website remain in one repository.
- Mobile navigation opens distinct Manga, Manhwa, Webtoon, and 18+ category routes.
- Each category has its own description and two-column mobile card grid.
- Clicking a card opens a separate title details route with synopsis and chapter list.
- Reader pages remain previews until authorized Telegram storage publishing is implemented.
- MongoDB status in Telegram settings reads effective values from `SC_MONGO_URI`, `config.py`, or `data/mongo.env`, showing Set or Not set.
- Storage channel is configured through the Telegram bot and requires bot administrator privileges.
- No website credentials form is provided.

## Run

From the existing `/root/Sc` virtual environment: `source .venv/bin/activate && python Miko.py`. Website port: 1980. No new Python dependencies.

## Note

The website is still a design preview. It does not serve actual chapters or connect to MongoDB. Only publish content for which you have appropriate rights.
