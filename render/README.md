# Arada Bingo Ethiopia — Render Deployment

This folder contains the full production-ready bot for deployment on [Render.com](https://render.com). It includes all backend logic, database models, templates, and static assets.

## Key Files
- `bot.py`: Main Telegram bot logic with Flask webhook
- `app.py`: Flask app (if used)
- `models.py`, `database.py`: SQLAlchemy setup
- `game_logic.py`: Bingo game logic
- `config.py`: Environment and bot settings
- `requirements.txt`: Python dependencies

## Folders
- `templates/`: HTML templates for admin dashboard
- `static/`: CSS and cartela assets
- `audio/`: Amharic audio files
- `utils/`: Helper functions (referral, validation, etc.)

## Deployment Notes
- Set environment variables in Render dashboard:
  - `TELEGRAM_BOT_TOKEN`
  - `WEBHOOK_URL`
- Make sure `requirements.txt` is up to date
- Webhook should point to your Render URL

This folder is ready for live deployment.
        
        └── winner.ogg
