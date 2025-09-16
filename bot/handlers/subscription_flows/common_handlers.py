import asyncio
import csv
import io
import json
import logging
import re
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from bs4 import BeautifulSoup
from markdownify import markdownify
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.fsm import CombinedSubscriptionStates, SubscriptionStates
from bot.keyboards import (
    belmeta_config_keyboard,
    export_format_keyboard,
    export_group_format_keyboard,
    habr_config_keyboard,
    praca_config_keyboard,
    rabota_config_keyboard,
    subscription_detail_keyboard,
    subscription_group_detail_keyboard,
    subscription_type_keyboard,
)
from database.models import Subscription, User
from scrapers.belmeta_scraper import BelmetaScraper
from scrapers.devby_scraper import DevbyScraper
from scrapers.habr_scraper import HabrScraper
from scrapers.praca_scraper import PracaScraper
from scrapers.rabota_scraper import RabotaScraper

router = Router()

with open("filters.json", "r", encoding="utf-8") as f:
    ALL_FILTERS = json.load(f)

PLATFORM_CONFIG = {
    "rabota_by": {
        "name": "Rabota.by",
        "state": SubscriptionStates.configuring_rabota_filters,
    },
    "habr_career": {
        "name": "Habr Career",
        "state": SubscriptionStates.configuring_habr_filters,
    },
    "dev_by": {"name": "dev.by", "no_filters": True},
    "belmeta_com": {
        "name": "Belmeta.com",
        "state": SubscriptionStates.configuring_belmeta_filters,
    },
    "praca_by": {
        "name": "Praca.by",
        "state": SubscriptionStates.configuring_praca_filters,
    },
}
PLATFORM_ORDER = ["rabota_by", "habr_career", "dev_by", "belmeta_com", "praca_by"]


def _generate_summary_text(subscription: Subscription) -> str:
    name = subscription.name
    params = subscription.search_params
    search_type = subscription.search_type
    filters = ALL_FILTERS.get(search_type, {})

    if search_type == "dev_by":
        keyword = params.get("q")
        if keyword:
            return f"<b>Подписка:</b> {name}\n<b>Фильтр по слову:</b> {keyword}"
        return f"<b>Подписка:</b> {name} (все вакансии)"

    if search_type == "praca_by":
        lines = [f"<b>Поисковый запрос:</b> {params.get('query', 'Не указан')}"]
        for key, info in filters.items():
            if key in params and params[key]:
                value = params[key]
                if info["type"] == "text_input":
                    lines.append(f"<b>{info['label']}:</b> {list(value.keys())[0]}")
                else:
                    selected_values = value.keys()
                    if key == "c_rad" and not selected_values:
                        lines.append(f"<b>{info['label']}:</b> Вся Беларусь")
                        continue
                    labels = [
                        opt["label"]
                        for opt in info["options"]
                        if opt["value"] in selected_values
                    ]
                    if labels:
                        lines.append(f"<b>{info['label']}:</b> {', '.join(labels)}")
        return "\n".join(lines)

    if search_type == "habr_career":
        lines = [f"<b>Поисковый запрос:</b> {params.get('q', 'Не указан')}"]
        for key, info in filters.items():
            if key in params and params[key]:
                value = params[key]
                if key == "salary":
                    lines.append(f"<b>{info['label']}:</b> от {value}$")
                else:
                    selected_labels = []
                    value_list = value if isinstance(value, list) else [value]
                    for v in value_list:
                        option_label = next(
                            (
                                label
                                for val, label in info.get("options", [])
                                if val == v
                            ),
                            v,
                        )
                        selected_labels.append(option_label)
                    if selected_labels:
                        lines.append(
                            f"<b>{info['label']}:</b> {', '.join(selected_labels)}"
                        )
        return "\n".join(lines)

    if search_type == "belmeta_com":
        lines = [f"<b>Поисковый запрос:</b> {params.get('q', 'Не указан')}"]
        for key, info in filters.items():
            if key == "l":
                region_value = params.get("l", "Вся Беларусь")
                lines.append(f"<b>{info['label']}:</b> {region_value}")
                continue

            if key in params and params[key]:
                value = params[key]
                if info["type"] == "text_input":
                    lines.append(f"<b>{info['label']}:</b> {value}")
                elif info["type"] == "single_choice":
                    option = next(
                        (opt for opt in info["options"] if opt["value"] == value), None
                    )
                    if option:
                        lines.append(f"<b>{info['label']}:</b> {option['label']}")
                else:
                    selected_values = value.split(",")
                    labels = [
                        opt["label"]
                        for opt in info["options"]
                        if opt["value"] in selected_values
                    ]
                    if labels:
                        lines.append(f"<b>{info['label']}:</b> {', '.join(labels)}")
        return "\n".join(lines)

    city_choice = params.get("original_city_choice", params.get("city", "minsk"))
    db_params = params.get("params", {})
    city_labels = {
        "all_with_hh": "Вся Беларусь (с hh.ru)",
        "all_rb_only": "Вся Беларусь (только РБ)",
        "minsk": "Минск",
        "gomel": "Гомель",
        "brest": "Брест",
        "vitebsk": "Витебск",
        "grodno": "Гродно",
        "mogilev": "Могилев",
    }
    city_name = city_labels.get(city_choice, "Не выбран")
    summary_lines = [f"<b>Поисковый запрос:</b> {name}", f"<b>Регион:</b> {city_name}"]

    for key, info in filters.items():
        param_name = info["param_name"]
        if param_name in db_params:
            values = db_params[param_name]
            if not isinstance(values, list):
                values = [values]

            labels = []
            if "options" in info and info["options"]:
                for v in values:
                    option = next(
                        (opt for opt in info["options"] if opt["value"] == str(v)), None
                    )
                    labels.append(option["label"] if option else v)
            else:
                labels = [str(v) for v in values]

            if labels:
                summary_lines.append(f"<b>{info['label']}:</b> {', '.join(labels)}")

    return "\n".join(summary_lines)


