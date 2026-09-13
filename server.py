import asyncio
import json
import time

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from main import is_valid_url, process_url
from scrape_sitemap import extract_urls_from_sitemap

app = FastAPI(title="Web Scraper API")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


class ScrapeRequest(BaseModel):
    urls: list[str]
    limit: int = 0


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.post("/scrape")
async def scrape(req: ScrapeRequest):
    async def event_generator():

        # Resolve URLs
        urls = []
        if req.sitemap:
            # Treat the first URL as a sitemap
            if req.urls:
                sitemap_url = req.urls[0]
                if not is_valid_url(sitemap_url):
                    yield {
                        "event": "error",
                        "data": json.dumps(
                            {"type": "error", "message": "Invalid sitemap URL."}
                        ),
                    }
                    return
                extracted = await asyncio.to_thread(
                    extract_urls_from_sitemap, sitemap_url
                )
                urls = list(dict.fromkeys(extracted))  # dedupe, preserve order
                yield {
                    "event": "message",
                    "data": json.dumps(
                        {
                            "type": "info",
                            "message": f"Extracted {len(urls)} URLs from sitemap.",
                        }
                    ),
                }
        else:
            urls = [u for u in req.urls if is_valid_url(u)]

        if not urls:
            yield {
                "event": "error",
                "data": json.dumps(
                    {"type": "error", "message": "No valid URLs provided."}
                ),
            }
            return

        # Apply limit
        if req.limit > 0:
            urls = urls[: req.limit]

        total = len(urls)
        start_time = time.time()
        successful = 0
        failed = 0

        all_results = []

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
