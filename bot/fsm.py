from aiogram.fsm.state import State, StatesGroup


class SubscriptionStates(StatesGroup):
    waiting_for_name = State()
    configuring_rabota_filters = State()
    waiting_for_rabota_salary = State()
    configuring_habr_filters = State()
    waiting_for_habr_salary = State()
    configuring_belmeta_filters = State()
    configuring_praca_filters = State()
    waiting_for_praca_salary = State()


class EditSubscriptionStates(StatesGroup):
    waiting_for_new_value = State()


class DorkSearchStates(StatesGroup):
    waiting_for_keyword = State()


class CombinedSubscriptionStates(StatesGroup):
    waiting_for_name = State()
    configuring_platform = State()