def _deduplicate_vacancies(vacancies: list[dict]) -> list[dict]:
    seen = set()
    deduplicated_list = []
    for vacancy in vacancies:
        company = vacancy.get("company", "").lower().strip()
        title = vacancy.get("title", "").lower().strip()
        if (company, title) not in seen:
            seen.add((company, title))
            deduplicated_list.append(vacancy)
    return deduplicated_list


async def _get_scraper_for_subscription(
    subscription: Subscription,
) -> tuple[
    RabotaScraper | HabrScraper | DevbyScraper | BelmetaScraper | PracaScraper | None,
    dict,
]:
    scraper, params = (None, None)
    if subscription.search_type == "rabota_by":
        search_config = subscription.search_params
        scraper = RabotaScraper(city=search_config.get("city", "minsk"))
        params = search_config.get("params", {})
    elif subscription.search_type == "habr_career":
        scraper = HabrScraper()
        params = subscription.search_params
    elif subscription.search_type == "dev_by":
        scraper = DevbyScraper()
        params = {}
    elif subscription.search_type == "belmeta_com":
        scraper = BelmetaScraper()
        params = subscription.search_params
    elif subscription.search_type == "praca_by":
        scraper = PracaScraper()
        params = subscription.search_params
    return scraper, params


async def _generate_export_file(
    vacancies: list[dict], file_format: str, name: str
) -> tuple[BufferedInputFile | None, str | None]:
    file_data, filename = (None, "")
    if not vacancies:
        return None, None

    processed_vacancies = []
    for vacancy in vacancies:
        processed_vacancy = vacancy.copy()
        processed_vacancy.pop("apply_url", None)

        description_html = processed_vacancy.get("description", "")
        if file_format == "md":
            processed_vacancy["description"] = markdownify(description_html)
        else:
            processed_vacancy["description"] = BeautifulSoup(
                description_html, "lxml"
            ).get_text(separator=" ", strip=True)
        processed_vacancies.append(processed_vacancy)

    if not processed_vacancies:
        return None, None

    if file_format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=processed_vacancies[0].keys())
        writer.writeheader()
        writer.writerows(processed_vacancies)
        file_data = output.getvalue().encode("utf-8")
        filename = f"vacancies_{name}.csv"
    elif file_format == "md":
        md_content = f"# Результаты по подписке: {name}\n\n"
        for item in processed_vacancies:
            md_content += f"## [{item.get('title', 'N/A')}]({item.get('url', '#')})\n\n"
            md_content += f"**Компания:** {item.get('company', 'N/A')}\n"
            md_content += f"**Зарплата:** {item.get('salary', 'N/A')}\n"
            md_content += f"**Локация:** {item.get('location', 'N/A')}\n\n"
            md_content += f"### Описание\n\n{item.get('description', 'N/A')}\n\n"
            md_content += "---\n\n"

        md_content = re.sub(r"\n{3,}", "\n\n", md_content).strip()
        file_data = md_content.encode("utf-8")
        timestamp = datetime.now().strftime("%Y-%m-%d")
        filename = f"vacancies_{name}_{timestamp}.md"

    if file_data and filename:
        return BufferedInputFile(file_data, filename=filename), filename
    return None, None


