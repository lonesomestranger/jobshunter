import asyncio
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.fsm import DorkSearchStates
from scrapers.duckduckgo_searcher import DuckDuckGoSearcher

router = Router()

DORK_TEMPLATES = [
    '(intitle:"вакансии" OR intitle:"карьера" OR intitle:"работа у нас" OR intitle:"открытые вакансии" OR intitle:"jobs" OR intitle:"careers" OR inurl:career OR inurl:vacancies OR inurl:jobs) "{keyword}" -site:hh.ru -site:rabota.by -site:dev.by -site:habr.com -site:linkedin.com',
    '("вакансии" OR "карьера в компании" OR "работа у нас" OR "ищем в команду") "{keyword}" -site:hh.ru -site:rabota.by -site:dev.by -site:habr.com -site:linkedin.com',
    '("откликнуться на вакансию" OR "отправить резюме" OR "заполнить анкету") "{keyword}" -site:hh.ru -site:rabota.by -site:dev.by -site:habr.com -site:linkedin.com',
    '(intitle:"вакансия" OR intitle:"вакансии" OR inurl:"career" OR inurl:"vacancies") "{keyword}" -site:rabota.by -site:hh.ru -site:dev.by -site:habr.com -site:linkedin.com',
    'вакансия работа карьера career ищем в команду work with us {keyword}" -site:rabota.by -site:hh.ru -site:dev.by -site:habr.com -site:linkedin.com',
]


@router.callback_query(F.data == "dork_search")
async def start_dork_search(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DorkSearchStates.waiting_for_keyword)
    await callback.message.edit_text(
        "Введите ключевое слово для поиска (например, 'Python разработчик' или 'Бухгалтер').\n\n"
        "Бот автоматически выполнит поиск по нескольким мощным запросам для нахождения вакансий на сайтах компаний."
    )
    await callback.answer()


@router.message(DorkSearchStates.waiting_for_keyword)
async def execute_dork_search(
    message: Message, state: FSMContext, session: AsyncSession
):
    keyword = message.text.strip()
    await state.clear()

    status_message = await message.answer(
        f"⏳ Выполняю поиск по ключевому слову: '{keyword}'..."
    )

    try:
        searcher = DuckDuckGoSearcher()
        all_results = []
        seen_links = set()
        total_dorks = len(DORK_TEMPLATES)

        for i, template in enumerate(DORK_TEMPLATES):
            await status_message.edit_text(
                f"⏳ Выполняю поиск... ({i + 1}/{total_dorks})\nКлючевое слово: '{keyword}'"
            )
            query_text = template.format(keyword=keyword)
            results = await searcher.search(query_text)

            if results:
                for item in results:
                    if item["link"] not in seen_links:
                        all_results.append(item)
                        seen_links.add(item["link"])

            if i < total_dorks - 1:
                await asyncio.sleep(2)

        if not all_results:
            await status_message.edit_text("😕 По вашему запросу ничего не найдено.")
            return

        md_content = f"# Результаты поиска по запросу: {keyword}\n\n"
        for item in all_results:
            md_content += f"## [{item['title']}]({item['link']})\n"
            md_content += f"`{item['link']}`\n\n---\n\n"

        file_data = md_content.encode("utf-8")
        timestamp = datetime.now().strftime("%Y-%m-%d")
        input_file = BufferedInputFile(
            file_data, filename=f"dork_results_{keyword}_{timestamp}.md"
        )

        await message.bot.send_document(
            message.from_user.id,
            input_file,
            caption=f"📄 Результаты поиска по вашему запросу: «{keyword}»",
        )
        await status_message.delete()

    except Exception as e:
        await status_message.edit_text(f"❌ Произошла ошибка при поиске: {e}")
