import os
import requests

API_KEY = os.environ["YOUTUBE_API_KEY"]
WEBHOOK = os.environ["DISCORD_WEBHOOK"]
CHANNEL_ID = os.environ["YOUTUBE_CHANNEL_ID"]
ROLE_ID = os.environ["DISCORD_ROLE_ID"]

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
STATE_FILE = "youtube_live_state.txt"


def youtube_get(endpoint, params):
    params = dict(params)
    params["key"] = API_KEY

    response = requests.get(
        f"{YOUTUBE_API}/{endpoint}",
        params=params,
        timeout=30
    )

    response.raise_for_status()
    return response.json()


def get_active_live():
    print("Sprawdzam aktywną transmisję SRS...")

    data = youtube_get(
        "search",
        {
            "part": "snippet",
            "channelId": CHANNEL_ID,
            "type": "video",
            "eventType": "live",
            "maxResults": 10
        }
    )

    items = data.get("items", [])
    print(f"Transmisje zwrócone przez YouTube: {len(items)}")

    for item in items:
        video_id = item.get("id", {}).get("videoId")

        if not video_id:
            continue

        details = youtube_get(
            "videos",
            {
                "part": "snippet,liveStreamingDetails",
                "id": video_id
            }
        )

        videos = details.get("items", [])

        if not videos:
            continue

        video = videos[0]
        snippet = video.get("snippet", {})
        live_details = video.get("liveStreamingDetails", {})

        # Akceptuj tylko transmisję, która faktycznie trwa.
        if (
            live_details.get("actualStartTime")
            and not live_details.get("actualEndTime")
        ):
            thumbnails = snippet.get("thumbnails", {})
            thumbnail = (
                thumbnails.get("maxres")
                or thumbnails.get("high")
                or thumbnails.get("medium")
                or {}
            )

            return {
                "id": video_id,
                "title": snippet.get(
                    "title",
                    "SRS Gran Turismo 7 LIVE"
                ),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "thumbnail": thumbnail.get("url", "")
            }

    print("Nie znaleziono aktywnej transmisji.")
    return None


def get_previous_live():
    if not os.path.exists(STATE_FILE):
        return ""

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return file.read().strip()
    except OSError as error:
        print(f"Nie można odczytać historii LIVE: {error}")
        return ""


def save_live_id(video_id):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        file.write(video_id)


def send_live_to_discord(live):
    embed = {
        "title": "🔴 SRS NADAJE NA ŻYWO!",
        "description": (
            f"🏁 **{live['title']}**\n\n"
            "🏎️ Gran Turismo 7\n"
            "🔥 Dołącz do transmisji!\n\n"
            f"📺 [OGLĄDAJ NA ŻYWO]({live['url']})"
        ),
        "url": live["url"],
        "color": 15158332
    }

    if live["thumbnail"]:
        embed["image"] = {"url": live["thumbnail"]}

    payload = {
        "content": f"<@&{ROLE_ID}> 🔴 **SRS JEST NA ŻYWO!**",
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

    print(f"Discord przyjął powiadomienie: HTTP {response.status_code}")


def main():
    live = get_active_live()

    if not live:
        print("Brak aktywnego LIVE. Koniec sprawdzania.")
        return

    print(f"Wykryto LIVE: {live['title']}")

    previous_live = get_previous_live()

    if previous_live == live["id"]:
        print("Ta transmisja została już ogłoszona.")
        return

    # Najpierw wyślij powiadomienie.
    send_live_to_discord(live)

    # Zapisz ID dopiero po udanym wysłaniu wiadomości.
    save_live_id(live["id"])

    print("Powiadomienie LIVE wysłane i zapisane.")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as error:
        print(f"Błąd połączenia z YouTube lub Discordem: {error}")
        raise
    except Exception as error:
        print(f"Nieoczekiwany błąd: {error}")
        raise
