"""Regenerate the architecture diagram in docs/.

Writes architecture.svg (editable source) and architecture.png (what the README
embeds, because GitHub renders repo-hosted PNGs unconditionally while SVG and
externally-referenced images in Mermaid are subject to its sanitiser and CSP).

Brand marks come from simple-icons (CC0 icon data; the trademarks remain with
their owners) and are inlined as vector paths rather than raster images, so the
file stays small and sharp at any zoom.

    cd frontend && npm install --no-save simple-icons playwright
    python docs/generate_architecture.py
"""

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ICON_EXPORT = """
const si = require('simple-icons');
const map = {react:'siReact', fastapi:'siFastapi', langchain:'siLangchain',
             huggingface:'siHuggingface', ollama:'siOllama', mistralai:'siMistralai',
             googlegemini:'siGooglegemini', sqlite:'siSqlite', openrouter:'siOpenrouter'};
const out = {};
for (const [k, v] of Object.entries(map)) {
    const i = si[v];
    if (i) out[k] = {title: i.title, hex: i.hex, path: i.path};
}
console.log(JSON.stringify(out));
"""

# Palette chosen to stay legible on both GitHub themes: a light card surface
# with dark text, rather than anything that depends on the page background.
BG = "#ffffff"
CARD = "#f7f8fc"
LANE = "#eef1f8"
LANE_TXT = "#5b6478"
BORDER = "#c9cfe0"
TEXT = "#1f2430"
MUTED = "#5b6478"
ACCENT = "#4f46e5"


def load_icons() -> dict:
    out = subprocess.run(
        ["node", "-e", ICON_EXPORT], cwd=ROOT / "frontend",
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


# Chroma is not in simple-icons, so its mark is carried here verbatim. Unlike
# the simple-icons paths this is multi-colour and drawn on its own coordinate
# system, hence the separate helper below rather than icon().
CHROMA_MARK = (
    '<g transform="matrix(0.86440678,0,0,0.86440678,17.355932,-11.812063)">'
    '<ellipse fill="#ffde2d" cx="170.66679" cy="81.919838" rx="85.333206" ry="81.919838"/>'
    '<ellipse fill="#327eff" cx="85.333206" cy="81.919838" rx="85.333206" ry="81.919838"/>'
    '<path d="m 170.66679,81.919964 c 0,45.243426 -38.20536,81.919196 -85.333713,81.919196 '
    'V 81.919964 Z M 85.333205,81.919836 C 85.333205,36.676791 123.53819,8.9599821e-5 '
    '170.66679,8.9599821e-5 V 81.919836 Z" fill="#ff6446"/>'
    "</g>"
)
CHROMA_VIEWBOX = (17.355932, -11.812063, 221.29, 141.62)


def chroma_mark(x: float, y: float, width: float) -> str:
    """The Chroma mark scaled to `width`, its own viewBox origin shifted to (x, y).

    It is wider than it is tall (roughly 1.56:1), so only the width is given and
    the height follows; forcing it into a square icon slot would distort it.
    """
    vx, vy, vw, _vh = CHROMA_VIEWBOX
    s = width / vw
    return (
        f'<g transform="translate({x},{y}) scale({s}) translate({-vx},{-vy})">'
        f"{CHROMA_MARK}</g>"
    )


def icon(icons: dict, name: str, x: float, y: float, size: float) -> str:
    """A brand mark scaled into `size` at (x, y). simple-icons paths are on a
    24x24 grid, so everything is one uniform scale factor."""
    ico = icons.get(name)
    if not ico:
        return ""
    s = size / 24
    return (
        f'<g transform="translate({x},{y}) scale({s})">'
        f'<path d="{ico["path"]}" fill="#{ico["hex"]}"/></g>'
    )


def card(x, y, w, h, title, subtitle="", icons_svg="", rx=12) -> str:
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
        f'fill="{CARD}" stroke="{BORDER}" stroke-width="1.4"/>',
        icons_svg,
    ]
    ty = y + (h / 2 + 5 if not subtitle else h / 2 - 4)
    parts.append(
        f'<text x="{x + w / 2}" y="{ty}" text-anchor="middle" fill="{TEXT}" '
        f'font-family="Inter,Segoe UI,Helvetica,Arial,sans-serif" font-size="15" '
        f'font-weight="650">{title}</text>'
    )
    if subtitle:
        for i, line in enumerate(subtitle.split("\n")):
            parts.append(
                f'<text x="{x + w / 2}" y="{y + h / 2 + 15 + i * 15}" text-anchor="middle" '
                f'fill="{MUTED}" font-family="Inter,Segoe UI,Helvetica,Arial,sans-serif" '
                f'font-size="12.5">{line}</text>'
            )
    return "".join(parts)


