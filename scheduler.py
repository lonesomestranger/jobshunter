import asyncio
import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from curl_cffi.requests import AsyncSession as CurlSession
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from bot.keyboards import vacancy_notification_keyboard
from config import settings
from database.models import User, Vacancy
from scrapers.belmeta_scraper import BelmetaScraper
from scrapers.devby_scraper import DevbyScraper
from scrapers.habr_scraper import HabrScraper
from scrapers.praca_scraper import PracaScraper
from scrapers.rabota_scraper import RabotaScraper

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def check_for_updates(
    bot: Bot, session_factory: async_sessionmaker[AsyncSession]
):
    logging.info("Scheduler job started: Checking for new items...")
    async with session_factory() as session:
        query = select(User).options(selectinload(User.subscriptions))
        result = await session.execute(query)
        users_with_subscriptions = result.scalars().all()

        if not users_with_subscriptions:
            logging.info("No users with subscriptions found. Skipping check.")
            return

        async with CurlSession() as curl_session:
            for user in users_with_subscriptions:
                if not user.subscriptions:
                    continue

                logging.info(f"Checking subscriptions for user {user.telegram_id}...")
                for sub in user.subscriptions:
                    try:
                        scraper_instance = None
                        params_for_scraper = {}
                        keyword = None

                        if sub.search_type == "rabota_by":
                            search_config = sub.search_params
                            city = search_config.get("city", "minsk")
                            params_for_scraper = search_config.get("params", {})
                            keyword = params_for_scraper.get("text", "").lower()
                            scraper_instance = RabotaScraper(city=city)
                        elif sub.search_type == "habr_career":
                            params_for_scraper = sub.search_params
                            keyword = params_for_scraper.get("q", "").lower()
                            scraper_instance = HabrScraper()
                        elif sub.search_type == "dev_by":
                            params_for_scraper = {}
                            keyword = sub.search_params.get("q", "").lower()
                            scraper_instance = DevbyScraper()
                        elif sub.search_type == "belmeta_com":
                            params_for_scraper = sub.search_params
                            keyword = params_for_scraper.get("q", "").lower()
                            scraper_instance = BelmetaScraper()
                        elif sub.search_type == "praca_by":
                            params_for_scraper = sub.search_params
                            keyword = params_for_scraper.get("query", "").lower()
                            scraper_instance = PracaScraper()

                        if not scraper_instance:
                            continue

                        known_urls_query = select(Vacancy.url).where(
                            Vacancy.subscription_id == sub.id
                        )
                        known_urls_result = await session.execute(known_urls_query)
                        known_urls = {url for (url,) in known_urls_result}

                        (
                            urls_on_page,
                            _,
                        ) = await scraper_instance.get_vacancy_urls_from_page(
                            curl_session, params_for_scraper, page=0
                        )

                        if (
                            hasattr(scraper_instance, "captcha_detected_in_session")
                            and scraper_instance.captcha_detected_in_session
                        ):
                            logging.error(
                                f"CAPTCHA detected for sub '{sub.name}'. Skipping."
                            )
                            continue

                        if urls_on_page is None:
                            continue

                        new_urls = [
                            url for url in urls_on_page if url and url not in known_urls
                        ]
                        if not new_urls:
                            logging.info(
                                f"No new vacancies for sub '{sub.name}' of user {user.telegram_id}."
                            )
                            continue

                        logging.info(
                            f"Found {len(new_urls)} new vacancies for '{sub.name}'. Scraping details..."
                        )
                        processed_count = 0
                        for url in new_urls:
                            if (
                                hasattr(scraper_instance, "captcha_detected_in_session")
                                and scraper_instance.captcha_detected_in_session
                            ):
                                logging.error(
                                    f"CAPTCHA detected during details scraping. Aborting for sub '{sub.name}'."
                                )
                                break

                            details = await scraper_instance.scrape_vacancy_details(
                                curl_session, url
                            )
                            if details:
                                if sub.search_type == "dev_by" and keyword:
                                    title_lower = details.get("title", "").lower()
                                    desc_lower = details.get("description", "").lower()
                                    if (
                                        keyword not in title_lower
                                        and keyword not in desc_lower
                                    ):
                                        continue

                                new_vacancy = Vacancy(
                                    url=details["url"],
                                    title=details["title"],
                                    company=details["company"],
                                    salary=details["salary"],
                                    location=details["location"],
                                    description=details["description"],
                                    subscription_id=sub.id,
                                )
                                session.add(new_vacancy)
                                processed_count += 1
                                message_text = (
                                    f"<b>🔔 Новая вакансия по подписке «{sub.name}»</b>\n\n"
                                    f"<b><a href='{details['url']}'>{details['title']}</a></b>\n"
                                    f"🏢 Компания: {details['company']}\n💰 Зарплата: {details['salary']}\n"
                                    f"📍 Локация: {details['location']}\n\n<i>{details['description'][:400]}...</i>"
                                )
                                keyboard = vacancy_notification_keyboard(
                                    view_url=details["url"],
                                    apply_url=details["apply_url"],
                                )
                                await bot.send_message(
                                    user.telegram_id,
                                    message_text,
                                    reply_markup=keyboard,
                                    disable_web_page_preview=True,
                                )
                                await asyncio.sleep(1)

                        if processed_count > 0:
                            await session.commit()
                            logging.info(
                                f"Successfully processed and saved {processed_count} new vacancies for '{sub.name}'."
                            )

                    except Exception as e:
                        logging.error(
                            f"An error occurred while processing subscription '{sub.name}' for user {user.telegram_id}: {e}",
                            exc_info=True,
                        )
                        await session.rollback()

    logging.info("Scheduler job finished.")


def setup_scheduler(
    bot: Bot, session_factory: async_sessionmaker[AsyncSession]
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Minsk")
    scheduler.add_job(
        check_for_updates,
        "interval",
        minutes=settings.SCHEDULER_INTERVAL_MINUTES,
        kwargs={"bot": bot, "session_factory": session_factory},
    )
    return scheduler
