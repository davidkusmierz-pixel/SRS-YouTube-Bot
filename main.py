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

        except (json.JSONDecodeError, OSError) as error:
            print(f"Nie można odczytać historii: {error}")

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
    print("Szukam aktywnej transmisji SRS...")

    items = youtube_search(
        eventType="live",
        order="date",
        maxResults=10
    )

    print(f"Aktywne transmisje zwrócone przez YouTube: {len(items)}")

    for item in items:
        video = make_video(item)

        if video:
            print(f"Znaleziono LIVE: {video['title']}")
            return video

    print("YouTube API nie zwróciło aktywnego LIVE.")
    return None


def get_latest_videos():
    items = youtube_search(order="date")
    videos = []

    for item in items:
        video = make_video(item)

        if video:
            videos.append(video)

    print(f"Znalezione materiały na kanale: {len(videos)}")
    return videos


def get_video_details(video_ids):
    details = {}

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
    Rozpoznaje aktywne, zaplanowane i zakończone transmisje,
    jeśli YouTube API udostępnia informacje o transmisji.
    """
    if not details:
        return False

    snippet = details.get("snippet", {})
    live_details = details.get("liveStreamingDetails", {})

    if snippet.get("liveBroadcastContent") in ("live", "upcoming"):
        return True

    if live_details.get("actualStartTime"):
        return True

    if live_details.get("actualEndTime"):
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
        f"Discord przyjął wiadomość HTTP {response.status_code}: "
        f"{'LIVE' if live else 'FILM'} — {video['title']}"
    )


def main():
    state = load_state()

    print("Sprawdzam kanał YouTube SRS...")

    # 1. Sprawdź aktywną transmisję.
    live = get_live()
    live_id = live["id"] if live else ""

    if live:
        if live_id not in state["live_history"]:
            send_discord(live, live=True)

            state["live_history"] = remember(
                state["live_history"],
                live_id
            )

            save_state(state)
        else:
            print("Ten LIVE ma już wysłane powiadomienie.")

    # 2. Pobierz filmy i sprawdź ich szczegóły.
    videos = get_latest_videos()
    details = get_video_details(
        [video["id"] for video in videos]
    )

    # 3. Pierwsze uruchomienie:
    # zapamiętaj istniejące materiały bez ogłaszania ich.
    if not state["initialized"]:
        print("Pierwsze uruchomienie — zapisuję dotychczasowe materiały.")

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

        print("Zapisano historię istniejących materiałów.")
        return

    # 4. Sprawdź nowe materiały.
    for video in reversed(videos):
        video_id = video["id"]

        # Nie ogłaszaj aktualnego LIVE jako filmu.
        if video_id == live_id:
            continue

        # Nie ogłaszaj ponownie transmisji już obsłużonej.
        if video_id in state["live_history"]:
            continue

        video_details = details.get(video_id, {})

        # Pomiń zapis transmisji rozpoznany przez YouTube API.
        if is_live_archive(video_details):
            state["live_history"] = remember(
                state["live_history"],
                video_id
            )

            save_state(state)
            print(f"Pominięto zapis transmisji: {video['title']}")
            continue

        # Nie wysyłaj ponownie znanych filmów.
        if video_id in state["videos"]:
            continue

        # Wyślij powiadomienie o nowym zwykłym filmie.
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
