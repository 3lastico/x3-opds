import re
import os
import html
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import feedparser
from bs4 import BeautifulSoup
from ebooklib import epub


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

MAX_AGE_HOURS = 30

SECTIONS = {
    "Germany": [
        {
            "source": "Tagesschau",
            "url": "https://www.tagesschau.de/xml/rss2",
            "limit": 5,
        },
        {
            "source": "Deutschlandfunk",
            "url": "https://www.deutschlandfunk.de/nachrichten-100.rss",
            "limit": 4,
        },
        {
            "source": "DW",
            "url": "https://rss.dw.com/syndication/feeds/VAS_CB_Eng_OurVoice.31791-cb.html",
            "limit": 3,
        },
    ],

    "Europe": [
        {
            "source": "Deutschlandfunk Europa",
            "url": "https://www.deutschlandfunk.de/europa-112.rss",
            "limit": 3,
        },
        {
            "source": "BBC",
            "url": "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
            "limit": 4,
        },
    ],

    "World": [
        {
            "source": "BBC",
            "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
            "limit": 5,
        },
        {
            "source": "The Guardian",
            "url": "https://www.theguardian.com/world/rss",
            "limit": 4,
        },
        {
            "source": "NPR",
            "url": "https://feeds.npr.org/1004/rss.xml",
            "limit": 4,
        },
    ],

    "Business": [
        {
            "source": "Deutschlandfunk Wirtschaft",
            "url": "https://www.deutschlandfunk.de/wirtschaft-106.rss",
            "limit": 3,
        },
        {
            "source": "BBC Business",
            "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
            "limit": 3,
        },
    ],

    "Science & Technology": [
        {
            "source": "Deutschlandfunk Wissen",
            "url": "https://www.deutschlandfunk.de/wissen-106.rss",
            "limit": 3,
        },
        {
            "source": "BBC",
            "url": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
            "limit": 3,
        },
        {
            "source": "Ars Technica",
            "url": "https://feeds.arstechnica.com/arstechnica/index",
            "limit": 3,
        },
    ],
}


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def clean_html(text):
    if not text:
        return ""

    soup = BeautifulSoup(text, "html.parser")

    # Remove images / embedded stuff
    for tag in soup(["img", "video", "audio", "iframe", "script", "style"]):
        tag.decompose()

    text = soup.get_text("\n")

    text = html.unescape(text)

    lines = []

    for line in text.splitlines():
        line = line.strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


def get_date(entry):
    for field in ("published_parsed", "updated_parsed"):
        value = entry.get(field)

        if value:
            return datetime(
                *value[:6],
                tzinfo=timezone.utc
            )

    for field in ("published", "updated"):
        value = entry.get(field)

        if value:
            try:
                parsed = parsedate_to_datetime(value)

                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)

                return parsed.astimezone(timezone.utc)

            except Exception:
                pass

    return None


def is_recent(entry):
    published = get_date(entry)

    if not published:
        # Don't throw away an otherwise valid item solely
        # because the publisher omitted a date.
        return True

    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=MAX_AGE_HOURS
    )

    return published >= cutoff


def normalize_title(title):
    title = title.lower()

    title = re.sub(r"[^\w\s]", "", title)

    words = title.split()

    # First several significant words are enough for basic
    # duplicate detection.
    return " ".join(words[:9])


def get_description(entry):
    candidates = []

    if entry.get("content"):
        for item in entry.content:
            value = item.get("value")

            if value:
                candidates.append(value)

    if entry.get("summary"):
        candidates.append(entry.summary)

    if entry.get("description"):
        candidates.append(entry.description)

    if not candidates:
        return ""

    # Prefer the longest content the feed itself supplies.
    candidates.sort(
        key=lambda value: len(clean_html(value)),
        reverse=True
    )

    return clean_html(candidates[0])


# ---------------------------------------------------------
# READ FEEDS
# ---------------------------------------------------------

def fetch_section(feeds, seen_titles):
    articles = []

    for feed_config in feeds:

        source = feed_config["source"]
        url = feed_config["url"]
        limit = feed_config["limit"]

        print(f"Fetching {source}")

        feed = feedparser.parse(url)

        if feed.bozo:
            print(
                f"Warning: possible feed issue for "
                f"{source}: {feed.bozo_exception}"
            )

        source_count = 0

        for entry in feed.entries:

            if source_count >= limit:
                break

            if not is_recent(entry):
                continue

            title = clean_html(
                entry.get("title", "")
            )

            if not title:
                continue

            normalized = normalize_title(title)

            if normalized in seen_titles:
                continue

            seen_titles.add(normalized)

            description = get_description(entry)

            link = entry.get("link", "")

            published = get_date(entry)

            articles.append(
                {
                    "title": title,
                    "source": source,
                    "description": description,
                    "link": link,
                    "published": published,
                }
            )

            source_count += 1

    articles.sort(
        key=lambda article:
            article["published"]
            or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True
    )

    return articles