async def _continue_combined_setup(
    event: Message | CallbackQuery, state: FSMContext, user: User, session: AsyncSession
):
    data = await state.get_data()
    message = event if isinstance(event, Message) else event.message
    collected_configs = data["collected_configs"]
    sub_name = data["name"]

    if not collected_configs:
        await state.clear()
        return

    for platform_key, search_params in collected_configs.items():
        new_sub = Subscription(
            name=sub_name,
            search_type=platform_key,
            search_params=search_params,
            user_id=user.telegram_id,
        )
        session.add(new_sub)
    await session.commit()
    await state.clear()
    prompt_message_id = data.get("prompt_message_id")
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=prompt_message_id,
        text=f"✅ Группа подписок '{sub_name}' успешно создана/дополнена!",
    )
    from bot.handlers.user_commands import handle_start_menu

    await handle_start_menu(event, session)


async def _start_next_platform_configuration(
    message: Message, state: FSMContext, user: User, session: AsyncSession
):
    data = await state.get_data()
    platforms = data["platforms_to_configure"]
    current_index = data["current_platform_index"]

    if current_index >= len(platforms):
        await _continue_combined_setup(message, state, user, session)
        return

    platform_key = platforms[current_index]
    platform_info = PLATFORM_CONFIG[platform_key]
    sub_name = data["name"]
    prompt_message_id = data.get("prompt_message_id")

    if platform_info.get("no_filters"):
        collected_configs = data.get("collected_configs", {})
        collected_configs[platform_key] = {"q": ""}
        await state.update_data(
            collected_configs=collected_configs,
            current_platform_index=current_index + 1,
        )
        await _start_next_platform_configuration(message, state, user, session)
    else:
        await state.set_state(CombinedSubscriptionStates.configuring_platform)
        if platform_key == "rabota_by":
            base_params = {
                "params": {
                    "L_save_area": "true",
                    "search_field": ["name", "company_name", "description"],
                    "ored_clusters": "true",
                    "items_on_page": "50",
                    "text": sub_name,
                },
                "original_city_choice": None,
                "city": None,
            }
            await state.update_data(current_config_params=base_params)
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=prompt_message_id,
                text=f"Шаг {current_index + 1}/{len(platforms)}. Настройте фильтры для {platform_info['name']}:",
                reply_markup=rabota_config_keyboard(base_params),
            )
        elif platform_key == "habr_career":
            base_params = {"q": sub_name, "type": "all"}
            await state.update_data(current_config_params=base_params)
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=prompt_message_id,
                text=f"Шаг {current_index + 1}/{len(platforms)}. Настройте фильтры для {platform_info['name']}:",
                reply_markup=habr_config_keyboard(base_params),
            )
        elif platform_key == "belmeta_com":
            base_params = {"q": sub_name}
            await state.update_data(current_config_params=base_params)
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=prompt_message_id,
                text=f"Шаг {current_index + 1}/{len(platforms)}. Настройте фильтры для {platform_info['name']}:",
                reply_markup=belmeta_config_keyboard(base_params),
            )
        elif platform_key == "praca_by":
            base_params = {"query": sub_name}
            await state.update_data(current_config_params=base_params)
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=prompt_message_id,
                text=f"Шаг {current_index + 1}/{len(platforms)}. Настройте фильтры для {platform_info['name']}:",
                reply_markup=praca_config_keyboard(base_params),
            )


