"""Render docs/PLAN.md as a self-contained docs/plan.html.

The markdown is the single source; this only converts it, so the two cannot
drift. Supports exactly the constructs PLAN.md uses: headings, tables,
unordered lists, fenced code, blockquotes, bold, inline code and links.

The one Mermaid diagram is drawn as inline SVG here, because the page has to
work offline with no CDN. GitHub renders the Mermaid source in PLAN.md itself.

Usage:
    python3 build/render_plan.py
"""

from __future__ import annotations

import html
import os
import re
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOURCE = os.path.join(ROOT, "docs", "PLAN.md")
OUTPUT = os.path.join(ROOT, "docs", "plan.html")

REPORT_URL = "https://danhamilt.github.io/prediction-markets-report/"


def code_spans(text: str) -> str:
    """Escape text, converting any backtick spans to <code>.

    Used for the inside of bold, where a span like a qualified table name can
    sit inside the emphasis.
    """
    parts = re.split(r"(`[^`]+`)", text)
    out: list[str] = []
    for part in parts:
        if len(part) > 2 and part.startswith("`") and part.endswith("`"):
            out.append(f"<code>{html.escape(part[1:-1])}</code>")
        else:
            out.append(html.escape(part))
    return "".join(out)


def inline(text: str) -> str:
    """Inline markdown: code spans, bold, then links.

    Bold is matched non-greedily so it can contain an asterisk, which matters
    for text like a qualified table name.
    """
    out: list[str] = []
    pattern = re.compile(
        r"(`[^`]+`)"
        r"|(\*\*.+?\*\*)"
        r"|(\[[^\]]+\]\([^)]+\))"
    )
    position = 0
    for match in pattern.finditer(text):
        out.append(html.escape(text[position : match.start()]))
        chunk = match.group(0)
        if chunk.startswith("`"):
            out.append(f"<code>{html.escape(chunk[1:-1])}</code>")
        elif chunk.startswith("**"):
            out.append(f"<strong>{code_spans(chunk[2:-2])}</strong>")
        else:
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", chunk).groups()  # type: ignore[union-attr]
            external = url.startswith("http")
            target = ' target="_blank" rel="noopener"' if external else ""
            out.append(
                f'<a href="{html.escape(url)}"{target}>'
                f"{html.escape(label)}</a>"
            )
        position = match.end()
    out.append(html.escape(text[position:]))
    return "".join(out)


def is_block_start(line: str) -> bool:
    """True when a line begins a new block rather than continuing one."""
    stripped = line.strip()
    if not stripped:
        return True
    return stripped.startswith(("#", "|", "- ", ">", "```")) or stripped == "---"


NUMBERED = re.compile(r"^\d+\.\s+(.*)$")


