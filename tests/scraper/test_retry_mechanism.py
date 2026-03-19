import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.scrapers.cmuh import CMUHScraper
from app.scrapers.ntuh import NTUHHsinchuScraper
from app.scrapers.hmmh import HMMHScraper
from app.scrapers.tvgh_taichung import TVGHTaichungScraper
from app.scrapers.tygh_hsinchu import TyghHsinchuScraper
from app.scrapers.tvgh_hsinchu import TvghHsinchuScraper
from app.scrapers.cgh_hsinchu import CGHHsinchuScraper

@pytest.mark.asyncio
async def test_cmuh_retry_mechanism():
    """Verify that CMUHScraper retries 5 times on failure (tenacity retry)."""
    scraper = CMUHScraper()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper._get("http://example.com")
            except httpx.ConnectError:
                pass
            # tenacity retries 5 times (stop_after_attempt(5))
            assert mock_get.call_count == 5

@pytest.mark.asyncio
async def test_ntuh_retry_mechanism():
    """Verify that NTUHHsinchuScraper retries 5 times on failure."""
    scraper = NTUHHsinchuScraper()
    # NTUH uses client.stream within an async context manager
    with patch("httpx.AsyncClient.stream") as mock_stream:
        import httpx
        from contextlib import asynccontextmanager
        
        @asynccontextmanager
        async def mock_stream_context(*args, **kwargs):
            raise httpx.TimeoutException("Timeout Error")
        
        mock_stream.side_effect = httpx.TimeoutException("Timeout Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper._get("http://example.com")
            except httpx.TimeoutException:
                pass
            # When the side_effect raises immediately (not in async context),
            # it gets called 5 times before retry gives up
            assert mock_stream.call_count == 5

@pytest.mark.asyncio
async def test_hmmh_retry_mechanism():
    """Verify that HMMHScraper retries 5 times on failure."""
    scraper = HMMHScraper()
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        import httpx
        mock_post.side_effect = httpx.RemoteProtocolError("Protocol Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper._post("http://example.com", data={})
            except httpx.RemoteProtocolError:
                pass
            assert mock_post.call_count == 5

@pytest.mark.asyncio
async def test_tvgh_taichung_retry_mechanism():
    """Verify that TVGHTaichungScraper retries 5 times on failure."""
    scraper = TVGHTaichungScraper()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper.fetch_departments()
            except httpx.ConnectError:
                pass
            assert mock_get.call_count == 5

@pytest.mark.asyncio
async def test_tygh_retry_mechanism():
    """Verify that TyghHsinchuScraper retries 5 times on failure."""
    scraper = TyghHsinchuScraper()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        import httpx
        mock_get.side_effect = httpx.TimeoutException("Timeout Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper._get("http://example.com")
            except httpx.TimeoutException:
                pass
            assert mock_get.call_count == 5

@pytest.mark.asyncio
async def test_tvgh_hsinchu_retry_mechanism():
    """Verify that TvghHsinchuScraper retries 5 times on failure."""
    scraper = TvghHsinchuScraper()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        import httpx
        mock_get.side_effect = httpx.ProxyError("Proxy Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper._get("http://example.com")
            except httpx.ProxyError:
                pass
            assert mock_get.call_count == 5

@pytest.mark.asyncio
async def test_cgh_retry_mechanism():
    """Verify that CGHHsinchuScraper retries 5 times on failure."""
    scraper = CGHHsinchuScraper()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper._get("http://example.com")
            except httpx.ConnectError:
                pass
            assert mock_get.call_count == 5
