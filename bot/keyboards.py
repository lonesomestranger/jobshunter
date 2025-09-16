import json
from collections import defaultdict

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

with open("filters.json", "r", encoding="utf-8") as f:
    ALL_FILTERS = json.load(f)


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="☰ Меню"))
    return builder.as_markup(resize_keyboard=True)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="➕ Создать подписку", callback_data="new_subscription"
        )
    )
    builder.row(
        InlineKeyboardButton(text="📋 Мои подписки", callback_data="my_subscriptions")
    )
    builder.row(
        InlineKeyboardButton(text="🔍 Поиск Google Dork", callback_data="dork_search")
    )
    return builder.as_markup()


def subscription_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    services = [
        ("rabota_by", "Поиск на Rabota.by"),
        ("habr_career", "Поиск на Habr Career"),
        ("dev_by", "Поиск на dev.by"),
        ("belmeta_com", "Поиск на Belmeta.com"),
        ("praca_by", "Поиск на Praca.by"),
        ("all_sites", "Поиск на всех сайтах"),
    ]
    for service_key, service_name in services:
        builder.button(text=service_name, callback_data=f"sub_type:{service_key}")
    builder.adjust(2)
    return builder.as_markup()


def subscription_list_keyboard(subscriptions: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    service_map = {
        "rabota_by": "RB",
        "habr_career": "Habr",
        "dev_by": "Dev",
        "belmeta_com": "BM",
        "praca_by": "Praca",
    }

    grouped_subs = defaultdict(list)
    for sub in subscriptions:
        grouped_subs[sub.name].append(sub)

    buttons_to_add = []
    for name, subs_in_group in grouped_subs.items():
        if len(subs_in_group) > 1:
            services = sorted(
                [service_map.get(s.search_type, "??") for s in subs_in_group]
            )
            button_text = f"{name} ({', '.join(services)})"
            buttons_to_add.append(
                InlineKeyboardButton(
                    text=button_text, callback_data=f"view_sub_group:{name}"
                )
            )
        else:
            sub = subs_in_group[0]
            service_short_name = service_map.get(sub.search_type, "??")
            button_text = f"{sub.name} ({service_short_name})"
            buttons_to_add.append(
                InlineKeyboardButton(
                    text=button_text, callback_data=f"view_sub:{sub.id}"
                )
            )

    builder.add(*buttons_to_add)
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="start")
    )
    return builder.as_markup()


def subscription_detail_keyboard(sub_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📥 Экспорт", callback_data=f"export_menu:{sub_id}")
    builder.button(text="✏️ Редактировать", callback_data=f"edit_sub:{sub_id}")
    builder.button(text="❌ Удалить", callback_data=f"delete_sub_{sub_id}")
    builder.button(text="⬅️ Назад к списку", callback_data="my_subscriptions")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def subscription_group_detail_keyboard(group_name: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📥 Экспорт группы", callback_data=f"export_group_menu:{group_name}"
    )
    builder.button(
        text="❌ Удалить группу", callback_data=f"delete_sub_group:{group_name}"
    )
    builder.button(text="⬅️ Назад к списку", callback_data="my_subscriptions")
    builder.adjust(1)
    return builder.as_markup()


def export_format_keyboard(sub_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="CSV", callback_data=f"export_to:{sub_id}:csv")
    builder.button(text="Markdown", callback_data=f"export_to:{sub_id}:md")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к деталям", callback_data=f"view_sub:{sub_id}"
        )
    )
    return builder.as_markup()


def export_group_format_keyboard(group_name: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="CSV", callback_data=f"export_group_to:{group_name}:csv")
    builder.button(text="Markdown", callback_data=f"export_group_to:{group_name}:md")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к деталям", callback_data=f"view_sub_group:{group_name}"
        )
    )
    return builder.as_markup()


def city_selection_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    regions = {
        "all_with_hh": "Вся Беларусь (с hh.ru)",
        "all_rb_only": "Вся Беларусь (только РБ)",
        "minsk": "Минск",
        "gomel": "Гомель",
        "brest": "Брест",
        "vitebsk": "Витебск",
        "grodno": "Гродно",
        "mogilev": "Могилев",
    }
    for key, label in regions.items():
        builder.button(text=label, callback_data=f"city_{key}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к фильтрам", callback_data="rabota_config:back"
        )
    )
    return builder.as_markup()


def rabota_config_keyboard(params: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

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
    city_name = city_labels.get(params.get("original_city_choice"), "Не выбран")
    builder.button(text=f"Регион: {city_name}", callback_data="rabota_config:city")

    for key, info in ALL_FILTERS["rabota_by"].items():
        label = info["label"]
        param_name = info["param_name"]
        value_text = ""
        if param_name in params.get("params", {}):
            value = params["params"][param_name]
            if info["type"] == "text_input":
                value_text = f": {value}"
            else:
                values = value if isinstance(value, list) else [value]
                value_text = f": ({len(values)})"
        builder.button(
            text=f"{label}{value_text}", callback_data=f"rabota_config:{key}"
        )

    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(
            text="✅ Сохранить подписку", callback_data="rabota_finish"
        )
    )
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="start"))
    return builder.as_markup()


def rabota_filter_options_keyboard(
    param_key: str, selected_values: list
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    param_info = ALL_FILTERS["rabota_by"][param_key]
    for option in param_info["options"]:
        text = (
            f"✅ {option['label']}"
            if option["value"] in selected_values
            else option["label"]
        )
        builder.button(
            text=text, callback_data=f"rabota_select:{param_key}:{option['value']}"
        )

    builder.adjust(1 if param_info["type"] == "single_choice" else 2)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к фильтрам", callback_data="rabota_config:back"
        )
    )
    return builder.as_markup()