DIAGRAM_SVG = """<figure class="diagram">
<svg viewBox="0 0 900 300" role="img"
     aria-label="kaz-socket sits between providers and consumers">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" class="arrowhead"></path>
    </marker>
  </defs>

  <rect x="8" y="20" width="196" height="260" rx="12" class="box-zone"></rect>
  <text x="106" y="44" class="zone-label" text-anchor="middle">PROVIDERS</text>
  <rect x="28" y="62" width="156" height="40" rx="8" class="box"></rect>
  <text x="106" y="87" class="box-text" text-anchor="middle">Kalshi REST</text>
  <rect x="28" y="116" width="156" height="40" rx="8" class="box-dashed"></rect>
  <text x="106" y="141" class="box-text" text-anchor="middle">Kalshi WS (keyed)</text>
  <rect x="28" y="170" width="156" height="40" rx="8" class="box"></rect>
  <text x="106" y="195" class="box-text" text-anchor="middle">Polymarket WS</text>

  <rect x="252" y="20" width="380" height="260" rx="12" class="box-zone"></rect>
  <text x="442" y="44" class="zone-label" text-anchor="middle">KAZ-SOCKET (ALWAYS-ON)</text>
  <rect x="272" y="62" width="340" height="44" rx="8" class="box"></rect>
  <text x="442" y="82" class="box-text" text-anchor="middle">SourceAdapter</text>
  <text x="442" y="97" class="box-sub" text-anchor="middle">normalise to cents</text>
  <rect x="272" y="122" width="340" height="52" rx="8" class="box-accent"></rect>
  <text x="442" y="144" class="box-text" text-anchor="middle">live_price + change_log</text>
  <text x="442" y="160" class="box-sub" text-anchor="middle">TTL cache, bounded log</text>
  <rect x="272" y="190" width="340" height="44" rx="8" class="box"></rect>
  <text x="442" y="210" class="box-text" text-anchor="middle">fanout</text>
  <text x="442" y="225" class="box-sub" text-anchor="middle">rooms, seq, TTL</text>

  <rect x="680" y="20" width="212" height="260" rx="12" class="box-zone"></rect>
  <text x="786" y="44" class="zone-label" text-anchor="middle">CONSUMERS</text>
  <rect x="698" y="62" width="176" height="44" rx="8" class="box"></rect>
  <text x="786" y="82" class="box-text" text-anchor="middle">Browsers</text>
  <text x="786" y="97" class="box-sub" text-anchor="middle">ws ?since=seq</text>
  <rect x="698" y="122" width="176" height="44" rx="8" class="box"></rect>
  <text x="786" y="142" class="box-text" text-anchor="middle">bet105-skin</text>
  <text x="786" y="157" class="box-sub" text-anchor="middle">GET snapshot</text>
  <rect x="698" y="182" width="176" height="44" rx="8" class="box"></rect>
  <text x="786" y="202" class="box-text" text-anchor="middle">kaz-control</text>
  <text x="786" y="217" class="box-sub" text-anchor="middle">socket.outbox</text>

  <line x1="204" y1="82" x2="268" y2="84" class="edge" marker-end="url(#arrow)"></line>
  <line x1="204" y1="136" x2="268" y2="136" class="edge-dashed" marker-end="url(#arrow)"></line>
  <line x1="204" y1="190" x2="268" y2="140" class="edge" marker-end="url(#arrow)"></line>
  <line x1="442" y1="106" x2="442" y2="118" class="edge" marker-end="url(#arrow)"></line>
  <line x1="442" y1="174" x2="442" y2="186" class="edge" marker-end="url(#arrow)"></line>
  <line x1="612" y1="200" x2="694" y2="86" class="edge" marker-end="url(#arrow)"></line>
  <line x1="612" y1="212" x2="694" y2="144" class="edge" marker-end="url(#arrow)"></line>
  <line x1="612" y1="224" x2="694" y2="204" class="edge" marker-end="url(#arrow)"></line>
</svg>
<figcaption>The two-repo boundary. kaz-socket holds every upstream
connection; consumers read from it and never open a provider socket.</figcaption>
</figure>"""


