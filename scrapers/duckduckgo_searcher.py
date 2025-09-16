import asyncio
import logging
from typing import Dict, List, Optional

from ddgs import DDGS

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class DuckDuckGoSearcher:
    def __init__(self):
        self.ddgs_client = DDGS()

    async def search(
        self, query: str, max_results: int = 100
    ) -> Optional[List[Dict[str, str]]]:
        logging.info(f"Поиск в DuckDuckGo по запросу: '{query}'")
        try:
            results = await asyncio.to_thread(
                self.ddgs_client.text, query=query, max_results=max_results
            )
            if not results:
                logging.warning(f"Не найдено результатов по запросу: '{query}'")
                return []

            return [
                {"title": res.get("title"), "link": res.get("href")}
                for res in results
                if res.get("title") and res.get("href")
            ]
        except Exception as e:
            logging.error(f"Произошла ошибка во время поиска DDG: {e}")
            return None


BLACKLIST = [
    "hh.ru",
    "rabota.by",
    # "habr.com/ru/companies",
    "career.habr.com",
    "gorodrabot.ru",
    "work.ua",
    "jooble.org",
    "getmatch.ru",
    "dreamjob.ru",
    "devjobsscanner.com",
    "jobs.devby.io",
    "dev.by",
    "layboard.com",
    "russia.gorodrabot.ru",
    "instagram.com",
    "facebook.com",
    "nicegram.app",
    "telegram-site.com",
    "github.com/hhru/api",
    "career.habr.com/salaries",
    "career.habr.com/resumes",
    "geekjob.ru/geek/",
]


def filter_and_deduplicate_results(
    results: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    if not results:
        return []

    filtered = []
    seen_urls = set()

    for result in results:
        link = result.get("link")
        if not link:
            continue

        if link in seen_urls:
            logging.info(f"Удален дубликат: {link}")
            continue

        if any(b in link.lower() for b in BLACKLIST):
            logging.info(f"Отфильтрована ссылка: {link}")
            continue

        filtered.append(result)
        seen_urls.add(link)

    return filtered


def save_to_markdown(results: List[Dict[str, str]], filename: str, query: str):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# Результаты поиска по запросу: {query}\n\n")
        for result in results:
            title = result.get("title", "Без заголовка")
            link = result.get("link", "")
            f.write(f"## [{title}]({link})\n")
            f.write(f"`{link}`\n\n")
            f.write("---\n\n")
    logging.info(f"Результаты сохранены в файл {filename}")


async def main():
    searcher = DuckDuckGoSearcher()
    query = "Python разработчик"

    raw_results = await searcher.search(query, max_results=100)

    if raw_results:
        logging.info(f"Найдено {len(raw_results)} результатов до обработки.")

        processed_results = filter_and_deduplicate_results(raw_results)
        logging.info(
            f"Осталось {len(processed_results)} результатов после фильтрации и удаления дубликатов."
        )

        if processed_results:
            save_to_markdown(
                processed_results, "clean_job_results_2025-09-15.md", query
            )
        else:
            logging.warning("После обработки не осталось релевантных результатов.")
    else:
        logging.error("Не удалось получить результаты поиска.")


if __name__ == "__main__":
    asyncio.run(main())
