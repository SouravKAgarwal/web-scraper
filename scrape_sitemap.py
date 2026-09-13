"""
Script to extract URLs from sitemap XML files.
Supports both standard sitemaps and sitemap indexes.
"""
import argparse
import logging
import xml.etree.ElementTree as ET

from curl_cffi import requests

from helpers import fetch_with_retries

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def extract_urls_from_sitemap(sitemap_url: str, max_depth: int = 5) -> list[str]:
    """
    Fetches a sitemap XML and extracts all the URLs found within it.
    Supports basic sitemaps and sitemap indexes. Recursively processes sitemap indexes.

    Args:
        sitemap_url (str): The URL of the sitemap or sitemap index to fetch.
        max_depth (int, optional): Maximum recursion depth for sitemap indexes 
            to prevent infinite loops. Defaults to 5.

    Returns:
        list[str]: A list of extracted URLs. Returns an empty list if extraction fails.
    """
    if max_depth <= 0:
        logger.warning(f"Maximum recursion depth reached. Skipping: {sitemap_url}")
        return []

    try:
        content = fetch_with_retries(sitemap_url, return_bytes=True)
    except (requests.RequestsError, OSError) as e:
        logger.error(f"Error fetching sitemap {sitemap_url}: {e}")
        return []

    urls = []

    try:
        root = ET.fromstring(content)

        # Namespaces are commonly used in sitemaps
        # Extract namespace if present
        namespace = ""
        if "}" in root.tag:
            namespace = root.tag.split("}")[0] + "}"

        # Check if this is a sitemapindex
        if root.tag.endswith("sitemapindex"):
            logger.info(
                f"Found sitemap index at {sitemap_url}. Processing child sitemaps..."
            )
            for sitemap in root.findall(f"{namespace}sitemap"):
                loc = sitemap.find(f"{namespace}loc")
                if loc is not None and loc.text:
                    child_sitemap_url = loc.text
                    urls.extend(
                        extract_urls_from_sitemap(
                            child_sitemap_url, max_depth=max_depth - 1
                        )
                    )
        # Otherwise, process as a standard sitemap
        elif root.tag.endswith("urlset"):
            for url in root.findall(f"{namespace}url"):
                loc = url.find(f"{namespace}loc")
                if loc is not None and loc.text:
                    urls.append(loc.text)
        else:
            logger.warning(f"Unknown root tag '{root.tag}' in {sitemap_url}")

    except ET.ParseError as e:
        logger.error(f"Error parsing XML from {sitemap_url}: {e}")

    return urls


def main():
    """
    Main entry point for the sitemap extraction script. Parses arguments,
    fetches the sitemap, extracts URLs, and optionally saves them to a file.
    """
    parser = argparse.ArgumentParser(description="Extract URLs from a sitemap XML.")
    parser.add_argument(
        "sitemap_url",
        help="The URL of the sitemap (e.g., https://example.com/sitemap.xml)",
    )
    parser.add_argument("-o", "--output", help="Optional output file to save the URLs")

    args = parser.parse_args()

    logger.info(f"Fetching sitemap from: {args.sitemap_url}")
    extracted_urls = extract_urls_from_sitemap(args.sitemap_url)

    # Remove duplicates while preserving order
    seen = set()
    unique_urls = [x for x in extracted_urls if not (x in seen or seen.add(x))]

    logger.info(f"Found {len(unique_urls)} unique URLs.")

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.writelines(f"{url}\n" for url in unique_urls)
            logger.info(f"Saved URLs to {args.output}")
        except OSError as e:
            logger.error(f"Error saving to {args.output}: {e}")
    else:
        for url in unique_urls:
            print(url)


if __name__ == "__main__":
    main()