# ---------------------------------------------------------
# EPUB GENERATION
# ---------------------------------------------------------

def paragraph_html(text):
    if not text:
        return "<p>No summary supplied by the feed.</p>"

    paragraphs = []

    for part in text.split("\n"):

        part = part.strip()

        if not part:
            continue

        paragraphs.append(
            f"<p>{html.escape(part)}</p>"
        )

    return "\n".join(paragraphs)


def make_article(article, number, section_slug):

    chapter = epub.EpubHtml(
        title=article["title"],
        file_name=(
            f"{section_slug}_{number:02}.xhtml"
        ),
        lang="en",
    )

    published = ""

    if article["published"]:
        published = article["published"].strftime(
            "%d %B %Y, %H:%M UTC"
        )

    link_html = ""

    if article["link"]:
        link_html = (
            f'<p class="link">'
            f'Source: '
            f'<a href="{html.escape(article["link"])}">'
            f'{html.escape(article["source"])}'
            f'</a>'
            f'</p>'
        )

    chapter.content = f"""
    <html>
    <head>
        <title>{html.escape(article["title"])}</title>
    </head>

    <body>

        <h1>{html.escape(article["title"])}</h1>

        <p class="source">
            {html.escape(article["source"])}
        </p>

        <p class="date">
            {html.escape(published)}
        </p>

        {paragraph_html(article["description"])}

        {link_html}

    </body>
    </html>
    """

    return chapter


def build_epub(sections):

    now = datetime.now()

    date_iso = now.strftime("%Y-%m-%d")
    date_pretty = now.strftime("%d %B %Y")

    book = epub.EpubBook()

    book.set_identifier(
        f"x3-daily-brief-{date_iso}"
    )

    book.set_title(
        f"Daily Brief — {date_pretty}"
    )

    book.set_language("en")

    book.add_author("X3 Daily Brief")

    css = """
    body {
        font-family: serif;
        margin: 5%;
        line-height: 1.35;
    }

    h1 {
        font-size: 1.35em;
        margin-bottom: 0.3em;
    }

    h2 {
        font-size: 1.45em;
    }

    .source {
        font-weight: bold;
        margin-bottom: 0;
    }

    .date {
        font-size: 0.8em;
        margin-top: 0.2em;
    }

    .link {
        margin-top: 2em;
        font-size: 0.8em;
    }
    """

    style = epub.EpubItem(
        uid="style",
        file_name="style/main.css",
        media_type="text/css",
        content=css,
    )

    book.add_item(style)

    spine = ["nav"]

    toc = []

    for section_name, articles in sections.items():

        if not articles:
            continue

        section_slug = re.sub(
            r"\W+",
            "_",
            section_name.lower()
        )

        section_chapter = epub.EpubHtml(
            title=section_name,
            file_name=f"{section_slug}.xhtml",
            lang="en",
        )

        section_chapter.content = f"""
        <html>
        <body>
            <h1>{html.escape(section_name)}</h1>
            <p>{len(articles)} stories</p>
        </body>
        </html>
        """

        book.add_item(section_chapter)

        section_articles = []

        spine.append(section_chapter)

        for number, article in enumerate(
            articles,
            start=1
        ):

            chapter = make_article(
                article,
                number,
                section_slug
            )

            chapter.add_item(style)

            book.add_item(chapter)

            spine.append(chapter)

            section_articles.append(chapter)

        toc.append(
            (
                epub.Section(section_name),
                section_articles,
            )
        )

    book.toc = toc

    book.spine = spine

    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    output_dir = "books/daily"

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    filename = (
        f"{output_dir}/"
        f"daily-brief-{date_iso}.epub"
    )

    epub.write_epub(
        filename,
        book
    )

    print()
    print(f"Created {filename}")

    return filename


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    seen_titles = set()

    generated_sections = {}

    total = 0

    for section_name, feeds in SECTIONS.items():

        articles = fetch_section(
            feeds,
            seen_titles
        )

        generated_sections[
            section_name
        ] = articles

        total += len(articles)

        print(
            f"{section_name}: "
            f"{len(articles)} stories"
        )

    print()
    print(
        f"Total stories: {total}"
    )

    if total == 0:
        raise RuntimeError(
            "No articles were retrieved."
        )

    build_epub(
        generated_sections
    )


if __name__ == "__main__":
    main()
