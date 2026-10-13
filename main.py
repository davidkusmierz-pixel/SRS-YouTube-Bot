import os
import json
import requests

API_KEY = os.environ["YOUTUBE_API_KEY"]
WEBHOOK = os.environ["DISCORD_WEBHOOK"]
CHANNEL_ID = os.environ["YOUTUBE_CHANNEL_ID"]
ROLE_ID = os.environ["DISCORD_ROLE_ID"]

STATE_FILE = "youtube_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    return {"video": "", "live": ""}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def youtube_search(**params):
    params.update({
        "part": "snippet",
        "channelId": CHANNEL_ID,
        "type": "video",
        "maxResults": 1,
        "key": API_KEY
    })

    response = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params=params,
        timeout=20
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    return items[0] if items else None


def make_video(item):
    video_id = item["id"]["videoId"]
    snippet = item["snippet"]
    thumbnails = snippet.get("thumbnails", {})

    thumbnail = (
        thumbnails.get("maxres")
        or thumbnails.get("high")
        or thumbnails.get("medium")
        or thumbnails.get("default")
        or {}
    )

    return {
        "id": video_id,
        "title": snippet["title"],
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail": thumbnail.get("url", "")
    }


def get_video():
    item = youtube_search(order="date")
    return make_video(item) if item else None


def get_live():
    item = youtube_search(eventType="live")
    return make_video(item) if item else None


def send_discord(video, live=False):
    if live:
        title = "🔴 SRS SIM RACING SQUAD — JESTEŚMY NA ŻYWO!"
        description = (
            f"🏁 **{video['title']}**\n\n"
            "🏎️ Gran Turismo 7\n"
            "🔥 Wpadaj na transmisję i kibicuj ekipie SRS!\n\n"
            f"📺 [OGLĄDAJ NA ŻYWO]({video['url']})"
        )
        color = 15158332
        message = "🔴 **SRS NADAJE NA ŻYWO!**"
    else:
        title = "🎬 NOWY FILM SRS!"
        description = (
            f"🏁 **{video['title']}**\n\n"
            "🏎️ Sim Racing Squad | Gran Turismo 7\n\n"
            f"📺 [OBEJRZYJ FILM]({video['url']})"
        )
        color = 3447003
        message = "🎬 **NOWY FILM NA KANALE SRS!**"

    embed = {
        "title": title,
        "description": description,
        "url": video["url"],
        "color": color
    }

    if video["thumbnail"]:
        embed["image"] = {"url": video["thumbnail"]}

    payload = {
        "content": f"<@&{ROLE_ID}> {message}",
        "embeds": [embed],
        "allowed_mentions": {
            "roles": [ROLE_ID]
        }
    }

    response = requests.post(
        WEBHOOK,
        json=payload,
        timeout=20
    )
    response.raise_for_status()
    print("Wysłano:", video["title"])


def main():
    state = load_state()

    video = get_video()
    if video and video["id"] != state.get("video", ""):
        send_discord(video, live=False)
        state["video"] = video["id"]

    live = get_live()
    if live and live["id"] != state.get("live", ""):
        send_discord(live, live=True)
        state["live"] = live["id"]

    save_state(state)


if __name__ == "__main__":
    main()
