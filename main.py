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
    default_state = {
        "videos": [],
        "live_history": [],
        "initialized": False
    }

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as file:
                state = json.load(file)

            for key, value in default_state.items():
                state.setdefault(key, value)

            return state

        except (json.JSONDecodeError, OSError):
            print("Nie można odczytać stanu. Używam pustego stanu.")

    return default_state


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


def remember(items, video_id, limit=500):
    if video_id not in items:
        items.append(video_id)

    return items[-limit:]


def youtube_get(endpoint, params):
    request_params = dict(params)
    request_params["key"] = API_KEY

    response = requests.get(
        f"{YOUTUBE_API}/{endpoint}",
        params=request_params,
        timeout=30
    )

    response.raise_for_status()
    return response.json()


def youtube_search(**params):
    search_params = {
        "part": "snippet",
        "channelId": CHANNEL_ID,
        "type": "video",
        "maxResults": 50
    }

    search_params.update(params)

    data = youtube_get("search", search_params)
    return data.get("items", [])


def make_video(item):
    video_id = item.get("id", {}).get("videoId")

    if not video_id:
        return None

    snippet = item.get("snippet", {})
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
    details = {}

    # YouTube API pozwala sprawdzać maksymalnie
    # 50 identyfikatorów w jednym zapytaniu.
    for start in range(0, len(video_ids), 50):
        batch = video_ids[start:start + 50]

        if not batch:
            continue

        data = youtube_get(
            "videos",
            {
                "part": "snippet,liveStreamingDetails",
                "id": ",".join(batch)
            }
        )

        for item in data.get("items", []):
            details[item["id"]] = item

    return details


def is_live_archive(details):
    """
    Rozpoznaje materiały powiązane z transmisjami.

    Zakończone transmisje mogą nadal mieć actualStartTime
    w liveStreamingDetails, dlatego nie należy traktować
    ich jako zwykłych filmów.
    """
    if not details:
        return False

    snippet = details.get("snippet", {})
    live_details = details.get("liveStreamingDetails", {})

    if live_details.get("actualStartTime"):
        return True

    if snippet.get("liveBroadcastContent") in ("live", "upcoming"):
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
        timeout=30
    )

    response.raise_for_status()

    print(
        f"Discord HTTP {response.status_code}: "
        f"{'LIVE' if live else 'FILM'} — {video['title']}"
    )


def main():
    state = load_state()

    print("Sprawdzam kanał YouTube SRS...")

    # 1. Wykryj aktywną transmisję.
    live = get_live()
    live_id = live["id"] if live else ""

    if live:
        print(f"Wykryto aktywny LIVE: {live['title']}")

        if live_id not in state["live_history"]:
            send_discord(live, live=True)

            state["live_history"] = remember(
                state["live_history"],
                live_id
            )

            save_state(state)
        else:
            print("Powiadomienie o tym LIVE było już wysłane.")
    else:
        print("Nie wykryto aktywnego LIVE.")

    # 2. Pobierz najnowsze filmy.
    videos = get_latest_videos()

    details = get_video_details(
        [video["id"] for video in videos]
    )

    # 3. Pierwsze uruchomienie:
    # zapamiętaj dotychczasowe materiały bez wysyłania
    # powiadomień o starych filmach.
    if not state["initialized"]:
        print("Pierwsze uruchomienie — zapisywanie historii.")

        for video in videos:
            video_id = video["id"]
            video_details = details.get(video_id, {})

            if is_live_archive(video_details):
                state["live_history"] = remember(
                    state["live_history"],
                    video_id
                )
            else:
                state["videos"] = remember(
                    state["videos"],
                    video_id
                )

        state["initialized"] = True
        save_state(state)

        print("Zapisano istniejące materiały.")
        return

    # 4. Sprawdź, czy pojawiły się nowe filmy.
    # Najpierw przetwarzamy starsze, potem nowsze.
    for video in reversed(videos):
        video_id = video["id"]

        # Nie wysyłaj aktywnej transmisji jako filmu.
        if video_id == live_id:
            continue

        # Nie wysyłaj materiału, dla którego już
        # wysłano powiadomienie LIVE.
        if video_id in state["live_history"]:
            continue

        video_details = details.get(video_id, {})

        # Nie wysyłaj zapisów transmisji jako zwykłych filmów.
        if is_live_archive(video_details):
            state["live_history"] = remember(
                state["live_history"],
                video_id
            )
            continue

        # Nie wysyłaj ponownie już obsłużonego filmu.
        if video_id in state["videos"]:
            continue

        send_discord(video, live=False)

        state["videos"] = remember(
            state["videos"],
            video_id
        )

        save_state(state)

    print("Sprawdzanie zakończone.")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as error:
        print(f"Błąd połączenia z YouTube lub Discordem: {error}")
        raise
    except Exception as error:
        print(f"Nieoczekiwany błąd bota: {error}")
        raise
