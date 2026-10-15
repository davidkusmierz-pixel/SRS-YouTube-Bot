import os
import json
import requests
from pathlib import Path

API_KEY = os.environ["YOUTUBE_API_KEY"]
WEBHOOK = os.environ["DISCORD_WEBHOOK"]
CHANNEL_ID = os.environ["YOUTUBE_CHANNEL_ID"]
ROLE_ID = os.environ.get("DISCORD_ROLE_ID", "").strip()
MODE = os.environ.get("SRS_MODE", "last_live").strip()

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
STATE_FILE = Path("youtube_state.json")


def youtube_get(endpoint, params):
    params = dict(params)
    params["key"] = API_KEY
    response = requests.get(f"{YOUTUBE_API}/{endpoint}", params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def load_state():
    if not STATE_FILE.exists():
        return {"sent_live": [], "sent_videos": []}
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        state.setdefault("sent_live", [])
        state.setdefault("sent_videos", [])
        return state
    except (OSError, json.JSONDecodeError):
        return {"sent_live": [], "sent_videos": []}


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )


def get_video(video_id):
    data = youtube_get("videos", {
        "part": "snippet,liveStreamingDetails",
        "id": video_id
    })
    items = data.get("items", [])
    if not items:
        return None
    video = items[0]
    snippet = video.get("snippet", {})
    live = video.get("liveStreamingDetails", {})
    thumbs = snippet.get("thumbnails", {})
    thumb = thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or {}
    return {
        "id": video_id,
        "title": snippet.get("title", "SRS YouTube"),
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail": thumb.get("url", ""),
        "is_live_archive": bool(live.get("actualStartTime")),
        "is_active": bool(live.get("actualStartTime") and not live.get("actualEndTime")),
        "published_at": snippet.get("publishedAt", "")
    }


def search_videos(**params):
    result = youtube_get("search", {
        "part": "snippet",
        "channelId": CHANNEL_ID,
        "type": "video",
        "maxResults": 25,
        **params
    })
    return [x.get("id", {}).get("videoId") for x in result.get("items", [])
            if x.get("id", {}).get("videoId")]


def get_last_live():
    # Prefer completed streams, newest first.
    ids = search_videos(eventType="completed", order="date")
    for video_id in ids:
        item = get_video(video_id)
        if item and item["is_live_archive"] and not item["is_active"]:
            return item

    # If there is no completed stream available, use the active live.
    ids = search_videos(eventType="live", order="date")
    for video_id in ids:
        item = get_video(video_id)
        if item and item["is_live_archive"]:
            return item
    return None


def get_new_regular_videos():
    ids = search_videos(order="date")
    videos = []
    seen = set()
    for video_id in ids:
        if video_id in seen:
            continue
        seen.add(video_id)
        item = get_video(video_id)
        if item and not item["is_live_archive"]:
            videos.append(item)
    return videos


def send_to_discord(item, kind):
    if kind == "live":
        heading = "🔴 SRS OSTATNI LIVE"
        content = f"🔴 **SRS — OSTATNI LIVE**"
        color = 15158332
        action = "📺 [OGLĄDAJ TRANSMISJĘ]"
    else:
        heading = "🎬 NOWY FILM SRS"
        content = "🎬 **NOWY FILM SRS**"
        color = 3447003
        action = "▶️ [OGLĄDAJ FILM]"

    if ROLE_ID:
        content = f"<@&{ROLE_ID}> {content}"

    embed = {
        "title": heading,
        "description": f"🏁 **{item['title']}**\n\n{action}({item['url']})",
        "url": item["url"],
        "color": color
    }
    if item.get("thumbnail"):
        embed["image"] = {"url": item["thumbnail"]}

    payload = {"content": content, "embeds": [embed]}
    if ROLE_ID:
        payload["allowed_mentions"] = {"roles": [ROLE_ID]}

    response = requests.post(WEBHOOK, json=payload, timeout=30)
    response.raise_for_status()
    print(f"Wysłano na Discorda: {item['title']} ({item['id']})")


def main():
    if MODE == "last_live":
        item = get_last_live()
        if not item:
            print("Nie znaleziono ostatniego LIVE (aktywnego ani zakończonego).")
            return
        state = load_state()
        if item["id"] in state["sent_live"]:
            print(f"Ten LIVE był już wysłany: {item['title']}")
            return
        send_to_discord(item, "live")
        state["sent_live"].append(item["id"])
        save_state(state)
        print("Ostatni LIVE wysłany i zapisany w historii.")
        return

    if MODE == "new_videos":
        state = load_state()
        sent_ids = set(state["sent_videos"])
        candidates = get_new_regular_videos()
        new_items = [v for v in candidates if v["id"] not in sent_ids]
        if not new_items:
            print("Brak nowych zwykłych filmów. Archiwa LIVE są pomijane.")
            return

        # Oldest first, so Discord receives them in chronological order.
        for item in reversed(new_items):
            send_to_discord(item, "video")
            state["sent_videos"].append(item["id"])
            save_state(state)
        print(f"Wysłano {len(new_items)} nowych zwykłych filmów.")
        return

    raise ValueError(f"Nieznany tryb SRS_MODE: {MODE}")


if __name__ == "__main__":
    main()
