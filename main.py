"""
Père Mehdi Ciné - Films, séries, dessins animés et football GRATUITS et LÉGAUX.
Sources : Internet Archive (œuvres libres de droits) + chaînes YouTube officielles
(FIFA, CAF TV, UEFA, ligues…). Aucune publicité, aucun site pirate.
"""
import json
import os
import ssl
import sys
import threading
import urllib.parse
import urllib.request

import certifi
import flet as ft
import yt_dlp

APP = "Père Mehdi Ciné"
IS_ANDROID = hasattr(sys, "getandroidapilevel") or "ANDROID_ROOT" in os.environ
CTX = ssl.create_default_context(cafile=certifi.where())
UA = {"User-Agent": "PereMehdiCine/1.0"}

# ---------------------------------------------------------------- Internet Archive
CATEGORIES = {
    "films": ("Films", "feature_films", ft.Icons.MOVIE),
    "series": ("Séries", "classic_tv", ft.Icons.LIVE_TV),
    "anime": ("Dessins animés", "animationandcartoons", ft.Icons.CHILD_CARE),
}


def http_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, context=CTX, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def archive_search(collection, text="", french=False, page=1, rows=40):
    q = f"collection:({collection}) AND mediatype:(movies)"
    if text:
        q += f" AND ({text})"
    if french:
        q += " AND language:(French OR fre OR Français)"
    params = [("q", q), ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "year"),
              ("sort[]", "downloads desc"), ("rows", str(rows)), ("page", str(page)),
              ("output", "json")]
    url = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(params)
    docs = http_json(url).get("response", {}).get("docs", [])
    out = []
    for d in docs:
        title = d.get("title")
        if isinstance(title, list):
            title = title[0]
        out.append({
            "kind": "archive",
            "id": d["identifier"],
            "title": title or d["identifier"],
            "sub": str(d.get("year", ""))[:4],
            "thumb": f"https://archive.org/services/img/{d['identifier']}",
        })
    return out


def archive_video_url(identifier):
    """Trouve le meilleur fichier MP4 d'une œuvre Internet Archive."""
    meta = http_json(f"https://archive.org/metadata/{identifier}")
    files = meta.get("files", [])
    mp4 = [f for f in files if f.get("name", "").lower().endswith(".mp4")]
    if not mp4:
        return None, None
    # préfère le fichier h.264 de taille raisonnable
    def rank(f):
        n, fmt = f["name"].lower(), f.get("format", "").lower()
        if "512kb" in n:
            return 0          # léger : idéal sur données mobiles
        if "h.264" in fmt:
            return 1
        return 2
    mp4.sort(key=rank)
    best = mp4[0]["name"]
    return f"https://archive.org/download/{identifier}/{urllib.parse.quote(best)}", best


# ---------------------------------------------------------------- Football (YouTube officiel)
OFFICIAL = ["caf tv", "cafonline", "fifa", "uefa", "champions league", "premier league",
            "laliga", "ligue 1", "bundesliga", "serie a", "afcon", "can ", "bein sports"]

FOOT_CHIPS = [
    ("Afrique (CAF)", "CAF TV highlights"),
    ("Matchs en direct", "CAF TV live"),
    ("FIFA", "FIFA highlights"),
    ("Ligue des champions", "UEFA Champions League highlights"),
    ("Premier League", "Premier League highlights"),
    ("LaLiga", "LaLiga highlights"),
    ("Ligue 1", "Ligue 1 résumé"),
]


def is_official(entry):
    ch = (entry.get("channel") or entry.get("uploader") or "").lower()
    if not ch:
        return False
    verified = entry.get("channel_is_verified")
    return any(k in ch + " " for k in OFFICIAL) and verified is not False


