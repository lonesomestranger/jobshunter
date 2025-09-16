import asyncio
import logging
import random
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession, RequestsError, Response

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class HabrScraper:
    def __init__(self):
        self.base_url = "https://career.habr.com"
        self.search_url = f"{self.base_url}/vacancies"
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "max-age=0",
            "Referer": "https://career.habr.com/",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        self.semaphore = asyncio.Semaphore(5)

    def _get_text(self, element):
        return element.text.strip().replace("\xa0", " ") if element else "N/A"

    async def _make_request(
        self, session: AsyncSession, url: str, params: dict = None
    ) -> Response | None:
        try:
            full_url = url
            if params:
                full_url += "?" + urlencode(params, doseq=True)
            logging.info(f"Requesting URL: {full_url}")

            response = await session.get(
                url,
                params=params,
                headers=self.headers,
                impersonate="chrome124",
                timeout=25,
            )
            response.raise_for_status()
            return response
        except RequestsError as e:
            logging.error(f"Request failed for {url} with params {params}: {e}")
            return None

    async def get_vacancy_urls_from_page(
        self, session: AsyncSession, params: dict, page: int
    ) -> list[str] | None:
        current_params = params.copy()
        current_params["page"] = page + 1

        response = await self._make_request(
            session, self.search_url, params=current_params
        )
        if response is None:
            return None

        soup = BeautifulSoup(response.text, "lxml")
        vacancy_cards = soup.select(".vacancy-card__title-link")
        if not vacancy_cards:
            logging.info(
                f"No vacancies found on page {page} for query '{params.get('q', '')}'."
            )
            return []

        urls = [urljoin(self.base_url, card["href"]) for card in vacancy_cards]
        return urls

    async def scrape_vacancy_details(
        self, session: AsyncSession, url: str
    ) -> dict | None:
        async with self.semaphore:
            logging.info(f"Scraping Habr vacancy: {url}")
            await asyncio.sleep(random.uniform(1.5, 3.0))

            response = await self._make_request(session, url)
            if response is None:
                return None

            try:
                soup = BeautifulSoup(response.text, "lxml")
                title = self._get_text(soup.select_one(".page-title__title"))
                salary = (
                    self._get_text(soup.select_one(".basic-salary__amount"))
                    or "не указана"
                )
                company = self._get_text(soup.select_one(".company_name a"))

                location_parts = [
                    self._get_text(el) for el in soup.select(".location-info__location")
                ]
                location = ", ".join(filter(None, location_parts))

                description_tag = soup.select_one(".vacancy-description__text")
                description = str(description_tag) if description_tag else "N/A"

                return {
                    "url": url,
                    "apply_url": url,
                    "title": title,
                    "salary": salary,
                    "company": company,
                    "location": location,
                    "description": description,
                }
            except Exception as e:
                logging.error(f"Failed to PARSE Habr vacancy {url}: {e}", exc_info=True)
                return None

    async def scrape_all_vacancies(
        self, params: dict, max_pages: int = 5
    ) -> list[dict]:
        all_vacancies = []
        async with AsyncSession() as session:
            for page_num in range(max_pages):
                urls = await self.get_vacancy_urls_from_page(session, params, page_num)
                if urls is None:
                    logging.error(
                        f"Could not retrieve URLs from page {page_num}. Stopping scrape for this subscription."
                    )
                    break
                if not urls:
                    logging.info(f"No more URLs found on page {page_num}. Stopping.")
                    break

                tasks = [self.scrape_vacancy_details(session, url) for url in urls]
                results = await asyncio.gather(*tasks)
                all_vacancies.extend([res for res in results if res])
                logging.info(
                    f"Page {page_num} scraped. Total vacancies: {len(all_vacancies)}"
                )

                test_params = params.copy()
                test_params["page"] = page_num + 2
                response = await self._make_request(
                    session, self.search_url, params=test_params
                )
                if response:
                    soup = BeautifulSoup(response.text, "lxml")
                    if not soup.select_one(".vacancy-card__title-link"):
                        logging.info(
                            "This was the last page of results. Stopping scrape."
                        )
                        break
                else:
                    logging.warning(
                        f"Could not verify next page ({page_num + 1}), stopping."
                    )
                    break

                await asyncio.sleep(random.uniform(2.5, 5.0))
        return all_vacancies
