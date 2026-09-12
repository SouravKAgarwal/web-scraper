import argparse
import json
import logging
import re
import sys
import time
from urllib.parse import urlparse
from pathlib import Path
import trafilatura
from curl_cffi import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

def slugify(text):
    """Convert text to a safe filename."""
    text = re.sub(r'[^\w\s-]', '', text.lower())
    return re.sub(r'[\s_-]+', '-', text).strip('-')

def is_valid_url(url):
    """Check if a string looks like a valid HTTP(S) URL."""
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)

def fetch_with_retries(url, max_retries=3, backoff_factor=2):
    """Fetch URL with retries and exponential backoff."""
    headers = {
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=15, impersonate="chrome")
            response.raise_for_status()
            return response.text
        except (requests.RequestsError, OSError) as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(backoff_factor * (attempt + 1))
            else:
                logger.error(f"Failed to fetch {url} after {max_retries} attempts.")
                raise

def scrape_webpage(url):
    """Scrape and extract main content from a webpage, returning structured data."""
    logger.info(f"Fetching: {url}")
    html = fetch_with_retries(url)
    
    logger.info("Extracting content...")
    
    # Try Trafilatura first (best for articles)
    text = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=True,
        include_images=True,
        include_comments=False
    )
    
    metadata = trafilatura.extract_metadata(html)
    title = metadata.title if metadata and metadata.title else ""
        
    if not text:
        raise ValueError("Could not extract any content from the page.")

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

def process_url(url, output_dir):
    """Scrape a URL and save it to the output directory. Returns structured data dict or error dict."""
    try:
        data = scrape_webpage(url)
        
        safe_title = slugify(data["title"])[:100]  # Limit length
        if not safe_title:
            safe_title = slugify(url)[:100]
            
        filename = f"{safe_title}.md"
        filepath = Path(output_dir) / filename
        
        # Avoid filename collisions by appending a numeric suffix
        counter = 1
        while filepath.exists():
            filename = f"{safe_title}-{counter}.md"
            filepath = Path(output_dir) / filename
            counter += 1
        
        # Add metadata header to markdown
        md_content = f"# {data['title']}\n\n"
        md_content += f"**Source:** {data['url']}\n\n---\n\n"
        md_content += data["content"]
        
        # Ensure the output directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        logger.info(f"Successfully saved to {filepath}\n")
        return data
    except Exception as e:
        logger.error(f"Error processing {url}: {e}\n")
        return {"url": url, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="A robust AI Web Scraper")
    parser.add_argument("url", nargs="?", help="A single URL to scrape")
    parser.add_argument("-f", "--file", help="Text file containing a list of URLs (one per line)")
    parser.add_argument("-o", "--output", default="output", help="Directory to save scraped markdown files")
    parser.add_argument("-n", "--limit", type=int, default=None, help="Maximum number of URLs to scrape")
    
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
        except Exception as e:
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
    target_urls = urls[:args.limit] if args.limit else urls
    if args.limit and len(urls) > args.limit:
        logger.warning(f"Limiting to first {args.limit} of {len(urls)} URLs (use -n to change).")

    logger.info(f"Starting scraping job for {len(target_urls)} URL(s)...")
    
    start_time = time.time()
    all_results = []
    success_count = 0
    
    for url in target_urls:
        result = process_url(url, args.output)
        all_results.append(result)
        if "error" not in result:
            success_count += 1

    elapsed = round(time.time() - start_time, 2)
    logger.info(f"Job completed. Successfully scraped {success_count}/{len(target_urls)} URLs in {elapsed}s.")

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
    print(json.dumps(res, indent=4, ensure_ascii=False))
