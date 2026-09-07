import json
import re
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape

OWNER = "hehonghui"
REPO = "awesome-english-ebooks"
BRANCH = "master"

SOURCES = [
    {
        "name": "The Economist",
        "path": "01_economist",
        "pattern": r"\.epub$",
    },
    {
        "name": "The New Yorker",
        "path": "02_new_yorker",
        "pattern": r"\.epub$",
    },
]


def github_tree():
    url = (
        f"https://api.github.com/repos/{OWNER}/{REPO}"
        f"/git/trees/{BRANCH}?recursive=1"
    )

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "x3-opds-generator",
            "Accept": "application/vnd.github+json",
        },
    )

    with urllib.request.urlopen(req) as response:
        return json.load(response)["tree"]


def extract_date(path):
    matches = re.findall(r"20\d{2}[._-]\d{2}[._-]\d{2}", path)

    if not matches:
        return None

    date_text = matches[-1].replace("_", ".").replace("-", ".")

    try:
        return datetime.strptime(date_text, "%Y.%m.%d")
    except ValueError:
        return None


def newest_epub(tree, source):
    candidates = []

    for item in tree:
        path = item.get("path", "")

        if item.get("type") != "blob":
            continue

        if not path.startswith(source["path"] + "/"):
            continue

        if not re.search(source["pattern"], path, re.IGNORECASE):
            continue

        date = extract_date(path)

        if date:
            candidates.append((date, path))

    if not candidates:
        return None

    candidates.sort(reverse=True)

    return candidates[0]


def raw_url(path):
    return (
        f"https://raw.githubusercontent.com/"
        f"{OWNER}/{REPO}/{BRANCH}/{path}"
    )


def make_feed(entries):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom"',
        '      xmlns:opds="http://opds-spec.org/2010/catalog">',
        "",
        "  <id>urn:x3:newspapers</id>",
        "  <title>X3 Newspapers</title>",
        f"  <updated>{now}</updated>",
        "",
    ]

    for source_name, date, path in entries:
        pretty_date = date.strftime("%d %B %Y")
        download_url = raw_url(path)

        entry_id = (
            source_name.lower()
            .replace(" ", "-")
            .replace("the-", "")
        )

        parts.extend(
            [
                "  <entry>",
                f"    <title>{escape(source_name)} — {pretty_date}</title>",
                f"    <id>urn:x3:{entry_id}:{date.strftime('%Y-%m-%d')}</id>",
                f"    <updated>{date.strftime('%Y-%m-%d')}T00:00:00Z</updated>",
                "    <author>",
                f"      <name>{escape(source_name)}</name>",
                "    </author>",
                f'    <summary type="text">{escape(source_name)} — {pretty_date}</summary>',
                "    <link",
                '      rel="http://opds-spec.org/acquisition/open-access"',
                f'      href="{escape(download_url)}"',
                '      type="application/epub+zip" />',
                "  </entry>",
                "",
            ]
        )

    parts.append("</feed>")

    return "\n".join(parts)


def main():
    tree = github_tree()

    entries = []

    for source in SOURCES:
        result = newest_epub(tree, source)

        if result:
            date, path = result
            print(f"{source['name']}: {path}")
            entries.append((source["name"], date, path))
        else:
            print(f"No EPUB found for {source['name']}")

    feed = make_feed(entries)

    with open("index.xml", "w", encoding="utf-8") as f:
        f.write(feed)


if __name__ == "__main__":
    main()
