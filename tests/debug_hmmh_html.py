"""
Debug script to check HTML parsing
"""
import asyncio
import re
from bs4 import BeautifulSoup
import httpx


async def debug_html():
    url = "https://www.hc.mmh.org.tw/find_division.php"
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        html = resp.text
    
    soup = BeautifulSoup(html, "lxml")
    
    print(f"Total HTML length: {len(html)}")
    print(f"Total <a> tags: {len(soup.find_all('a'))}")
    
    # Test regex
    pattern = re.compile(r"depid=(\d+)")
    
    count = 0
    links = soup.find_all("a", href=True)
    print(f"\nFound {len(links)} links with href attribute\n")
    
    for a in links:
        href = a["href"]
        m = pattern.search(href)
        if m:
            code = m.group(1)
            name = a.get_text(strip=True)
            count += 1
            print(f"{count:2d}. Code={code:3s}, Name='{name}'")
            if "/child/" in href:
                print(f"     → Skipped (children's hospital)")
    
    print(f"\nTotal departments found: {count}")


if __name__ == "__main__":
    asyncio.run(debug_html())
