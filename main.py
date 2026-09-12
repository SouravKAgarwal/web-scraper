import argparse
import logging
import re
import sys
import time
from urllib.parse import urlparse
from pathlib import Path

import trafilatura
from bs4 import BeautifulSoup
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

def extract_fallback(html):
    """Fallback extraction using BeautifulSoup if Trafilatura fails."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Remove script, style, nav, and footer elements
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()
        
    return soup.get_text(separator='\n\n', strip=True)

def scrape_webpage(url):
    """Scrape and extract main content from a webpage."""
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
    
    # Fallback to BeautifulSoup if Trafilatura returns empty or very little text
    if not text or len(text.strip()) < 50:
        logger.info("Trafilatura extraction failed or returned too little text. Using fallback...")
        text = extract_fallback(html)
        if not title:
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.string if soup.title else "Untitled"

    if not text:
        raise ValueError("Could not extract any content from the page.")

    # Fallback title if still empty
    if not title:
        parsed_url = urlparse(url)
        title = parsed_url.netloc + parsed_url.path

    return {
        "url": url,
        "title": title.strip(),
        "text": text.strip(),
    }

def process_url(url, output_dir):
    """Scrape a URL and save it to the output directory."""
    try:
        data = scrape_webpage(url)
        
        # Generate safe filename based on the article's title
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
        content = f"# {data['title']}\n\n"
        content += f"**Source:** {data['url']}\n\n---\n\n"
        content += data["text"]
        
        # Ensure the output directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            
        logger.info(f"Successfully saved to {filepath}\n")
        return True
    except Exception as e:
        logger.error(f"Error processing {url}: {e}\n")
        return False

def is_interactive():
    # Check if running in a Jupyter/Interactive Window environment
    return hasattr(sys, 'ps1') or 'ipykernel' in sys.modules

def main():
    # If running in Jupyter, sys.argv has kernel arguments which break argparse
    if is_interactive():
        print("Interactive mode detected.")
        url = input("Enter webpage URL: ").strip()
        if url:
            if not is_valid_url(url):
                logger.error(f"Invalid URL: {url}")
                return
            process_url(url, "output")
        return

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
    
    success_count = 0
    for url in target_urls:
        if process_url(url, args.output):
            success_count += 1
            
    logger.info(f"Job completed. Successfully scraped {success_count}/{len(target_urls)} URLs.")

if __name__ == "__main__":
    main()