def rabota_salary_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к фильтрам", callback_data="rabota_config:back"
        )
    )
    return builder.as_markup()


def habr_config_keyboard(current_params: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, info in ALL_FILTERS["habr_career"].items():
        label = info["label"]
        value_text = ""
        if key in current_params and current_params[key]:
            if key == "salary":
                value_text = f": {current_params[key]}$"
            else:
                value = current_params[key]
                selected_count = len(value if isinstance(value, list) else [value])
                if selected_count > 0:
                    value_text = f": ({selected_count})"

        builder.button(text=f"{label}{value_text}", callback_data=f"habr_config:{key}")

    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="✅ Сохранить подписку", callback_data="habr_finish")
    )
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="start"))
    return builder.as_markup()


def habr_filter_options_keyboard(
    filter_key: str, selected_values: list
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    options = ALL_FILTERS["habr_career"][filter_key].get("options", [])

    for value, label in options:
        text = f"✅ {label}" if value in selected_values else label
        builder.button(text=text, callback_data=f"habr_select:{filter_key}:{value}")

    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к фильтрам", callback_data="habr_config:back"
        )
    )
    return builder.as_markup()


def habr_salary_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к фильтрам", callback_data="habr_config:back"
        )
    )
    return builder.as_markup()


def belmeta_config_keyboard(current_params: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, info in ALL_FILTERS["belmeta_com"].items():
        label = info["label"]
        value_text = ""
        if key == "l":
            region_value = current_params.get("l")
            if region_value:
                value_text = f": {region_value}"
            else:
                value_text = ": Вся Беларусь"
        elif key in current_params and current_params[key]:
            value = current_params[key]
            if info["type"] == "text_input":
                value_text = f": {value}"
            elif info["type"] == "single_choice":
                option = next(
                    (opt for opt in info["options"] if opt["value"] == value), None
                )
                value_text = f": {option['label']}" if option else ""
            else:
                values = value.split(",")
                value_text = f": ({len(values)})"
        builder.button(
            text=f"{label}{value_text}", callback_data=f"belmeta_config:{key}"
        )
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(
            text="✅ Сохранить подписку", callback_data="belmeta_finish"
        )
    )
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="start"))
    return builder.as_markup()


def belmeta_filter_options_keyboard(
    filter_key: str, selected_values: list
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    info = ALL_FILTERS["belmeta_com"][filter_key]

    if filter_key == "l":
        city_buttons = []
        for option in info["options"]:
            text = (
                f"✅ {option['label']}"
                if option["value"] in selected_values
                else option["label"]
            )
            city_buttons.append(
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"belmeta_select:{filter_key}:{option['value']}",
                )
            )
        builder.row(*city_buttons, width=2)

        all_belarus_selected = not selected_values
        text_all_belarus = "✅ Вся Беларусь" if all_belarus_selected else "Вся Беларусь"
        builder.row(
            InlineKeyboardButton(
                text=text_all_belarus,
                callback_data=f"belmeta_select:{filter_key}:all",
            )
        )
    else:
        for option in info["options"]:
            text = (
                f"✅ {option['label']}"
                if option["value"] in selected_values
                else option["label"]
            )
            builder.button(
                text=text,
                callback_data=f"belmeta_select:{filter_key}:{option['value']}",
            )
        builder.adjust(1 if info["type"] == "single_choice" else 2)

    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к фильтрам", callback_data="belmeta_config:back"
        )
    )
    return builder.as_markup()


def praca_config_keyboard(current_params: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, info in ALL_FILTERS["praca_by"].items():
        label = info["label"]
        value_text = ""
        if key in current_params and current_params[key]:
            value = current_params[key]
            if info["type"] == "text_input":
                value_text = f": {list(value.keys())[0]}"
            else:
                values = value if isinstance(value, dict) else {value: value}
                value_text = f": ({len(values)})"
        builder.button(text=f"{label}{value_text}", callback_data=f"praca_config:{key}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="✅ Сохранить подписку", callback_data="praca_finish")
    )
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="start"))
    return builder.as_markup()


def praca_filter_options_keyboard(
    filter_key: str, selected_values: dict
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    info = ALL_FILTERS["praca_by"][filter_key]

    if filter_key == "c_rad":
        all_belarus_selected = not selected_values
        text_all_belarus = "✅ Вся Беларусь" if all_belarus_selected else "Вся Беларусь"
        builder.row(
            InlineKeyboardButton(
                text=text_all_belarus,
                callback_data=f"praca_select:{filter_key}:all_belarus",
            )
        )

    for option in info["options"]:
        text = (
            f"✅ {option['label']}"
            if option["value"] in selected_values
            else option["label"]
        )
        builder.button(
            text=text, callback_data=f"praca_select:{filter_key}:{option['value']}"
        )
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к фильтрам", callback_data="praca_config:back"
        )
    )
    return builder.as_markup()


def praca_salary_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к фильтрам", callback_data="praca_config:back"
        )
    )
    return builder.as_markup()


def vacancy_notification_keyboard(
    view_url: str, apply_url: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👀 Посмотреть вакансию", url=view_url))
    if apply_url != view_url:
        builder.row(InlineKeyboardButton(text="✅ Откликнуться", url=apply_url))
    return builder.as_markup()
