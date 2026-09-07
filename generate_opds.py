import os
import re
import json
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape

OWNER = "hehonghui"
REPO = "awesome-english-ebooks"
BRANCH = "master"

# Automatically gets YOUR GitHub username when running in Actions.
MY_GITHUB_USER = os.environ.get("GITHUB_REPOSITORY_OWNER", "3lastico")
MY_REPO = "x3-opds"

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
    matches = re.findall(
        r"20\d{2}[._-]\d{2}[._-]\d{2}",
        path
    )

    if not matches:
        return None

    date_text = (
        matches[-1]
        .replace("_", ".")
        .replace("-", ".")
    )

    try:
        return datetime.strptime(
            date_text,
            "%Y.%m.%d"
        )
    except ValueError:
        return None


def newest_epub(tree, source):
    candidates = []

    for item in tree:
        path = item.get("path", "")

        if item.get("type") != "blob":
            continue

        if not path.startswith(
            source["path"] + "/"
        ):
            continue

        if not re.search(
            source["pattern"],
            path,
            re.IGNORECASE
        ):
            continue

        date = extract_date(path)

        if date:
            candidates.append(
                (date, path)
            )

    if not candidates:
        return None

    candidates.sort(reverse=True)

    return candidates[0]


def raw_url(path):
    return (
        f"https://raw.githubusercontent.com/"
        f"{OWNER}/{REPO}/{BRANCH}/{path}"
    )


def daily_briefs():
    folder = "books/daily"

    if not os.path.isdir(folder):
        return []

    results = []

    for filename in os.listdir(folder):

        if not filename.endswith(".epub"):
            continue

        date = extract_date(filename)

        if not date:
            continue

        url = (
            f"https://{MY_GITHUB_USER}.github.io/"
            f"{MY_REPO}/books/daily/{filename}"
        )

        results.append(
            (date, filename, url)
        )

    results.sort(reverse=True)

    return results[:7]


def add_entry(
    parts,
    title,
    entry_id,
    date,
    url,
    author
):
    pretty_date = date.strftime(
        "%d %B %Y"
    )

    parts.extend(
        [
            "  <entry>",
            f"    <title>{escape(title)}</title>",
            f"    <id>{escape(entry_id)}</id>",
            (
                "    <updated>"
                f"{date.strftime('%Y-%m-%d')}"
                "T00:00:00Z</updated>"
            ),
            "    <author>",
            f"      <name>{escape(author)}</name>",
            "    </author>",
            (
                '    <summary type="text">'
                f"{escape(title)}"
                "</summary>"
            ),
            "    <link",
            (
                '      rel="http://opds-spec.org/'
                'acquisition/open-access"'
            ),
            f'      href="{escape(url)}"',
            '      type="application/epub+zip" />',
            "  </entry>",
            "",
        ]
    )


def make_feed(magazines, briefs):
    now = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    self_url = (
        f"https://{MY_GITHUB_USER}.github.io/"
        f"{MY_REPO}/index.xml"
    )

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            '<feed xmlns="http://www.w3.org/2005/Atom" '
            'xmlns:opds="http://opds-spec.org/2010/catalog">'
        ),
        "",
        "  <id>urn:x3:library</id>",
        "  <title>X3 Library</title>",
        f"  <updated>{now}</updated>",
        "",
        "  <link",
        '    rel="self"',
        f'    href="{escape(self_url)}"',
        (
            '    type="application/atom+xml;'
            'profile=opds-catalog;kind=acquisition" />'
        ),
        "",
    ]

    # Daily Briefs first
    for date, filename, url in briefs:

        pretty_date = date.strftime(
            "%d %B %Y"
        )

        title = (
            f"Daily Brief — {pretty_date}"
        )

        add_entry(
            parts,
            title,
            (
                "urn:x3:daily:"
                f"{date.strftime('%Y-%m-%d')}"
            ),
            date,
            url,
            "X3 Daily Brief",
        )

    # Then newest magazine issues
    for source_name, date, path in magazines:

        pretty_date = date.strftime(
            "%d %B %Y"
        )

        title = (
            f"{source_name} — {pretty_date}"
        )

        entry_id = (
            source_name.lower()
            .replace(" ", "-")
            .replace("the-", "")
        )

        add_entry(
            parts,
            title,
            (
                f"urn:x3:{entry_id}:"
                f"{date.strftime('%Y-%m-%d')}"
            ),
            date,
            raw_url(path),
            source_name,
        )

    parts.append("</feed>")

    return "\n".join(parts)


def main():
    tree = github_tree()

    magazines = []

    for source in SOURCES:
        result = newest_epub(
            tree,
            source
        )

        if result:
            date, path = result

            print(
                f"{source['name']}: {path}"
            )

            magazines.append(
                (
                    source["name"],
                    date,
                    path
                )
            )

    briefs = daily_briefs()

    print(
        f"Daily Briefs found: {len(briefs)}"
    )

    feed = make_feed(
        magazines,
        briefs
    )

    with open(
        "index.xml",
        "w",
        encoding="utf-8"
    ) as f:
        f.write(feed)

    print("Generated index.xml")


if __name__ == "__main__":
    main()
