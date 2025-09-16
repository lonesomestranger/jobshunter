import asyncio
import json
import logging
import random
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession, RequestsError, Response


class RabotaScraper:
    def __init__(self, city: str):
        self.city_subdomain = city if city not in ["minsk", "all"] else ""
        self.base_url = f"https://{self.city_subdomain + '.' if self.city_subdomain else ''}rabota.by"
        self.search_url = f"{self.base_url}/search/vacancy"
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self.semaphore = asyncio.Semaphore(5)
        self.captcha_detected_in_session = False

    def _get_text(self, element):
        return element.text.strip().replace("\xa0", " ") if element else "N/A"

    def _parse_salary(self, salary_str: str) -> str:
        if not salary_str or salary_str == "N/A":
            return "не указана"
        return salary_str.replace("\u202f", " ").replace("\xa0", " ")

    async def _make_request_with_retries(
        self, session: AsyncSession, url: str, params: dict = None
    ) -> Response | None:
        retries = 3
        delays = [0, 5, 10]

        for i in range(retries):
            try:
                if delays[i] > 0:
                    logging.warning(
                        f"CAPTCHA detected for {url}. Retrying in {delays[i]} seconds... (Attempt {i + 1}/{retries})"
                    )
                    await asyncio.sleep(delays[i])

                response = await session.get(
                    url,
                    params=params,
                    headers=self.headers,
                    impersonate="chrome136",
                    timeout=25,
                )
                response.raise_for_status()

                if "Подтвердите, что вы не робот" not in response.text:
                    return response

            except RequestsError as e:
                logging.error(f"Request failed on attempt {i + 1} for {url}: {e}")
                if i == retries - 1:
                    break

        logging.error(f"Failed to bypass CAPTCHA for {url} after {retries} attempts.")
        return None

    async def get_vacancy_urls_from_page(
        self, session: AsyncSession, params: dict, page: int
    ) -> tuple[list[str] | None, bool]:
        current_params = params.copy()
        current_params["page"] = page
        logging.info(
            f"Requesting search page #{page} with query '{params.get('text', '')}' and area '{params.get('area', 'default')}'"
        )

        response = await self._make_request_with_retries(
            session, self.search_url, params=current_params
        )
        if response is None:
            self.captcha_detected_in_session = True
            return None, False

        soup = BeautifulSoup(response.text, "lxml")
        template_tag = soup.select_one("template#HH-Lux-InitialState")
        if not template_tag:
            logging.error(f"Could not find HH-Lux-InitialState tag on page {page}.")
            return None, False

        json_data = json.loads(template_tag.string)
        vacancies = json_data.get("vacancySearchResult", {}).get("vacancies", [])
        if not vacancies:
            logging.info(f"No vacancies found in JSON on page {page}.")
            return [], False

        urls = [
            vac.get("links", {}).get("desktop")
            for vac in vacancies
            if vac.get("links", {}).get("desktop")
        ]
        has_next_page = json_data.get("vacancySearchResult", {}).get(
            "hasNextPage", False
        )
        return urls, has_next_page

    async def scrape_vacancy_details(
        self, session: AsyncSession, url: str
    ) -> dict | None:
        async with self.semaphore:
            logging.info(f"Scraping vacancy: {url}")
            await asyncio.sleep(random.uniform(1.5, 3.0))

            response = await self._make_request_with_retries(session, url)
            if response is None:
                self.captcha_detected_in_session = True
                return None

            try:
                soup = BeautifulSoup(response.text, "lxml")
                title_element = soup.select_one('[data-qa="vacancy-title"]')
                if not title_element:
                    logging.warning(
                        f"Could not find title for vacancy {url}. Page structure might be different. Skipping."
                    )
                    return None

                title = self._get_text(title_element)
                salary = self._parse_salary(
                    self._get_text(soup.select_one('[data-qa="vacancy-salary"]'))
                )
                company_tag = soup.select_one('[data-qa="vacancy-company-name"]')
                company_name = (
                    self._get_text(company_tag.find("span")) if company_tag else "N/A"
                )
                location = self._get_text(
                    soup.select_one('[data-qa="vacancy-view-raw-address"]')
                ) or self._get_text(
                    soup.select_one('[data-qa="vacancy-view-location"]')
                )
                description_tag = soup.select_one('[data-qa="vacancy-description"]')
                description = str(description_tag) if description_tag else "N/A"
                apply_link_tag = soup.select_one(
                    '[data-qa="vacancy-response-link-top"]'
                )
                apply_url = (
                    urljoin(self.base_url, apply_link_tag["href"])
                    if apply_link_tag
                    else url
                )

                return {
                    "url": url,
                    "apply_url": apply_url,
                    "title": title,
                    "salary": salary,
                    "company": company_name,
                    "location": location,
                    "description": description,
                }
            except Exception as e:
                logging.error(
                    f"Failed to PARSE vacancy {url} after successful request: {e}"
                )
                return None

    async def scrape_all_vacancies(
        self, params: dict, max_pages: int = 5
    ) -> list[dict]:
        all_vacancies = []
        async with AsyncSession() as session:
            for page_num in range(max_pages):
                if self.captcha_detected_in_session:
                    logging.error(
                        "CAPTCHA was detected and retries failed. Stopping export for this subscription."
                    )
                    break

                urls, has_next_page = await self.get_vacancy_urls_from_page(
                    session, params, page_num
                )
                if urls is None:
                    break
                if not urls:
                    logging.info(
                        f"No more URLs found on page {page_num}. Stopping export scrape."
                    )
                    break

                tasks = [self.scrape_vacancy_details(session, url) for url in urls]
                results = await asyncio.gather(*tasks)

                successful_results = [res for res in results if res]
                all_vacancies.extend(successful_results)

                logging.info(
                    f"Page {page_num} scraped. Found {len(successful_results)} valid vacancies. New total: {len(all_vacancies)}"
                )

                if not has_next_page:
                    logging.info("Last page reached. Stopping scrape.")
                    break

                await asyncio.sleep(random.uniform(3.0, 6.0))

        return all_vacancies