def youtube_search(query, live_only=False, n=40):
    opts = {"quiet": True, "extract_flat": True, "skip_download": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    out = []
    for e in info.get("entries", []) or []:
        if not e or not e.get("id") or not is_official(e):
            continue
        live = e.get("live_status") == "is_live"
        if live_only and not live:
            continue
        thumbs = e.get("thumbnails") or []
        out.append({
            "kind": "youtube",
            "id": e["id"],
            "title": e.get("title", ""),
            "sub": ("🔴 EN DIRECT • " if live else "") + (e.get("channel") or ""),
            "thumb": thumbs[-1]["url"] if thumbs else f"https://i.ytimg.com/vi/{e['id']}/hqdefault.jpg",
        })
    return out


# ---------------------------------------------------------------- Interface
def main(page: ft.Page):
    page.title = APP
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.AMBER)
    page.padding = 0
    if not IS_ANDROID:
        page.window.width = 1000
        page.window.height = 760

    state = {"tab": "films", "query": "", "french": False, "page": 1, "foot": FOOT_CHIPS[0]}

    grid = ft.GridView(expand=True, max_extent=190, child_aspect_ratio=0.62,
                       spacing=10, run_spacing=10, padding=12)
    status = ft.Text("", size=13, color=ft.Colors.GREY_400)
    loader = ft.ProgressBar(visible=False)
    more_btn = ft.TextButton("Voir plus", icon=ft.Icons.EXPAND_MORE, visible=False)

    def snack(msg):
        page.open(ft.SnackBar(ft.Text(msg)))

    # ----- lecture
    def play(item):
        if item["kind"] == "youtube":
            page.launch_url(f"https://www.youtube.com/watch?v={item['id']}")
            return

        def work():
            try:
                snack("Ouverture du film…")
                url, _ = archive_video_url(item["id"])
                page.launch_url(url or f"https://archive.org/details/{item['id']}")
            except Exception:
                page.launch_url(f"https://archive.org/details/{item['id']}")
        threading.Thread(target=work, daemon=True).start()

    def download(item):
        def work():
            try:
                url, name = archive_video_url(item["id"])
                if not url:
                    snack("Pas de fichier MP4 pour ce titre.")
                    return
                if IS_ANDROID:
                    folder = "/storage/emulated/0/Download/Pere Mehdi"
                else:
                    folder = os.path.join(os.path.expanduser("~"), "Downloads", "Pere Mehdi")
                os.makedirs(folder, exist_ok=True)
                safe = "".join(c for c in item["title"] if c.isalnum() or c in " -_")[:70].strip()
                dest = os.path.join(folder, (safe or item["id"]) + ".mp4")
                snack(f"Téléchargement de « {item['title']} »…")
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, context=CTX, timeout=60) as r, open(dest, "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                snack(f"✅ Enregistré : {dest}")
            except Exception as ex:
                snack(f"❌ Échec du téléchargement : {str(ex)[:120]}")
        threading.Thread(target=work, daemon=True).start()

    def card(item):
        actions = [ft.IconButton(ft.Icons.PLAY_CIRCLE_FILL, icon_color=ft.Colors.AMBER,
                                 tooltip="Regarder", on_click=lambda e, it=item: play(it))]
        if item["kind"] == "archive":
            actions.append(ft.IconButton(ft.Icons.DOWNLOAD, tooltip="Télécharger",
                                         on_click=lambda e, it=item: download(it)))
        return ft.Card(
            content=ft.Container(
                on_click=lambda e, it=item: play(it),
                content=ft.Column([
                    ft.Image(src=item["thumb"], height=150, fit=ft.ImageFit.COVER,
                             border_radius=ft.border_radius.only(top_left=10, top_right=10),
                             error_content=ft.Container(ft.Icon(ft.Icons.MOVIE, size=50),
                                                        alignment=ft.alignment.center)),
                    ft.Container(ft.Text(item["title"], size=12, max_lines=2,
                                         weight=ft.FontWeight.BOLD,
                                         overflow=ft.TextOverflow.ELLIPSIS),
                                 padding=ft.padding.symmetric(horizontal=6)),
                    ft.Container(ft.Text(item["sub"], size=10, color=ft.Colors.GREY_400,
                                         max_lines=1), padding=ft.padding.only(left=6)),
                    ft.Row(actions, alignment=ft.MainAxisAlignment.CENTER, spacing=0),
                ], spacing=2),
            ),
        )

    # ----- chargement
    def load(append=False):
        loader.visible = True
        more_btn.visible = False
        if not append:
            grid.controls.clear()
            state["page"] = 1
        status.value = "Chargement…"
        page.update()

        def work():
            try:
                if state["tab"] == "foot":
                    label, q = state["foot"]
                    if state["query"]:
                        q = state["query"] + " football highlights"
                    items = youtube_search(q, live_only=(label == "Matchs en direct"))
                    if not items and label == "Matchs en direct":
                        status.value = "Aucun match officiel gratuit en direct pour le moment."
                    else:
                        status.value = f"{len(items)} vidéos officielles"
                else:
                    coll = CATEGORIES[state["tab"]][1]
                    items = archive_search(coll, state["query"], state["french"], state["page"])
                    status.value = f"{len(grid.controls) + len(items)} titres"
                    more_btn.visible = len(items) >= 40
                for it in items:
                    grid.controls.append(card(it))
                if not items and not status.value.startswith("Aucun"):
                    status.value = "Aucun résultat."
            except Exception as ex:
                status.value = f"Erreur de connexion : {str(ex)[:150]}"
            loader.visible = False
            page.update()
        threading.Thread(target=work, daemon=True).start()

    def on_more(e):
        state["page"] += 1
        load(append=True)
    more_btn.on_click = on_more

    # ----- barre du haut
    search = ft.TextField(hint_text="Rechercher un titre…", prefix_icon=ft.Icons.SEARCH,
                          dense=True, expand=True, border_radius=25,
                          on_submit=lambda e: (state.update(query=search.value.strip()), load()))
    fr_switch = ft.Switch(label="Français", value=False,
                          on_change=lambda e: (state.update(french=fr_switch.value), load()))

    foot_chips = ft.Row(scroll=ft.ScrollMode.AUTO, visible=False)

    def pick_foot(chip):
        state["foot"] = chip
        state["query"] = ""
        search.value = ""
        for c in foot_chips.controls:
            c.selected = c.data == chip
        load()

    for chip in FOOT_CHIPS:
        foot_chips.controls.append(ft.Chip(label=ft.Text(chip[0]), data=chip,
                                           selected=chip == state["foot"],
                                           on_click=lambda e, c=chip: pick_foot(c)))

    tabs_keys = ["films", "series", "anime", "foot"]

    def on_nav(e):
        state["tab"] = tabs_keys[e.control.selected_index]
        state["query"] = ""
        search.value = ""
        foot = state["tab"] == "foot"
        foot_chips.visible = foot
        fr_switch.visible = not foot
        load()

    nav = ft.NavigationBar(
        selected_index=0, on_change=on_nav,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.MOVIE, label="Films"),
            ft.NavigationBarDestination(icon=ft.Icons.LIVE_TV, label="Séries"),
            ft.NavigationBarDestination(icon=ft.Icons.CHILD_CARE, label="Dessins animés"),
            ft.NavigationBarDestination(icon=ft.Icons.SPORTS_SOCCER, label="Football"),
        ],
    )
    page.navigation_bar = nav

    header = ft.Container(
        padding=ft.padding.only(left=12, right=12, top=30 if IS_ANDROID else 10, bottom=6),
        gradient=ft.LinearGradient(colors=[ft.Colors.BLACK, ft.Colors.BROWN_900]),
        content=ft.Column([
            ft.Row([ft.Icon(ft.Icons.THEATERS, color=ft.Colors.AMBER, size=30),
                    ft.Text(APP, size=22, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.Icon(ft.Icons.VERIFIED_USER, color=ft.Colors.GREEN_400, size=18),
                    ft.Text("100 % légal", size=11, color=ft.Colors.GREEN_400)]),
            ft.Row([search, fr_switch]),
            foot_chips,
        ], spacing=6),
    )

    page.add(ft.Column([
        header, loader,
        ft.Container(status, padding=ft.padding.only(left=12)),
        grid,
        ft.Row([more_btn], alignment=ft.MainAxisAlignment.CENTER),
    ], expand=True, spacing=4))

    load()


if __name__ == "__main__":
    ft.app(target=main)