def convert(markdown: str) -> str:
    lines = markdown.split("\n")
    out: list[str] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]

        # fenced code
        if line.startswith("```"):
            language = line[3:].strip()
            index += 1
            block: list[str] = []
            while index < total and not lines[index].startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            if language == "mermaid":
                out.append(DIAGRAM_SVG)
                continue
            body = html.escape("\n".join(block))
            label = (
                f'<div class="code-label">{html.escape(language)}</div>'
                if language
                else ""
            )
            out.append(
                f'<div class="code">{label}<pre><code>{body}</code></pre></div>'
            )
            continue

        # table
        if line.startswith("|") and index + 1 < total and set(
            lines[index + 1].replace("|", "").replace(" ", "")
        ) <= set("-:"):
            header = [cell.strip() for cell in line.strip("|").split("|")]
            index += 2
            rows: list[list[str]] = []
            while index < total and lines[index].startswith("|"):
                rows.append(
                    [cell.strip() for cell in lines[index].strip("|").split("|")]
                )
                index += 1
            head = "".join(f"<th>{inline(cell)}</th>" for cell in header)
            body = "".join(
                "<tr>"
                + "".join(f"<td>{inline(cell)}</td>" for cell in row)
                + "</tr>"
                for row in rows
            )
            out.append(
                '<div class="table-wrap"><table>'
                f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
            )
            continue

        # headings
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2)
            anchor = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
            out.append(
                f'<h{level} id="{anchor}">{inline(text)}</h{level}>'
            )
            index += 1
            continue

        # horizontal rule
        if line.strip() == "---":
            out.append("<hr>")
            index += 1
            continue

        # unordered list, with wrapped continuation lines joined in
        if line.startswith("- "):
            items: list[str] = []
            current = line[2:]
            index += 1
            while index < total:
                following = lines[index]
                if following.startswith("- "):
                    items.append(current)
                    current = following[2:]
                    index += 1
                elif not is_block_start(following):
                    current = f"{current} {following.strip()}"
                    index += 1
                else:
                    break
            items.append(current)
            body = "".join(f"<li>{inline(item)}</li>" for item in items)
            out.append(f"<ul>{body}</ul>")
            continue

        # ordered list, same continuation handling
        numbered = NUMBERED.match(line)
        if numbered:
            items = []
            current = numbered.group(1)
            index += 1
            while index < total:
                following = lines[index]
                step = NUMBERED.match(following)
                if step:
                    items.append(current)
                    current = step.group(1)
                    index += 1
                elif not is_block_start(following):
                    current = f"{current} {following.strip()}"
                    index += 1
                else:
                    break
            items.append(current)
            body = "".join(f"<li>{inline(item)}</li>" for item in items)
            out.append(f"<ol>{body}</ol>")
            continue

        # blockquote
        if line.startswith(">"):
            quoted: list[str] = []
            while index < total and lines[index].startswith(">"):
                quoted.append(lines[index].lstrip(">").strip())
                index += 1
            out.append(
                f'<blockquote>{inline(" ".join(quoted))}</blockquote>'
            )
            continue

        # blank
        if not line.strip():
            index += 1
            continue

        # paragraph
        paragraph: list[str] = []
        while (
            index < total
            and lines[index].strip()
            and not lines[index].startswith(("#", "|", "- ", ">", "```"))
            and lines[index].strip() != "---"
        ):
            paragraph.append(lines[index].strip())
            index += 1
        out.append(f"<p>{inline(' '.join(paragraph))}</p>")

    return "\n".join(out)


