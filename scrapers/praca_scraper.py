import asyncio
import logging
import os
import random
from datetime import datetime
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession, RequestsError, Response

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class PracaScraper:
    def __init__(self):
        self.base_url = "https://praca.by"
        self.search_url = f"{self.base_url}/search/vacancies/"
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self.semaphore = asyncio.Semaphore(5)
        self.captcha_detected_in_session = False
        self.debug_dir = "debug/failed_pages"
        os.makedirs(self.debug_dir, exist_ok=True)

    def _get_text(self, element, default="N/A"):
        return element.text.strip().replace("\xa0", " ") if element else default

    def _save_failed_page(self, url: str, content: str):
        if not content:
            return
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            page_id = url.split("/vacancy/")[1].split("/")[0]
            filename = os.path.join(
                self.debug_dir, f"praca_failed_{page_id}_{timestamp}.html"
            )
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
            logging.info(f"Saved problematic HTML to {filename}")
        except Exception as e:
            logging.error(f"Could not save failed page HTML for {url}: {e}")

    def _build_params(self, params: dict) -> dict:
        flat_params = {}
        for key, value in params.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, dict):
                        for inner_key, inner_value in sub_value.items():
                            flat_params[f"search[{key}][{sub_key}][{inner_key}]"] = (
                                inner_value
                            )
                    else:
                        flat_params[f"search[{key}][{sub_key}]"] = sub_value
            else:
                flat_params[f"search[{key}]"] = value
        return flat_params

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
                impersonate="chrome136",
                timeout=25,
            )
            response.raise_for_status()
            return response
        except RequestsError as e:
            logging.error(f"Request failed for {url} with params {params}: {e}")
            return None

    async def get_vacancy_urls_from_page(
        self, session: AsyncSession, params: dict, page: int = 0
    ) -> tuple[list[str] | None, bool]:
        request_params = self._build_params(params)
        if page > 0:
            request_params["page"] = page

        response = await self._make_request(
            session, self.search_url, params=request_params
        )
        if response is None:
            return None, False

        soup = BeautifulSoup(response.text, "lxml")
        vacancy_links = soup.select("li.vac-small a.vac-small__title-link")

        if not vacancy_links:
            logging.info(f"No vacancy links found on praca.by page {page}.")
            return [], False

        urls = [link["href"] for link in vacancy_links]
        has_next_page = soup.select_one(".next.page-item:not(.disabled)") is not None
        return urls, has_next_page

    async def scrape_vacancy_details(
        self, session: AsyncSession, url: str
    ) -> dict | None:
        async with self.semaphore:
            print_url = f"{url.split('?')[0].rstrip('/')}/print-version/"
            logging.info(f"Scraping praca.by vacancy: {print_url}")
            await asyncio.sleep(random.uniform(1.5, 3.0))

            response = await self._make_request(session, print_url)
            if response is None:
                return None

            try:
                soup = BeautifulSoup(response.text, "lxml")
                title = self._get_text(soup.select_one("h1"))
                company = self._get_text(soup.select_one(".org-name"))
                salary = self._get_text(soup.select_one(".salary .sum"), "не указана")
                location = self._get_text(soup.select_one(".address"))
                description_tag = soup.select_one(".description > div")
                description_html = str(description_tag) if description_tag else "N/A"

                return {
                    "url": url,
                    "apply_url": url,
                    "title": title,
                    "salary": salary,
                    "company": company,
                    "location": location,
                    "description": description_html,
                }
            except Exception as e:
                logging.error(
                    f"Failed to PARSE praca.by vacancy {url}: {e}", exc_info=True
                )
                self._save_failed_page(url, response.text)
                return None

    async def scrape_all_vacancies(
        self, params: dict, max_pages: int = 5
    ) -> list[dict]:
        all_vacancies = []
        async with AsyncSession() as session:
            for page_num in range(max_pages):
                urls, has_next_page = await self.get_vacancy_urls_from_page(
                    session, params, page_num
                )
                if urls is None:
                    logging.error(
                        f"Could not retrieve URLs from page {page_num}. Stopping scrape."
                    )
                    break
                if not urls:
                    logging.info(f"No more URLs found on page {page_num}. Stopping.")
                    break

                tasks = [self.scrape_vacancy_details(session, url) for url in urls]
                results = await asyncio.gather(*tasks)
                valid_results = [res for res in results if res]
                all_vacancies.extend(valid_results)
                logging.info(
                    f"Page {page_num} scraped. Found {len(valid_results)} valid vacancies. Total: {len(all_vacancies)}"
                )

                if not has_next_page:
                    logging.info("Last page reached. Stopping scrape.")
                    break

                await asyncio.sleep(random.uniform(2.0, 4.0))
        return all_vacancies
