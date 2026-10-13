
import os
import requests

YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]
CHANNEL_ID = os.environ["YOUTUBE_CHANNEL_ID"]
STATE_FILE = "last_live.txt"

def get_live_stream():
    url = "https://www.googleapis.com/youtube/v3/search"

    params = {
        "part": "snippet",
        "channelId": CHANNEL_ID,
        "eventType": "live",
        "type": "video",
        "maxResults": 1,
        "key": YOUTUBE_API_KEY
    }

    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()

    items = response.json().get("items", [])

    if not items:
        return None

    video = items[0]
    video_id = video["id"]["videoId"]
    snippet = video["snippet"]

    return {
        "id": video_id,
        "title": snippet["title"],
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail": (
            snippet.get("thumbnails", {})
            .get("high", {})
            .get("url", "")
        )
    }

def main():
    live = get_live_stream()

    if live is None:
        print("SRS: brak aktywnej transmisji.")
        return

    last_id = ""

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            last_id = file.read().strip()

    if live["id"] == last_id:
        print("Ta transmisja została już ogłoszona.")
        return

    embed = {
        "title": "🔴 SRS SIM RACING SQUAD — JESTEŚMY NA ŻYWO!",
        "description": (
            f"🏁 **{live['title']}**\n\n"
            "🏎️ Gran Turismo 7\n"
            "🔥 Wpadaj na transmisję i kibicuj ekipie!\n\n"
            f"📺 [OGLĄDAJ NA ŻYWO]({live['url']})"
        ),
        "url": live["url"],
        "color": 15158332
    }

    if live["thumbnail"]:
        embed["image"] = {"url": live["thumbnail"]}

    payload = {
        "content": "🏁 @Społeczność **SRS NADAJE NA ŻYWO!** 🔴",
        "embeds": [embed],
        "allowed_mentions": {"parse": ["everyone"]}
    }

    response = requests.post(
        DISCORD_WEBHOOK,
        json=payload,
        timeout=20
    )
    response.raise_for_status()

    with open(STATE_FILE, "w", encoding="utf-8") as file:
        file.write(live["id"])

    print("Wysłano powiadomienie SRS na Discorda.")

if __name__ == "__main__":
    main()
