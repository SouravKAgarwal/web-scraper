"""
Main script for scraping and processing web pages.
Provides functionality to scrape single URLs or a list of URLs from a file.
"""
import argparse
import json
import logging
import time
from urllib.parse import urlparse

import trafilatura
from bs4 import BeautifulSoup
from curl_cffi import requests

from helpers import clean_markdown, fetch_with_retries, is_valid_url

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def scrape_webpage(url: str) -> dict:
    """
    Scrape and extract main content from a webpage, returning structured data.

    This function fetches the HTML content of the provided URL, pre-processes it to handle
    parsing bugs, and extracts the main text and metadata using Trafilatura.

    Args:
        url (str): The URL of the webpage to scrape.

    Returns:
        dict: A dictionary containing the scraped data:
            - url (str): The original URL.
            - title (str): The title of the webpage.
            - description (str): A brief description or snippet of the content.
            - content (str): The extracted main text content formatted as Markdown.
            - author (str | None): The author of the content, if found.
            - date (str | None): The publication date, if found.
            - image (str | None): The primary image URL, if found.
            - sitename (str | None): The name of the website, if found.
            - language (str | None): The language of the content, if found.
            - word_count (int): The number of words in the extracted content.

    Raises:
        ValueError: If no content could be extracted from the page.
    """
    logger.info(f"Fetching: {url}")
    html = fetch_with_retries(url)

    logger.info("Extracting content...")

    # Pre-process HTML to fix Trafilatura's parsing bugs with complex tags
    soup = BeautifulSoup(html, "html.parser")

    # Unwrap all nested tags inside <pre> blocks to prevent code block fragmentation
    for pre in soup.find_all("pre"):
        for tag in pre.find_all(True):
            tag.unwrap()

    # Try Trafilatura first (best for articles)
    text = trafilatura.extract(
        str(soup),
        output_format="markdown",
        include_tables=True,
        include_formatting=True,
        include_links=True,
        include_images=True,
        include_comments=False,
    )

    metadata = trafilatura.extract_metadata(html)
    title = metadata.title if metadata and metadata.title else ""

    if not text:
        raise ValueError("Could not extract any content from the page.")

    text = clean_markdown(text)

    # Fallback title if still empty
    if not title:
        parsed_url = urlparse(url)
        title = parsed_url.netloc + parsed_url.path

    # Build description: use meta description or first 200 chars of content
    description = ""
    if metadata and metadata.description:
        description = metadata.description
    elif text:
        description = text[:200].rsplit(" ", 1)[0] + "..."

    return {
        "url": url,
        "title": title.strip(),
        "description": description.strip(),
        "content": text.strip(),
        "author": (metadata.author if metadata and metadata.author else None),
        "date": (metadata.date if metadata and metadata.date else None),
        "image": (metadata.image if metadata and metadata.image else None),
        "sitename": (metadata.sitename if metadata and metadata.sitename else None),
        "language": (metadata.language if metadata and metadata.language else None),
        "word_count": len(text.split()),
    }


def process_url(url: str) -> dict:
    """
    Safely scrape a URL and return structured data, handling any exceptions.

    Args:
        url (str): The URL to scrape.

    Returns:
        dict: The structured data dictionary on success, or a dictionary containing
              the 'url' and 'error' message on failure.
    """
    try:
        data = scrape_webpage(url)

        logger.info(f"Successfully scraped: {data['title']}\n")
        return data
    except (requests.RequestsError, OSError, ValueError, TypeError) as e:
        logger.error(f"Error processing {url}: {e}\n")
        return {"url": url, "error": str(e)}


def main() -> dict | None:
    """
    Main entry point for the CLI script. Parses arguments and executes the scraping job.

    Returns:
        dict | None: A summary of the scraping results, or None if validation fails.
    """
    parser = argparse.ArgumentParser(description="A robust AI Web Scraper")
    parser.add_argument("url", nargs="?", help="A single URL to scrape")
    parser.add_argument(
        "-f", "--file", help="Text file containing a list of URLs (one per line)"
    )
    parser.add_argument(
        "-n", "--limit", type=int, default=None, help="Maximum number of URLs to scrape"
    )

    args = parser.parse_args()

    urls = []

    # 1. Add URL if provided via argument
    if args.url:
        if is_valid_url(args.url):
            urls.append(args.url)
        else:
            logger.error(f"Invalid URL: {args.url}")
            return

    # 2. Add URLs if provided via a file
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if is_valid_url(line):
                            urls.append(line)
                        else:
                            logger.warning(f"Skipping invalid URL: {line}")
        except (OSError, UnicodeError) as e:
            logger.error(f"Failed to read URLs from file {args.file}: {e}")
            return

    # 3. Fallback to manual input if no URLs provided
    if not urls:
        print("No URLs provided via arguments.")
        url = input("Enter webpage URL: ").strip()
        if url:
            if not is_valid_url(url):
                logger.error(f"Invalid URL: {url}")
                return
            urls.append(url)
        else:
            parser.print_help()
            return

    # Apply limit if specified
    target_urls = urls[: args.limit] if args.limit else urls
    if args.limit and len(urls) > args.limit:
        logger.warning(
            f"Limiting to first {args.limit} of {len(urls)} URLs (use -n to change)."
        )

    logger.info(f"Starting scraping job for {len(target_urls)} URL(s)...")

    start_time = time.time()
    all_results = []
    success_count = 0

    for url in target_urls:
        result = process_url(url)
        all_results.append(result)
        if "error" not in result:
            success_count += 1

    elapsed = round(time.time() - start_time, 2)
    logger.info(
        f"Job completed. Successfully scraped {success_count}/{len(target_urls)} URLs in {elapsed}s."
    )

    output = {
        "results": [r for r in all_results if "error" not in r],
        "failed_results": [r for r in all_results if "error" in r],
        "total": len(target_urls),
        "successful": success_count,
        "response_time": elapsed,
    }

    return output


if __name__ == "__main__":
    res = main()
    if res:
        print(json.dumps(res, indent=4, ensure_ascii=False))