def lane(x, y, w, h, label) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{LANE}"/>'
        f'<text x="{x + 16}" y="{y + 21}" fill="{LANE_TXT}" font-size="11.5" font-weight="700" '
        f'letter-spacing="1.4" font-family="Inter,Segoe UI,Helvetica,Arial,sans-serif">'
        f'{label.upper()}</text>'
    )


def arrow(x1, y1, x2, y2, label="", dashed=False, curve=0) -> str:
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    if curve:
        d = f"M{x1},{y1} C{x1 + curve},{y1} {x2 - curve},{y2} {x2},{y2}"
    else:
        d = f"M{x1},{y1} L{x2},{y2}"
    out = (
        f'<path d="{d}" fill="none" stroke="{ACCENT}" stroke-width="1.8" '
        f'marker-end="url(#arw)"{dash}/>'
    )
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        w = len(label) * 6.4 + 12
        out += (
            f'<rect x="{mx - w / 2}" y="{my - 10}" width="{w}" height="18" rx="9" '
            f'fill="{BG}" stroke="{BORDER}" stroke-width="1"/>'
            f'<text x="{mx}" y="{my + 3}" text-anchor="middle" fill="{MUTED}" font-size="11.5" '
            f'font-family="Inter,Segoe UI,Helvetica,Arial,sans-serif">{label}</text>'
        )
    return out