STYLES = """
:root {
  --bg:#0c0f14; --panel:#141922; --panel-2:#1b212c; --line:#262e3b;
  --ink:#e8edf5; --ink-dim:#9aa6b8; --ink-faint:#6b7688;
  --accent:#5b9dff; --accent-2:#38d39f;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
* { box-sizing:border-box; }
body {
  margin:0; background:var(--bg); color:var(--ink);
  font-family:var(--sans); font-size:16px; line-height:1.65;
  -webkit-font-smoothing:antialiased;
}
.wrap { max-width:920px; margin:0 auto; padding:0 28px 96px; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
code {
  font-family:var(--mono); font-size:0.86em; background:var(--panel-2);
  border:1px solid var(--line); border-radius:4px; padding:0.08em 0.36em;
  color:#cfe0ff; word-break:break-word;
}
h1,h2,h3,h4 { line-height:1.25; margin:0 0 0.5em; letter-spacing:-0.01em; }
h1 { font-size:2.1rem; letter-spacing:-0.03em; margin-top:2.6rem; }
h2 { font-size:1.5rem; margin-top:2.8rem; padding-top:1.6rem; border-top:1px solid var(--line); }
h3 { font-size:1.14rem; margin-top:2rem; }
h4 { font-size:1rem; margin-top:1.6rem; color:var(--ink-dim); }
p { margin:0 0 1rem; }
ul { margin:0 0 1.2rem; padding-left:1.3rem; }
li { margin-bottom:0.4rem; }
hr { border:0; border-top:1px solid var(--line); margin:2.4rem 0; }
blockquote {
  margin:1.2rem 0; padding:0.2rem 0 0.2rem 1rem;
  border-left:2px solid var(--accent-2); color:var(--ink-dim); font-style:italic;
}
header.hero { padding:56px 0 8px; }
.eyebrow {
  text-transform:uppercase; letter-spacing:0.18em; font-size:0.72rem;
  color:var(--accent-2); margin:0 0 0.6rem;
}
header.hero p.sub { color:var(--ink-dim); font-size:1.06rem; max-width:70ch; }
.backlink {
  display:inline-block; margin-top:0.4rem; font-family:var(--mono); font-size:0.84rem;
}
.table-wrap {
  overflow-x:auto; border:1px solid var(--line); border-radius:10px;
  margin:1.1rem 0 1.6rem; background:var(--panel);
}
table { width:100%; border-collapse:collapse; font-size:0.9rem; }
th {
  text-align:left; padding:11px 14px; background:var(--panel-2);
  color:var(--ink-dim); font-weight:600; font-size:0.71rem;
  text-transform:uppercase; letter-spacing:0.08em;
  border-bottom:1px solid var(--line); white-space:nowrap;
}
td { padding:11px 14px; border-bottom:1px solid var(--line); vertical-align:top; }
tr:last-child td { border-bottom:0; }
tbody tr:hover { background:rgba(91,157,255,0.045); }
.code {
  border:1px solid var(--line); border-radius:10px; background:#0a0d12;
  margin:0.9rem 0 1.5rem; overflow:hidden;
}
.code-label {
  font-family:var(--mono); font-size:0.71rem; color:var(--ink-faint);
  padding:8px 14px; border-bottom:1px solid var(--line); background:var(--panel);
  text-transform:uppercase; letter-spacing:0.08em;
}
.code pre {
  margin:0; padding:15px 16px; overflow-x:auto; font-family:var(--mono);
  font-size:0.79rem; line-height:1.6; color:#b9c9e3;
}
.code pre code { background:none; border:0; padding:0; color:inherit; }
figure.diagram {
  margin:1.4rem 0 1.8rem; background:var(--panel); border:1px solid var(--line);
  border-radius:12px; padding:16px;
}
figure.diagram svg { width:100%; height:auto; display:block; }
figure.diagram figcaption {
  color:var(--ink-dim); font-size:0.84rem; margin-top:10px; font-family:var(--mono);
}
.box, .box-dashed, .box-accent { stroke:#3a4658; stroke-width:1; fill:#1b212c; }
.box-dashed { fill:#161b24; stroke-dasharray:4 3; }
.box-accent { fill:rgba(91,157,255,0.14); stroke:#5b9dff; }
.box-zone { fill:rgba(255,255,255,0.02); stroke:#2c3444; stroke-width:1; }
.box-text { fill:#e8edf5; font-size:12px; font-family:var(--mono); }
.box-sub { fill:#8b97a9; font-size:10px; font-family:var(--mono); }
.zone-label { fill:#6b7688; font-size:10px; font-family:var(--mono); letter-spacing:0.12em; }
.edge { stroke:#5b9dff; stroke-width:1.4; fill:none; }
.edge-dashed { stroke:#5b9dff; stroke-width:1.4; fill:none; stroke-dasharray:4 3; opacity:0.65; }
.arrowhead { fill:#5b9dff; }
footer {
  padding:36px 0 72px; color:var(--ink-faint); font-size:0.85rem;
  border-top:1px solid var(--line); margin-top:3rem;
}
@media (max-width:700px){ .wrap{padding:0 18px 64px;} }
"""


def main() -> None:
    with open(SOURCE, encoding="utf-8") as handle:
        markdown = handle.read()

    body = convert(markdown)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>kaz-socket &mdash; architecture, cost model and the US election slice</title>
<meta name="description" content="The kaz-socket architecture plan: the two-repo boundary, the scope decision, measured feed costs, a live cache with TTL priced against a straight relay, and the US election slice.">
<meta name="color-scheme" content="dark">
<style>{STYLES}</style>
</head>
<body>
<div class="wrap">
<header class="hero">
  <p class="eyebrow">Architecture plan</p>
  <p class="sub">The service design and cost model for a prediction-market feed
  edge, built on the measured API survey.</p>
  <a class="backlink" href="{REPORT_URL}">Back to the API survey</a>
</header>
{body}
<footer>
  <p>Generated {html.escape(generated)} from <code>docs/PLAN.md</code>, which
  is the source of this page. Every figure marked measured was taken from an
  anonymous public endpoint.</p>
</footer>
</div>
</body>
</html>
"""

    with open(OUTPUT, "w", encoding="utf-8") as handle:
        handle.write(document)
    print(f"wrote {OUTPUT} ({len(document):,} bytes)")


if __name__ == "__main__":
    main()
