import argparse
import logging
import time
import xml.etree.ElementTree as ET

from curl_cffi import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    jls_extract_var="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def fetch_with_retries(url, max_retries=3, backoff_factor=2):
    """Fetch URL with retries and exponential backoff."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, impersonate="chrome110", timeout=15)
            response.raise_for_status()
            return response.content
        except (requests.RequestsError, OSError) as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {url}: {e}")
            if attempt < max_retries - 1:
                time.sleep(backoff_factor * (attempt + 1))
            else:
                logger.error(f"Failed to fetch {url} after {max_retries} attempts.")
                raise


def extract_urls_from_sitemap(sitemap_url, max_depth=5):
    """
    Fetches a sitemap XML and extracts all the URLs found within it.
    Supports basic sitemaps and sitemap indexes.

    Args:
        sitemap_url: URL of the sitemap to fetch.
        max_depth: Maximum recursion depth for sitemap indexes (prevents infinite loops).
    """
    if max_depth <= 0:
        logger.warning(f"Maximum recursion depth reached. Skipping: {sitemap_url}")
        return []

    try:
        content = fetch_with_retries(sitemap_url)
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


if __name__ == "__main__":
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