@router.callback_query(F.data == "new_subscription")
async def start_new_subscription(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Выберите сервис для создания подписки:",
        reply_markup=subscription_type_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub_type:"))
async def process_subscription_type(callback: CallbackQuery, state: FSMContext):
    sub_type = callback.data.split(":")[1]

    if sub_type == "all_sites":
        await state.set_state(CombinedSubscriptionStates.waiting_for_name)
        await state.update_data(
            platforms_to_configure=PLATFORM_ORDER,
            current_platform_index=0,
            collected_configs={},
        )
        prompt_text = "Вы выбрали поиск по всем сайтам. Введите общее название для этой группы подписок (например, 'Python разработчик')."
    else:
        await state.set_state(SubscriptionStates.waiting_for_name)
        await state.update_data(search_type=sub_type)
        prompt_text = "Введите текст для поиска (например, 'Python разработчик').\n\nЭтот текст также будет названием подписки."
        if sub_type == "dev_by":
            prompt_text = "Введите название для подписки (например, 'Все с devby')."

    prompt = await callback.message.edit_text(prompt_text, parse_mode="HTML")
    await state.update_data(prompt_message_id=prompt.message_id)
    await callback.answer()


@router.message(SubscriptionStates.waiting_for_name)
@router.message(CombinedSubscriptionStates.waiting_for_name)
async def process_subscription_name(
    message: Message, state: FSMContext, session: AsyncSession, user: User
):
    current_state = await state.get_state()
    is_combined_flow = current_state == CombinedSubscriptionStates.waiting_for_name
    user_input = message.text.strip()
    data = await state.get_data()

    if is_combined_flow:
        query = select(Subscription.search_type).where(
            Subscription.name == user_input, Subscription.user_id == user.telegram_id
        )
        result = await session.execute(query)
        existing_platforms = {row[0] for row in result.all()}
        platforms_to_configure = [
            p for p in PLATFORM_ORDER if p not in existing_platforms
        ]

        if not platforms_to_configure:
            await message.answer(
                f"Группа подписок '{user_input}' уже полностью настроена для всех сайтов."
            )
            await state.clear()
            return
        await state.update_data(platforms_to_configure=platforms_to_configure)
    else:
        sub_type = data["search_type"]
        query = select(Subscription).where(
            Subscription.name == user_input,
            Subscription.user_id == user.telegram_id,
            Subscription.search_type == sub_type,
        )
        if (await session.execute(query)).scalars().first():
            await message.answer(
                "Подписка с таким названием для этого сервиса уже существует. Пожалуйста, выберите другое."
            )
            return

    prompt_message_id = data.get("prompt_message_id")
    await message.delete()
    await state.update_data(name=user_input)

    if is_combined_flow:
        await _start_next_platform_configuration(message, state, user, session)
        return

    sub_type = data["search_type"]
    if sub_type == "dev_by":
        new_subscription = Subscription(
            name=user_input,
            search_type="dev_by",
            search_params={"q": ""},
            user_id=user.telegram_id,
        )
        session.add(new_subscription)
        await session.commit()
        await state.clear()
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text=f"✅ Подписка '{user_input}' на dev.by успешно создана!",
        )
        from bot.handlers.user_commands import handle_start_menu

        await handle_start_menu(message, session)
        return

    if sub_type == "rabota_by":
        base_params = {
            "params": {
                "L_save_area": "true",
                "search_field": ["name", "company_name", "description"],
                "ored_clusters": "true",
                "items_on_page": "50",
                "text": user_input,
            },
            "original_city_choice": None,
            "city": None,
        }
        await state.update_data(search_params=base_params)
        await state.set_state(SubscriptionStates.configuring_rabota_filters)
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text="Отлично! Теперь настройте фильтры для Rabota.by:",
            reply_markup=rabota_config_keyboard(base_params),
        )
    elif sub_type == "habr_career":
        await state.update_data(
            name=user_input, search_params={"q": user_input, "type": "all"}
        )
        await state.set_state(SubscriptionStates.configuring_habr_filters)
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text="Отлично! Теперь настройте фильтры для Habr Career:",
            reply_markup=habr_config_keyboard({"q": user_input}),
        )
    elif sub_type == "belmeta_com":
        await state.update_data(name=user_input, search_params={"q": user_input})
        await state.set_state(SubscriptionStates.configuring_belmeta_filters)
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text="Отлично! Теперь настройте фильтры для Belmeta.com:",
            reply_markup=belmeta_config_keyboard({"q": user_input}),
        )
    elif sub_type == "praca_by":
        await state.update_data(name=user_input, search_params={"query": user_input})
        await state.set_state(SubscriptionStates.configuring_praca_filters)
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text="Отлично! Теперь настройте фильтры для Praca.by:",
            reply_markup=praca_config_keyboard({"query": user_input}),
        )


