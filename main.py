name: SRS YouTube LIVE

on:
  schedule:
    - cron: "*/5 * * * *"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  check-live:
    runs-on: ubuntu-latest

    steps:
      - name: Pobierz repozytorium
        uses: actions/checkout@v4

      - name: Ustaw Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Zainstaluj biblioteki
        run: pip install requests

      - name: Sprawdź aktywną transmisję SRS
        env:
          YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}
          DISCORD_WEBHOOK: ${{ secrets.DISCORD_WEBHOOK }}
          YOUTUBE_CHANNEL_ID: ${{ secrets.YOUTUBE_CHANNEL_ID }}
          DISCORD_ROLE_ID: ${{ secrets.DISCORD_ROLE_ID }}
        run: python main.py

      - name: Zapisz stan LIVE
        run: |
          git config user.name "SRS YouTube Bot"
          git config user.email "srs-bot@users.noreply.github.com"
          git add youtube_live_state.txt
          if ! git diff --cached --quiet; then
            git commit -m "Update YouTube LIVE state"
            git push
          fi
