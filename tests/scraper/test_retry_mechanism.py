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
    """Verify that CMUHScraper retries 3 times on failure."""
    scraper = CMUHScraper()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Connection Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper._get("http://example.com")
            except Exception:
                pass
            assert mock_get.call_count == 3
            assert mock_sleep.call_count == 2

@pytest.mark.asyncio
async def test_ntuh_retry_mechanism():
    """Verify that NTUHHsinchuScraper retries 3 times on failure."""
    scraper = NTUHHsinchuScraper()
    # NTUH uses client.stream
    with patch("httpx.AsyncClient.stream", new_callable=AsyncMock) as mock_stream:
        # Mocking a context manager with side effect to fail
        mock_stream.side_effect = Exception("Connection Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper._get("http://example.com")
            except Exception:
                pass
            assert mock_stream.call_count == 3
            assert mock_sleep.call_count == 2

@pytest.mark.asyncio
async def test_hmmh_retry_mechanism():
    """Verify that HMMHScraper retries 3 times on failure."""
    scraper = HMMHScraper()
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = Exception("Connection Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper._post("http://example.com", data={})
            except Exception:
                pass
            assert mock_post.call_count == 3

@pytest.mark.asyncio
async def test_tvgh_taichung_retry_mechanism():
    """Verify that TVGHTaichungScraper retries 3 times on failure."""
    scraper = TVGHTaichungScraper()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Connection Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper.fetch_departments()
            except Exception:
                pass
            assert mock_get.call_count == 3

@pytest.mark.asyncio
async def test_tygh_retry_mechanism():
    """Verify that TyghHsinchuScraper retries 3 times on failure."""
    scraper = TyghHsinchuScraper()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Connection Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper._get("http://example.com")
            except Exception:
                pass
            assert mock_get.call_count == 3

@pytest.mark.asyncio
async def test_tvgh_hsinchu_retry_mechanism():
    """Verify that TvghHsinchuScraper retries 3 times on failure."""
    scraper = TvghHsinchuScraper()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Connection Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper._get("http://example.com")
            except Exception:
                pass
            assert mock_get.call_count == 3

@pytest.mark.asyncio
async def test_cgh_retry_mechanism():
    """Verify that CGHHsinchuScraper retries 3 times on failure."""
    scraper = CGHHsinchuScraper()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Connection Error")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            try:
                await scraper._get("http://example.com")
            except Exception:
                pass
            assert mock_get.call_count == 3