@router.callback_query(F.data.startswith("view_sub:"))
async def view_subscription_details(
    callback: CallbackQuery, session: AsyncSession, user: User
):
    sub_id = int(callback.data.split(":")[1])
    query = select(Subscription).where(
        Subscription.id == sub_id, Subscription.user_id == user.telegram_id
    )
    subscription = (await session.execute(query)).scalars().first()
    if not subscription:
        await callback.answer("Подписка не найдена.", show_alert=True)
        return

    service_name = PLATFORM_CONFIG.get(subscription.search_type, {}).get("name", "N/A")
    summary = _generate_summary_text(subscription)

    await callback.message.edit_text(
        f"<b>Детали подписки ({service_name}):</b>\n\n{summary}",
        reply_markup=subscription_detail_keyboard(sub_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("view_sub_group:"))
async def view_subscription_group_details(
    callback: CallbackQuery, session: AsyncSession, user: User
):
    group_name = callback.data.split(":", 1)[1]
    query = (
        select(Subscription)
        .where(
            Subscription.name == group_name, Subscription.user_id == user.telegram_id
        )
        .order_by(Subscription.search_type)
    )
    subscriptions = (await session.execute(query)).scalars().all()
    if not subscriptions:
        await callback.answer("Группа подписок не найдена.", show_alert=True)
        return

    full_summary = f"<b>Детали группы подписок «{group_name}»:</b>\n\n"
    for sub in subscriptions:
        service_name = PLATFORM_CONFIG.get(sub.search_type, {}).get("name", "N/A")
        summary = _generate_summary_text(sub)
        full_summary += f"<b>--- {service_name} ---</b>\n{summary}\n\n"

    await callback.message.edit_text(
        full_summary.strip(),
        reply_markup=subscription_group_detail_keyboard(group_name),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_sub_group:"))
async def delete_subscription_group(
    callback: CallbackQuery, session: AsyncSession, user: User, state: FSMContext
):
    group_name = callback.data.split(":", 1)[1]
    await session.execute(
        delete(Subscription).where(
            Subscription.name == group_name, Subscription.user_id == user.telegram_id
        )
    )
    await session.commit()
    await callback.answer("Группа подписок удалена.", show_alert=True)
    from bot.handlers.user_commands import handle_my_subscriptions

    await handle_my_subscriptions(callback, session, user, state)


@router.callback_query(F.data.startswith("delete_sub_"))
async def delete_subscription(
    callback: CallbackQuery, session: AsyncSession, user: User, state: FSMContext
):
    sub_id = int(callback.data.split("_")[2])
    await session.execute(
        delete(Subscription).where(
            Subscription.id == sub_id, Subscription.user_id == user.telegram_id
        )
    )
    await session.commit()
    await callback.answer("Подписка удалена.", show_alert=True)
    from bot.handlers.user_commands import handle_my_subscriptions

    await handle_my_subscriptions(callback, session, user, state)


@router.callback_query(F.data.startswith("edit_sub:"))
async def start_editing_subscription(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    sub_id = int(callback.data.split(":")[1])
    query = select(Subscription).where(Subscription.id == sub_id)
    subscription = (await session.execute(query)).scalars().first()

    if not subscription:
        await callback.answer("Подписка не найдена.", show_alert=True)
        return

    if subscription.search_type == "dev_by":
        await callback.answer(
            "Для подписок dev.by редактирование не требуется.", show_alert=True
        )
        return

    await state.update_data(
        sub_id=sub_id,
        name=subscription.name,
        search_params=subscription.search_params,
        prompt_message_id=callback.message.message_id,
    )

    if subscription.search_type == "habr_career":
        await state.set_state(SubscriptionStates.configuring_habr_filters)
        await callback.message.edit_text(
            "Редактирование фильтров для Habr Career:",
            reply_markup=habr_config_keyboard(subscription.search_params),
        )
    elif subscription.search_type == "rabota_by":
        await state.set_state(SubscriptionStates.configuring_rabota_filters)
        await callback.message.edit_text(
            "Редактирование фильтров для Rabota.by:",
            reply_markup=rabota_config_keyboard(subscription.search_params),
        )
    elif subscription.search_type == "belmeta_com":
        await state.set_state(SubscriptionStates.configuring_belmeta_filters)
        await callback.message.edit_text(
            "Редактирование фильтров для Belmeta.com:",
            reply_markup=belmeta_config_keyboard(subscription.search_params),
        )
    elif subscription.search_type == "praca_by":
        await state.set_state(SubscriptionStates.configuring_praca_filters)
        await callback.message.edit_text(
            "Редактирование фильтров для Praca.by:",
            reply_markup=praca_config_keyboard(subscription.search_params),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("export_menu:"))
async def show_export_menu(callback: CallbackQuery):
    sub_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(
        "Выберите формат для экспорта:", reply_markup=export_format_keyboard(sub_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("export_group_menu:"))
async def show_group_export_menu(callback: CallbackQuery):
    group_name = callback.data.split(":", 1)[1]
    await callback.message.edit_text(
        "Выберите формат для экспорта:",
        reply_markup=export_group_format_keyboard(group_name),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("export_to:"))
async def export_subscription_to_file(
    callback: CallbackQuery, session: AsyncSession, user: User
):
    _, sub_id_str, export_format = callback.data.split(":")
    sub_id = int(sub_id_str)

    query = select(Subscription).where(
        Subscription.id == sub_id, Subscription.user_id == user.telegram_id
    )
    subscription = (await session.execute(query)).scalars().first()
    if not subscription:
        await callback.answer("Подписка не найдена.", show_alert=True)
        return

    await callback.message.edit_text("⏳ Собираю вакансии по вашему запросу...")
    await callback.answer()

    try:
        scraper, params = await _get_scraper_for_subscription(subscription)
        if not scraper:
            await callback.message.edit_text("❌ Неподдерживаемый тип подписки.")
            return

        vacancies = await scraper.scrape_all_vacancies(params)
        if not vacancies:
            await callback.message.edit_text("😕 По вашему запросу ничего не найдено.")
            return

        input_file, _ = await _generate_export_file(
            vacancies, export_format, subscription.name
        )
        if input_file:
            await callback.bot.send_document(callback.from_user.id, input_file)
            await callback.message.delete()
        else:
            await callback.message.edit_text("❌ Не удалось сформировать файл.")
    except Exception as e:
        logging.error(f"Failed to export subscription {sub_id}: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ Произошла ошибка: {e}")


@router.callback_query(F.data.startswith("export_group_to:"))
async def export_subscription_group_to_file(
    callback: CallbackQuery, session: AsyncSession, user: User
):
    _, group_name, export_format = callback.data.split(":")

    query = select(Subscription).where(
        Subscription.name == group_name, Subscription.user_id == user.telegram_id
    )
    subscriptions = (await session.execute(query)).scalars().all()
    if not subscriptions:
        await callback.answer("Группа подписок не найдена.", show_alert=True)
        return

    await callback.message.edit_text(
        "⏳ Собираю вакансии со всех сайтов. Это может занять некоторое время..."
    )
    await callback.answer()

    try:
        all_vacancies = []
        tasks = []

        async def scrape_and_collect(sub):
            scraper, params = await _get_scraper_for_subscription(sub)
            if scraper:
                return await scraper.scrape_all_vacancies(params)
            return []

        for sub in subscriptions:
            tasks.append(scrape_and_collect(sub))

        results = await asyncio.gather(*tasks)
        for result_list in results:
            all_vacancies.extend(result_list)

        if not all_vacancies:
            await callback.message.edit_text("😕 По вашему запросу ничего не найдено.")
            return

        deduplicated_vacancies = _deduplicate_vacancies(all_vacancies)
        logging.info(
            f"Total vacancies: {len(all_vacancies)}, after deduplication: {len(deduplicated_vacancies)}"
        )

        input_file, _ = await _generate_export_file(
            deduplicated_vacancies, export_format, group_name
        )
        if input_file:
            await callback.bot.send_document(callback.from_user.id, input_file)
            await callback.message.delete()
        else:
            await callback.message.edit_text("❌ Не удалось сформировать файл.")
    except Exception as e:
        logging.error(
            f"Failed to export subscription group {group_name}: {e}", exc_info=True
        )
        await callback.message.edit_text(f"❌ Произошла ошибка: {e}")
