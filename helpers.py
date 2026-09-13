"""
Utility functions for web scraping and data processing.
"""
import logging
import re
import time
from urllib.parse import urlparse

from curl_cffi import requests

logger = logging.getLogger(__name__)

def is_valid_url(url: str) -> bool:
    """
    Check if a string looks like a valid HTTP(S) URL.

    Args:
        url (str): The URL string to validate.

    Returns:
        bool: True if the URL scheme is http or https and has a valid network location, False otherwise.
    """
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except (TypeError, ValueError):
        return False


def fetch_with_retries(url: str, max_retries: int = 3, backoff_factor: int = 2, return_bytes: bool = False):
    """
    Fetch the content of a URL with retries and exponential backoff.

    Args:
        url (str): The URL to fetch.
        max_retries (int, optional): Maximum number of retry attempts. Defaults to 3.
        backoff_factor (int, optional): Multiplier for the exponential backoff delay. Defaults to 2.
        return_bytes (bool, optional): If True, returns raw bytes (e.g., for XML). If False, returns decoded text. Defaults to False.

    Returns:
        str | bytes: The text or byte content of the HTTP response.

    Raises:
        requests.RequestsError: If a request error occurs.
        OSError: If a network-related error occurs.
    """
    headers = {
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }

    for attempt in range(max_retries):
        try:
            # Impersonate chrome for better success rate
            response = requests.get(
                url, headers=headers, timeout=15, impersonate="chrome110"
            )
            response.raise_for_status()
            return response.content if return_bytes else response.text
        except (requests.RequestsError, OSError) as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {url}: {e}")
            if attempt < max_retries - 1:
                time.sleep(backoff_factor * (attempt + 1))
            else:
                logger.error(f"Failed to fetch {url} after {max_retries} attempts.")
                raise


def clean_markdown(text: str) -> str:
    """
    Clean up messy markdown formatting, typically produced by automated extractors.

    Args:
        text (str): The raw markdown text to clean.

    Returns:
        str: The cleaned markdown text, or the original text if it was empty.
    """
    if not text:
        return text

    # 1. Fix incorrect bullet position (includes nested lists):
    # Trafilatura splits definition lists into separate bullets and newlines.
    # We merge them: "  - \n **Term** \n  - \n Definition"
    text = re.sub(
        r"^(\s*)-\s*\n\s*\*\*(.*?)\*\*\s*\n\1-\s*\n\s*",
        r"\1- **\2**: ",
        text,
        flags=re.MULTILINE,
    )

    # 2. Handle a variation where it doesn't add a second hyphen
    text = re.sub(
        r"^(\s*)-\s*\n\s*\*\*(.*?)\*\*\s*\n\s*",
        r"\1- **\2**: ",
        text,
        flags=re.MULTILINE,
    )

    # 3. Remove any remaining standalone empty bullets
    text = re.sub(r"^\s*-\s*\n", "", text, flags=re.MULTILINE)

    # 4. Remove multiple consecutive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
