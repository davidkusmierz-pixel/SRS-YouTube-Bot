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
        json.dump(state, f, ensure_ascii=False, indent=2)


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

    return response.json().get("items", [])


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


def get_latest_video():
    items = youtube_search(order="date")
    return make_video(items[0]) if items else None


def get_live():
    items = youtube_search(eventType="live")
    return make_video(items[0]) if items else None


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

    response = requests.post(WEBHOOK, json=payload, timeout=20)
    response.raise_for_status()

    print(f"Wysłano {'LIVE' if live else 'FILM'}: {video['title']}")


def main():
    state = load_state()

    # Najpierw sprawdź transmisję na żywo.
    live = get_live()
    live_id = live["id"] if live else ""

    if live and live_id != state.get("live", ""):
        send_discord(live, live=True)
        state["live"] = live_id

    # Następnie sprawdź najnowszy film.
    video = get_latest_video()

    if video:
        video_id = video["id"]

        # Nie wysyłaj tej samej transmisji ponownie jako filmu.
        if video_id != live_id and video_id != state.get("video", ""):
            send_discord(video, live=False)

        state["video"] = video_id

    save_state(state)


if __name__ == "__main__":
    main()
