"""Демонстрация API редстоуна без GUI."""

from __future__ import annotations

from redstone import Action, RedstoneEngine, RedstoneMessage


def run_demo() -> None:
    engine = RedstoneEngine()

    # 1. Генерация блоков через данные
    engine.process({
        "состояние": "активен",
        "координата_воздействия": [0, 0, 0],
        "передаваемые_данные": {
            "действие": Action.GENERATE.value,
            "тип": "генератор",
            "данные": {"сигнал": 1},
        },
    })
    engine.process({
        "состояние": "активен",
        "координата_воздействия": [1, 0, 0],
        "передаваемые_данные": {
            "действие": Action.GENERATE.value,
            "тип": "реле",
        },
    })

    # 2. Соединение
    engine.process({
        "координата_воздействия": [0, 0, 0],
        "передаваемые_данные": {
            "действие": Action.CONNECT.value,
            "цель": engine.world.get(1, 0, 0).block_id,
        },
    })

    # 3. Выделение группы цветом
    engine.process({
        "состояние": "выделена",
        "координата_воздействия": [0, 0, 0],
        "передаваемые_данные": {
            "действие": Action.SELECT_GROUP.value,
            "цвет": "#FFD600",
        },
    })

    # 4. Передача данных
    result = engine.transfer_between((0, 0, 0), (1, 0, 0), {"сигнал": 42, "вложенность": {"a": {"b": 1}}})
    print("Передача:", result)

    # 5. Команда внутри блока
    engine.inject_block_command(0, 0, 0, {
        "состояние": "сохранение",
        "передаваемые_данные": {"действие": Action.SAVE.value},
    })

    # 6. Блокировка передачи мышью (эмуляция)
    engine.handle_mouse(1, 0, 0, button=1, modifiers={"alt": True})

    # 7. Перемещение данных по соединённой группе
    engine.process({
        "состояние": "передача",
        "координата_воздействия": [0, 0, 0],
        "передаваемые_данные": {
            "действие": Action.MOVE_DATA.value,
            "данные": {"пакет": {"уровень1": {"уровень2": "значение"}}},
        },
    })

    print("Мир:", engine.world.to_dict())
    print("Журнал событий:", len(engine.event_log), "записей")


if __name__ == "__main__":
    run_demo()
