
import os
import json
import requests

API_KEY = os.environ["YOUTUBE_API_KEY"]
WEBHOOK = os.environ["DISCORD_WEBHOOK"]
CHANNEL_ID = os.environ["YOUTUBE_CHANNEL_ID"]
ROLE_ID = os.environ["DISCORD_ROLE_ID"]

STATE_FILE = "youtube_state.json"

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

                state.setdefault("live", "")
                state.setdefault("videos", [])
                state.setdefault("live_history", [])

                return state

        except (json.JSONDecodeError, OSError):
            pass

    return {
        "live": "",
        "videos": [],
        "live_history": []
    }


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def youtube_get(endpoint, params):
    response = requests.get(
        f"{YOUTUBE_API}/{endpoint}",
        params=params,
        timeout=20
    )

    response.raise_for_status()
    return response.json()


def youtube_search(**params):
    params.update({
        "part": "snippet",
        "channelId": CHANNEL_ID,
        "type": "video",
        "maxResults": 10,
        "key": API_KEY
    })

    data = youtube_get("search", params)
    return data.get("items", [])


def make_video(item):
    video_id = item["id"].get("videoId")

    if not video_id:
        return None

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
        "title": snippet.get("title", "SRS Sim Racing Squad"),
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail": thumbnail.get("url", ""),
        "published_at": snippet.get("publishedAt", "")
    }


def get_live():
    items = youtube_search(
        eventType="live",
        order="date"
    )

    for item in items:
        video = make_video(item)

        if video:
            return video

    return None


def get_latest_videos():
    items = youtube_search(order="date")

    videos = []

    for item in items:
        video = make_video(item)

        if video:
            videos.append(video)

    return videos


def get_video_details(video_ids):
    """
    Pobiera szczegóły filmów.
    Sprawdza, czy YouTube oznacza materiał jako
    transmisję na żywo lub zapis transmisji.
    """

    if not video_ids:
        return {}

    data = youtube_get(
        "videos",
        {
            "part": "snippet,liveStreamingDetails",
            "id": ",".join(video_ids),
            "key": API_KEY
        }
    )

    return {
        item["id"]: item
        for item in data.get("items", [])
    }


def is_live_archive(video_details):
    """
    Zwraca True, jeżeli materiał ma dane transmisji
    na żywo, w tym informacje o zakończonej transmisji.
    """

    if not video_details:
        return False

    snippet = video_details.get("snippet", {})
    live_details = video_details.get("liveStreamingDetails", {})

    # Typowy zapis zakończonej transmisji.
    if live_details.get("actualStartTime"):
        return True

    # YouTube może oznaczać transmisję jako LIVE.
    if snippet.get("liveBroadcastContent") == "live":
        return True

    return False


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

    if video.get("thumbnail"):
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

    print(
        f"Wysłano {'LIVE' if live else 'FILM'}: "
        f"{video['title']}"
    )


def remember(items, video_id, limit=100):
    if video_id not in items:
        items.append(video_id)

    return items[-limit:]


def main():
    state = load_state()

    # 1. Sprawdź aktywną transmisję.
    live = get_live()
    live_id = live["id"] if live else ""

    if live:
        if live_id != state["live"]:
            if live_id not in state["live_history"]:
                send_discord(live, live=True)

                state["live_history"] = remember(
                    state["live_history"],
                    live_id
                )

        state["live"] = live_id

    else:
        state["live"] = ""

    # 2. Pobierz najnowsze filmy z kanału.
    videos = get_latest_videos()

    # Sprawdź szczegóły filmów, aby wykryć zapisy LIVE.
    details = get_video_details(
        [video["id"] for video in videos]
    )

    for video in reversed(videos):
        video_id = video["id"]

        # Nie wysyłaj aktywnej transmisji jako filmu.
        if video_id == live_id:
            continue

        # Nie wysyłaj ponownie tej samej transmisji,
        # jeśli wcześniej wysłano już powiadomienie LIVE.
        if video_id in state["live_history"]:
            continue

        # Nie wysyłaj zwykłego powiadomienia o zapisie LIVE.
        if is_live_archive(details.get(video_id)):
            state["live_history"] = remember(
                state["live_history"],
                video_id
            )
            continue

        # Nie wysyłaj ponownie tego samego filmu.
        if video_id in state["videos"]:
            continue

        # Wyślij powiadomienie o nowym zwykłym filmie.
        send_discord(video, live=False)

        state["videos"] = remember(
            state["videos"],
            video_id
        )

    save_state(state)


if __name__ == "__main__":
    main()
```