def build(icons: dict) -> str:
    W, H = 1180, 826
    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        f'<defs><marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        f'markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{ACCENT}"/></marker></defs>',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        f'<text x="40" y="46" fill="{TEXT}" font-size="21" font-weight="700" '
        f'font-family="Inter,Segoe UI,Helvetica,Arial,sans-serif">AEDS RAG - architecture</text>',
        f'<text x="40" y="68" fill="{MUTED}" font-size="13" '
        f'font-family="Inter,Segoe UI,Helvetica,Arial,sans-serif">'
        f'Chroma for semantic similarity, SQLite for facts that must be exact, '
        f'a checkpointer for conversation state.</text>',
    ]

    # --- client -------------------------------------------------------------
    p.append(lane(40, 92, 1100, 92, "Browser"))
    p.append(card(56, 116, 300, 56, "React UI",
                  "chat  ·  admin panel",
                  icon(icons, "react", 74, 130, 26)))
    p.append(f'<text x="392" y="140" fill="{MUTED}" font-size="12.5" '
             f'font-family="Inter,Segoe UI,Helvetica,Arial,sans-serif">'
             f'Every visitor gets their own anonymous session identity,</text>')
    p.append(f'<text x="392" y="158" fill="{MUTED}" font-size="12.5" '
             f'font-family="Inter,Segoe UI,Helvetica,Arial,sans-serif">'
             f'so threads, history and rate limits stay separate without anyone signing up.</text>')

    # --- api ----------------------------------------------------------------
    # /admin sits under FastAPI rather than in line with the chat path: it is a
    # separate branch off the same app, not a stage the chat request passes
    # through, and a single left-to-right row of arrows implied otherwise.
    p.append(lane(40, 204, 1100, 182, "API"))
    p.append(card(56, 230, 300, 66, "FastAPI",
                  "auth · rate limit · daily LLM budget",
                  icon(icons, "fastapi", 74, 248, 26)))
    p.append(card(430, 230, 300, 66, "POST /chat/stream", "server-sent events"))
    p.append(card(804, 230, 320, 66, "Semantic cache",
                  "exact match, then cosine ≥ 0.94\nhit → answer returned without the pipeline"))
    p.append(card(56, 316, 300, 56, "/admin",
                  "documents · review · users · config"))

    # --- pipeline -----------------------------------------------------------
    p.append(lane(40, 406, 1100, 110, "LangGraph pipeline  ·  state in a SQLite checkpointer"))
    p.append(icon(icons, "langchain", 1090, 424, 26))
    p.append(card(76, 436, 280, 62, "retrieve", "route → search → rerank → gate"))
    p.append(card(436, 436, 280, 62, "generate", "grounded in retrieved context"))
    p.append(card(796, 436, 280, 62, "detect_contribution", "flags asserted facts for review (Laya)"))
    p.append(arrow(356, 467, 430, 467))
    p.append(arrow(716, 467, 790, 467))

    # --- models -------------------------------------------------------------
    p.append(lane(40, 536, 540, 250, "Models"))
    p.append(card(56, 566, 508, 62, "bge-large-en-v1.5",
                  "embeddings · 1024-dim · runs locally",
                  icon(icons, "huggingface", 74, 584, 26)))
    p.append(card(56, 640, 508, 62, "bge-reranker-base",
                  "cross-encoder · top 10 → top 4",
                  icon(icons, "huggingface", 74, 658, 26)))
    p.append(card(56, 714, 161, 58, "ministral-3:3b",
                  "default · local",
                  icon(icons, "ollama", 64, 731, 17)))
    p.append(card(229, 714, 161, 58, "gemini-3.1-flash-lite",
                  "cloud",
                  icon(icons, "googlegemini", 245, 730, 20)))
    p.append(card(402, 714, 161, 58, "OpenRouter",
                  "cloud · auto-fallback",
                  icon(icons, "openrouter", 418, 730, 20)))

    # --- storage ------------------------------------------------------------
    p.append(lane(600, 536, 540, 250, "Storage"))
    p.append(card(616, 566, 508, 62, "Chroma", "approved_chunks · vector + BM25 hybrid",
                  chroma_mark(634, 586, 34)))
    p.append(card(616, 640, 508, 62, "SQLite  app.db",
                  "courses · deadlines · users · submissions · query_log",
                  icon(icons, "sqlite", 634, 658, 26)))
    p.append(card(616, 714, 508, 58, "SQLite  checkpoints.db",
                  "conversation state per thread",
                  icon(icons, "sqlite", 634, 730, 26)))

    # --- flow ---------------------------------------------------------------
    p.append(arrow(206, 172, 206, 226))                      # UI -> FastAPI
    p.append(arrow(356, 263, 426, 263))                      # FastAPI -> /chat/stream
    p.append(arrow(730, 263, 800, 263))                      # /chat/stream -> cache
    p.append(arrow(206, 296, 206, 312))                      # FastAPI -> /admin (branch)
    p.append(arrow(964, 296, 964, 404, "miss"))              # cache -> pipeline
    p.append(arrow(216, 498, 216, 532))                      # retrieve -> models
    p.append(arrow(936, 498, 936, 532))                      # detect -> storage

    p.append(f'<text x="40" y="{H - 18}" fill="{MUTED}" font-size="11.5" '
             f'font-family="Inter,Segoe UI,Helvetica,Arial,sans-serif">'
             f'Generated by docs/generate_architecture.py  ·  brand marks from simple-icons (CC0)'
             f'</text>')
    p.append("</svg>")
    return "\n".join(p)


def rasterise(svg_path: pathlib.Path, png_path: pathlib.Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900},
                                device_scale_factor=2)
        page.goto(svg_path.as_uri())
        page.wait_for_timeout(400)
        page.locator("svg").screenshot(path=str(png_path))
        browser.close()


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    svg = build(load_icons())
    svg_path = DOCS / "architecture.svg"
    svg_path.write_text(svg)
    rasterise(svg_path, DOCS / "architecture.png")
    print(f"wrote {svg_path.relative_to(ROOT)} and docs/architecture.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
