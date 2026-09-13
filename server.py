import asyncio
import json
import time
from enum import Enum

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from helpers import is_valid_url
from main import process_url
from scrape_sitemap import extract_urls_from_sitemap

app = FastAPI(
    title="Web Scraper API",
    description="API for scraping web pages and sitemaps, returning structured Markdown content.",
    version="1.0.0",
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


class ResponseFormat(str, Enum):
    sse = "sse"
    json = "json"


class ScrapeRequest(BaseModel):
    urls: list[str] = Field(
        ...,
        description="List of URLs to scrape. If sitemap is true, the first URL is treated as a sitemap URL.",
        examples=[["https://example.com/sitemap.xml"]],
    )
    limit: int = Field(
        default=0,
        description="Maximum number of URLs to scrape. Set to 0 for no limit.",
    )
    sitemap: bool = Field(
        default=False,
        description="If true, treats the first URL in the urls list as a sitemap and extracts URLs from it.",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.sse,
        description="Format of the response: 'sse' for Server-Sent Events stream, 'json' for a single JSON response.",
    )


class ScrapeResult(BaseModel):
    url: str
    title: str = ""
    description: str = ""
    content: str = ""
    author: str | None = None
    date: str | None = None
    image: str | None = None
    sitename: str | None = None
    language: str | None = None
    word_count: int = 0


class FailedResult(BaseModel):
    url: str
    error: str


class ScrapeResponse(BaseModel):
    successful: int
    failed: int
    total: int
    results: list[ScrapeResult]
    failed_results: list[FailedResult]
    response_time: float


@app.get("/", summary="Serve the web interface", tags=["UI"])
async def index():
    """
    Serves the static index.html file for the web UI.
    """
    return FileResponse("static/index.html")


async def resolve_urls(req: ScrapeRequest) -> list[str]:
    """Helper function to resolve and validate URLs from the request."""
    urls = []
    if req.sitemap:
        if req.urls:
            sitemap_url = req.urls[0]
            if not is_valid_url(sitemap_url):
                raise ValueError("Invalid sitemap URL.")
            extracted = await asyncio.to_thread(extract_urls_from_sitemap, sitemap_url)
            urls = list(dict.fromkeys(extracted))  # dedupe, preserve order
    else:
        urls = [u for u in req.urls if is_valid_url(u)]

    if not urls:
        raise ValueError("No valid URLs provided.")

    # Apply limit
    if req.limit > 0:
        urls = urls[: req.limit]

    return urls


@app.post(
    "/scrape",
    summary="Scrape a list of URLs or a sitemap",
    tags=["Scraping"],
    responses={
        200: {
            "description": "Returns either a Server-Sent Events (SSE) stream or a JSON payload depending on response_format.",
            "model": ScrapeResponse,
        }
    },
)
async def scrape(req: ScrapeRequest):
    """
    **Initiates a web scraping job for a list of URLs or a sitemap.**
    
    This endpoint processes the incoming URLs and extracts structured Markdown content, metadata, and statistics.

    ### URL Resolution
    - **Sitemap Mode:** If `sitemap` is set to `true`, the first URL in the `urls` list is treated as a sitemap XML. The API will fetch the sitemap, extract all valid URLs recursively, and queue them for scraping.
    - **Direct Mode:** If `sitemap` is `false`, the API will scrape the exact URLs provided in the `urls` list.
    - **Limit:** You can restrict the maximum number of URLs to process using the `limit` parameter (set to 0 for no limit).

    ### Response Formats
    The behavior of this endpoint changes based on the `response_format` parameter:
    
    - **`sse` (Server-Sent Events) - Default:** 
      Ideal for front-end integrations or long lists. It returns a real-time stream of events, allowing you to track progress.
      *Events emitted:*
      - `info`: General informational messages (e.g., sitemap extraction count).
      - `progress`: Updates indicating which URL is currently being processed.
      - `result`: The extracted data or error for a single URL.
      - `done`: Emitted at the end with a complete summary of the job.
      - `error`: Emitted if a fatal validation error occurs before scraping begins.
      
    - **`json` (Standard JSON):** 
      Ideal for backend scripts or bulk programmatic access. It waits synchronously for all scraping tasks to complete (which may take a while depending on the number of URLs) and returns a single JSON object containing the total successes, failures, execution time, and an array of all extracted results.
    """
    
    if req.response_format == ResponseFormat.json:
        try:
            urls = await resolve_urls(req)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

        start_time = time.time()
        successful = 0
        failed = 0
        all_results = []

        for url in urls:
            result = await asyncio.to_thread(process_url, url)
            all_results.append(result)
            if "error" in result:
                failed += 1
            else:
                successful += 1

        elapsed = round(time.time() - start_time, 2)
        return {
            "successful": successful,
            "failed": failed,
            "total": len(urls),
            "results": [r for r in all_results if "error" not in r],
            "failed_results": [r for r in all_results if "error" in r],
            "response_time": elapsed,
        }

    else:
        async def event_generator():
            try:
                urls = await resolve_urls(req)
            except ValueError as e:
                yield {
                    "event": "error",
                    "data": json.dumps({"type": "error", "message": str(e)}),
                }
                return

            total = len(urls)
            start_time = time.time()
            successful = 0
            failed = 0
            all_results = []

            # Optional info event if it was a sitemap
            if req.sitemap:
                yield {
                    "event": "message",
                    "data": json.dumps(
                        {
                            "type": "info",
                            "message": f"Extracted {len(urls)} URLs from sitemap.",
                        }
                    ),
                }

            for i, url in enumerate(urls):
                # Send progress event
                yield {
                    "event": "message",
                    "data": json.dumps(
                        {
                            "type": "progress",
                            "current": i + 1,
                            "total": total,
                            "url": url,
                        }
                    ),
                }

                # Run the blocking scrape in a thread
                result = await asyncio.to_thread(process_url, url)
                all_results.append(result)

                if "error" in result:
                    failed += 1
                else:
                    successful += 1

                # Send result event
                yield {
                    "event": "message",
                    "data": json.dumps({"type": "result", "data": result}),
                }

            elapsed = round(time.time() - start_time, 2)

            # Send done event
            yield {
                "event": "message",
                "data": json.dumps(
                    {
                        "type": "done",
                        "successful": successful,
                        "failed": failed,
                        "total": total,
                        "results": [r for r in all_results if "error" not in r],
                        "response_time": elapsed,
                    }
                ),
            }

        return EventSourceResponse(event_generator())
