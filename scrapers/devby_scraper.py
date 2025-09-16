import asyncio
import logging
import os
import random
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession, RequestsError, Response

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class DevbyScraper:
    def __init__(self):
        self.base_url = "https://jobs.devby.io"
        self.search_url = self.base_url
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
            vacancy_id = url.split("/vacancies/")[1].split("?")[0]
            filename = os.path.join(
                self.debug_dir, f"devby_failed_{vacancy_id}_{timestamp}.html"
            )
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
            logging.info(f"Saved problematic HTML to {filename}")
        except Exception as e:
            logging.error(f"Could not save failed page HTML for {url}: {e}")

    async def _make_request(self, session: AsyncSession, url: str) -> Response | None:
        try:
            logging.info(f"Requesting URL: {url}")
            response = await session.get(
                url, headers=self.headers, impersonate="chrome136", timeout=25
            )
            response.raise_for_status()
            return response
        except RequestsError as e:
            logging.error(f"Request failed for {url}: {e}")
            return None

    async def get_vacancy_urls_from_page(
        self, session: AsyncSession, params: dict, page: int = 0
    ) -> list[str] | None:
        logging.info("Requesting dev.by vacancies list page...")
        response = await self._make_request(session, self.search_url)
        if response is None:
            return None

        soup = BeautifulSoup(response.text, "lxml")
        vacancy_items = soup.select(
            ".vacancies-list-item__body a.vacancies-list-item__link_block"
        )

        if not vacancy_items:
            logging.info("No vacancy links found on dev.by main page.")
            return []

        urls = [urljoin(self.base_url, link["href"]) for link in vacancy_items]
        return urls

    async def scrape_vacancy_details(
        self, session: AsyncSession, url: str
    ) -> dict | None:
        async with self.semaphore:
            logging.info(f"Scraping dev.by vacancy: {url}")
            await asyncio.sleep(random.uniform(1.5, 3.0))

            response = await self._make_request(session, url)
            if response is None:
                return None

            try:
                soup = BeautifulSoup(response.text, "lxml")

                title_element = soup.select_one("h1.title")
                if not title_element:
                    logging.warning(
                        f"Could not find title for dev.by vacancy {url}. Page might be a CAPTCHA or has changed. Saving HTML for debug."
                    )
                    self._save_failed_page(url, response.text)
                    return None

                title = self._get_text(title_element, default="Заголовок не найден")
                company = self._get_text(
                    soup.select_one(".vacancy__header__company-name a"),
                    default="Компания не найдена",
                )

                info_data = {}
                for item in soup.select(".vacancy__info-block__item"):
                    text_content = item.get_text(strip=True)
                    if ":" in text_content:
                        key, value = text_content.split(":", 1)
                        info_data[key.strip()] = value.strip()

                salary = info_data.get("Зарплата", "не указана")
                location = info_data.get("Город", "Локация не указана")

                tags = [
                    self._get_text(tag) for tag in soup.select("a.vacancy__tags__item")
                ]

                description_tag = soup.select_one("div.vacancy__text .text")
                description_html = str(description_tag) if description_tag else "N/A"

                extra_info_lines = [
                    f"<b>{key}:</b> {value}"
                    for key, value in info_data.items()
                    if key not in ["Зарплата", "Город"]
                ]
                tags_line = "<b>Тэги:</b> " + ", ".join(tags) if tags else ""

                full_description_parts = []
                if extra_info_lines:
                    full_description_parts.append("<br>".join(extra_info_lines))
                if tags_line:
                    full_description_parts.append(tags_line)

                final_description = ""
                if full_description_parts:
                    final_description += (
                        "<p>" + "</p><p>".join(full_description_parts) + "</p>"
                    )
                    final_description += "<hr>"
                final_description += description_html

                return {
                    "url": url,
                    "apply_url": url,
                    "title": title,
                    "salary": salary,
                    "company": company,
                    "location": location,
                    "description": final_description.strip(),
                }
            except Exception as e:
                logging.error(
                    f"Failed to PARSE dev.by vacancy {url}: {e}", exc_info=True
                )
                self._save_failed_page(url, response.text)
                return None

    async def scrape_all_vacancies(self, params: dict = None) -> list[dict]:
        all_vacancies = []
        async with AsyncSession() as session:
            urls = await self.get_vacancy_urls_from_page(session, params={})
            if not urls:
                logging.info("No vacancies to scrape from dev.by.")
                return []

            logging.info(
                f"Found {len(urls)} vacancies. Scraping details sequentially to avoid blocking..."
            )
            for i, url in enumerate(urls):
                details = await self.scrape_vacancy_details(session, url)
                if details:
                    all_vacancies.append(details)
                logging.info(
                    f"Processed {i + 1}/{len(urls)}. Total collected: {len(all_vacancies)}"
                )

            logging.info(f"Total vacancies scraped from dev.by: {len(all_vacancies)}")

        return all_vacancies
