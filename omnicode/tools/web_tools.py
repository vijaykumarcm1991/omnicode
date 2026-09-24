"""
Web browsing and search tools for OmniCode.
Fetches web content (HTML to Markdown) and performs web searches.
"""

import re
import urllib.parse
from typing import Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from .base import BaseTool, ToolResult


def html_to_markdown(html_content: str, max_chars: int = 15000) -> str:
    """Convert HTML content into readable markdown text."""
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove non-content tags
    for tag in soup(
        ["script", "style", "nav", "footer", "header", "noscript", "svg", "iframe", "form"]
    ):
        tag.decompose()

    # Extract title
    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    # Process headings
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        level = int(h.name[1])
        prefix = "#" * level + " "
        h.replace_with(f"\n\n{prefix}{h.get_text().strip()}\n\n")

    # Process links
    for a in soup.find_all("a", href=True):
        text = a.get_text().strip()
        href = a["href"]
        if text and not href.startswith("javascript:"):
            a.replace_with(f" [{text}]({href}) ")

    # Process code blocks
    for pre in soup.find_all("pre"):
        code_text = pre.get_text()
        pre.replace_with(f"\n```\n{code_text}\n```\n")

    # Process paragraphs and lists
    for li in soup.find_all("li"):
        li.replace_with(f"\n* {li.get_text().strip()}")
    for p in soup.find_all("p"):
        p.replace_with(f"\n\n{p.get_text().strip()}\n\n")

    text = soup.get_text()
    # Normalize extra whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +", " ", text).strip()

    res = f"# {title}\n\n{text}" if title else text
    if len(res) > max_chars:
        res = res[:max_chars] + f"\n\n... [Content truncated, total length: {len(res)} characters]"
    return res


class FetchWebPageTool(BaseTool):
    """Tool to fetch and read web pages as clean Markdown."""

    name = "fetch_web_page"
    description = (
        "Fetch URL content and convert it into clean, readable Markdown. "
        "Useful for reading documentation, API references, or web articles."
    )
    is_read_only = True

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full HTTP or HTTPS URL to fetch.",
                }
            },
            "required": ["url"],
        }

    async def execute(self, url: str, **kwargs) -> ToolResult:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True, headers=headers
            ) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return ToolResult(
                        success=False,
                        error=f"HTTP request failed with status code {response.status_code}",
                    )

                content_type = response.headers.get("content-type", "")
                if "text/html" in content_type:
                    markdown = html_to_markdown(response.text)
                else:
                    markdown = response.text[:15000]

                return ToolResult(
                    success=True,
                    output=markdown,
                    metadata={"url": url, "status_code": response.status_code},
                )
        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to fetch URL '{url}': {str(e)}"
            )


class WebSearchTool(BaseTool):
    """Tool to search the web using DuckDuckGo HTML search."""

    name = "web_search"
    description = (
        "Perform a web search for documentation, packages, error solutions, or technical queries."
    )
    is_read_only = True

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum search results to return (default: 5).",
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, max_results: int = 5, **kwargs) -> ToolResult:
        try:
            encoded_query = urllib.parse.quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True, headers=headers
            ) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return ToolResult(
                        success=False,
                        error=f"Search request failed with status code {response.status_code}",
                    )

                soup = BeautifulSoup(response.text, "html.parser")
                results = []
                for result in soup.find_all("div", class_="result"):
                    title_elem = result.find("a", class_="result__a")
                    snippet_elem = result.find("a", class_="result__snippet")
                    if title_elem:
                        title = title_elem.get_text().strip()
                        link = title_elem.get("href", "")
                        snippet = snippet_elem.get_text().strip() if snippet_elem else ""

                        # DuckDuckGo HTML wraps URLs in /l/?uddg=
                        if "uddg=" in link:
                            match = re.search(r"uddg=([^&]+)", link)
                            if match:
                                link = urllib.parse.unquote(match.group(1))

                        results.append(f"### [{title}]({link})\n{snippet}\n")
                        if len(results) >= max_results:
                            break

                if not results:
                    return ToolResult(
                        success=True,
                        output=f"No web results found for query: '{query}'",
                    )

                out = f"Web search results for '{query}':\n\n" + "\n".join(results)
                return ToolResult(success=True, output=out)
        except Exception as e:
            return ToolResult(
                success=False, error=f"Web search failed: {str(e)}"
            )
