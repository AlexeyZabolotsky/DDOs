"""Графический интерфейс (tkinter) для редстоун-мира.

Мышь не работает с блоками напрямую: каждый клик собирает сообщение
формата {"состояние": ..., "координата": (x, y, z), "данные": {...}}
и отправляет его в ``World.dispatch`` — тот же путь, по которому идут
сообщения из «программ» внутри блоков.

Управление:
    * слева — палитра инструментов (каждый инструмент = состояние);
    * ЛКМ — применить инструмент (для выделения/перемещения — тянуть);
    * ПКМ — уничтожить блок под курсором;
    * колесо/поле Z — переключение слоя по оси Z;
    * наведение мыши — данные блока в строке состояния.
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog
from typing import Optional, Tuple

from redstone.core import Coord, World, СОСТОЯНИЯ, сообщение

КЛЕТКА = 36          # размер клетки в пикселях
СЕТКА = 16           # клеток по каждой оси на экране

ИНСТРУМЕНТЫ = [
    ("Генерация", СОСТОЯНИЯ["ГЕНЕРАЦИЯ"]),
    ("Уничтожение", СОСТОЯНИЯ["УНИЧТОЖЕНИЕ"]),
    ("Сохранение", СОСТОЯНИЯ["СОХРАНЕНИЕ"]),
    ("Стирание", СОСТОЯНИЯ["СТИРАНИЕ"]),
    ("Передача", СОСТОЯНИЯ["ПЕРЕДАЧА"]),
    ("Блокировка", СОСТОЯНИЯ["БЛОКИРОВКА"]),
    ("Разблокировка", СОСТОЯНИЯ["РАЗБЛОКИРОВКА"]),
    ("Выделение", СОСТОЯНИЯ["ВЫДЕЛЕНИЕ"]),
    ("Снять выделение", СОСТОЯНИЯ["СНЯТИЕ_ВЫДЕЛЕНИЯ"]),
    ("Соединение", СОСТОЯНИЯ["СОЕДИНЕНИЕ"]),
    ("Разъединение", СОСТОЯНИЯ["РАЗЪЕДИНЕНИЕ"]),
    ("Перемещение", СОСТОЯНИЯ["ПЕРЕМЕЩЕНИЕ"]),
]


class RedstoneApp:
    def __init__(self, world: Optional[World] = None) -> None:
        self.world = world or World()
        self.world.наблюдатели.append(lambda msg: self.перерисовать())

        self.инструмент = СОСТОЯНИЯ["ГЕНЕРАЦИЯ"]
        self.слой_z = 0
        self.цвет_выделения = "#ffd54f"
        # Промежуточные точки для двухшаговых инструментов.
        self._первая_точка: Optional[Coord] = None   # соединение/разъединение
        self._начало_тяги: Optional[Coord] = None    # выделение/перемещение

        self.root = tk.Tk()
        self.root.title("Редстоун на Python")
        self._построить_интерфейс()
        self.перерисовать()

    # ------------------------------------------------------------------ UI ---
    def _построить_интерфейс(self) -> None:
        панель = tk.Frame(self.root, padx=6, pady=6)
        панель.pack(side=tk.LEFT, fill=tk.Y)

        tk.Label(панель, text="Инструменты", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self._кнопки = {}
        for имя, состояние in ИНСТРУМЕНТЫ:
            b = tk.Button(панель, text=имя, width=16,
                          command=lambda s=состояние: self.выбрать_инструмент(s))
            b.pack(pady=1)
            self._кнопки[состояние] = b

        tk.Label(панель, text="").pack()
        tk.Button(панель, text="Цвет выделения…", width=16,
                  command=self.выбрать_цвет).pack(pady=1)
        self._метка_цвета = tk.Label(панель, text="      ", bg=self.цвет_выделения)
        self._метка_цвета.pack(pady=1)

        кадр_z = tk.Frame(панель)
        кадр_z.pack(pady=4)
        tk.Label(кадр_z, text="Слой Z:").pack(side=tk.LEFT)
        self._спин_z = tk.Spinbox(кадр_z, from_=-64, to=64, width=4,
                                  command=self._сменить_слой)
        self._спин_z.delete(0, tk.END)
        self._спин_z.insert(0, "0")
        self._спин_z.pack(side=tk.LEFT)

        tk.Label(панель, text="").pack()
        tk.Button(панель, text="Сохранить мир…", width=16,
                  command=self.сохранить_мир).pack(pady=1)
        tk.Button(панель, text="Загрузить мир…", width=16,
                  command=self.загрузить_мир).pack(pady=1)

        self.canvas = tk.Canvas(self.root, width=СЕТКА * КЛЕТКА,
                                height=СЕТКА * КЛЕТКА, bg="#1e1e1e",
                                highlightthickness=0)
        self.canvas.pack(side=tk.TOP, padx=6, pady=6)
        self.canvas.bind("<Button-1>", self._лкм_нажатие)
        self.canvas.bind("<ButtonRelease-1>", self._лкм_отпускание)
        self.canvas.bind("<Button-3>", self._пкм)
        self.canvas.bind("<Motion>", self._наведение)

        self.статус = tk.Label(self.root, anchor="w", justify=tk.LEFT,
                               font=("TkFixedFont", 9))
        self.статус.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=(0, 6))

        self.выбрать_инструмент(self.инструмент)

    def выбрать_инструмент(self, состояние: str) -> None:
        self.инструмент = состояние
        self._первая_точка = None
        for s, b in self._кнопки.items():
            b.config(relief=tk.SUNKEN if s == состояние else tk.RAISED)
        self._статус(f"Инструмент: {состояние}")

    def выбрать_цвет(self) -> None:
        цвет = colorchooser.askcolor(self.цвет_выделения)[1]
        if цвет:
            self.цвет_выделения = цвет
            self._метка_цвета.config(bg=цвет)

    def _сменить_слой(self) -> None:
        try:
            self.слой_z = int(self._спин_z.get())
        except ValueError:
            self.слой_z = 0
        self.перерисовать()

    # ------------------------------------------------------- события мыши ---
    def _координата(self, event: tk.Event) -> Coord:
        return (event.x // КЛЕТКА, event.y // КЛЕТКА, self.слой_z)

    def _лкм_нажатие(self, event: tk.Event) -> None:
        c = self._координата(event)
        if self.инструмент in (СОСТОЯНИЯ["ВЫДЕЛЕНИЕ"], СОСТОЯНИЯ["ПЕРЕМЕЩЕНИЕ"]):
            self._начало_тяги = c
            return
        self._применить_инструмент(c)

    def _лкм_отпускание(self, event: tk.Event) -> None:
        if self._начало_тяги is None:
            return
        начало, конец = self._начало_тяги, self._координата(event)
        self._начало_тяги = None

        if self.инструмент == СОСТОЯНИЯ["ВЫДЕЛЕНИЕ"]:
            self._отправить(сообщение(
                СОСТОЯНИЯ["ВЫДЕЛЕНИЕ"], начало,
                {"область": [list(начало), list(конец)],
                 "цвет": self.цвет_выделения},
            ))
        elif self.инструмент == СОСТОЯНИЯ["ПЕРЕМЕЩЕНИЕ"]:
            сдвиг = tuple(конец[i] - начало[i] for i in range(3))
            self._отправить(сообщение(
                СОСТОЯНИЯ["ПЕРЕМЕЩЕНИЕ"], начало,
                {"сдвиг": list(сдвиг)},
            ))

    def _пкм(self, event: tk.Event) -> None:
        self._отправить(сообщение(СОСТОЯНИЯ["УНИЧТОЖЕНИЕ"], self._координата(event)))

    def _применить_инструмент(self, c: Coord) -> None:
        s = self.инструмент
        if s == СОСТОЯНИЯ["ГЕНЕРАЦИЯ"]:
            self._отправить(сообщение(s, c, {"цвет": "#9e9e9e"}))
        elif s in (СОСТОЯНИЯ["УНИЧТОЖЕНИЕ"], СОСТОЯНИЯ["БЛОКИРОВКА"],
                   СОСТОЯНИЯ["РАЗБЛОКИРОВКА"]):
            self._отправить(сообщение(s, c))
        elif s == СОСТОЯНИЯ["СОХРАНЕНИЕ"]:
            данные = self._спросить_json(
                "Сохранение данных",
                'Данные (JSON любой вложенности), например\n'
                '{"программа": [...], "метки": {"a": {"b": 1}}}:')
            if данные is not None:
                self._отправить(сообщение(s, c, данные))
        elif s == СОСТОЯНИЯ["СТИРАНИЕ"]:
            ответ = simpledialog.askstring(
                "Стирание", "Ключи через запятую (пусто — стереть всё):",
                parent=self.root)
            if ответ is None:
                return
            ключи = [k.strip() for k in ответ.split(",") if k.strip()]
            self._отправить(сообщение(s, c, {"ключи": ключи} if ключи else {}))
        elif s == СОСТОЯНИЯ["ПЕРЕДАЧА"]:
            данные = self._спросить_json(
                "Передача данных",
                'Передаваемые данные (JSON), например {"сигнал": {"уровень": 15}}:')
            if данные is not None:
                self._отправить(сообщение(s, c, данные))
        elif s == СОСТОЯНИЯ["СНЯТИЕ_ВЫДЕЛЕНИЯ"]:
            self._отправить(сообщение(s, c, {"все": True}))
        elif s in (СОСТОЯНИЯ["СОЕДИНЕНИЕ"], СОСТОЯНИЯ["РАЗЪЕДИНЕНИЕ"]):
            if self._первая_точка is None:
                self._первая_точка = c
                self._статус(f"{s}: первый блок {c}, кликните второй")
            else:
                первый, self._первая_точка = self._первая_точка, None
                self._отправить(сообщение(s, первый, {"с": list(c)}))

    def _отправить(self, msg: dict) -> None:
        try:
            self.world.dispatch(msg)
            self._статус(f"→ {json.dumps(msg, ensure_ascii=False, default=list)}")
        except (KeyError, ValueError) as exc:
            self._статус(f"Ошибка: {exc}")

    # ----------------------------------------------------------- отрисовка ---
    def перерисовать(self) -> None:
        cv = self.canvas
        cv.delete("all")
        for i in range(СЕТКА + 1):
            cv.create_line(i * КЛЕТКА, 0, i * КЛЕТКА, СЕТКА * КЛЕТКА, fill="#333")
            cv.create_line(0, i * КЛЕТКА, СЕТКА * КЛЕТКА, i * КЛЕТКА, fill="#333")

        # Линии соединений текущего слоя.
        for c, блок in self.world.блоки.items():
            if c[2] != self.слой_z:
                continue
            for сосед in блок.соединения:
                if сосед[2] != self.слой_z or сосед <= c:
                    continue
                cv.create_line(
                    c[0] * КЛЕТКА + КЛЕТКА // 2, c[1] * КЛЕТКА + КЛЕТКА // 2,
                    сосед[0] * КЛЕТКА + КЛЕТКА // 2, сосед[1] * КЛЕТКА + КЛЕТКА // 2,
                    fill="#80cbc4", width=2)

        for c, блок in self.world.блоки.items():
            if c[2] != self.слой_z:
                continue
            x0, y0 = c[0] * КЛЕТКА + 3, c[1] * КЛЕТКА + 3
            x1, y1 = x0 + КЛЕТКА - 6, y0 + КЛЕТКА - 6
            контур = "#ffffff" if блок.выделен else "#000000"
            ширина = 3 if блок.выделен else 1
            cv.create_rectangle(x0, y0, x1, y1, fill=блок.цвет,
                                outline=контур, width=ширина)
            if блок.заблокирован:
                cv.create_line(x0, y0, x1, y1, fill="#e53935", width=2)
                cv.create_line(x0, y1, x1, y0, fill="#e53935", width=2)
            if блок.сигнал is not None:
                cv.create_oval(x1 - 9, y0, x1, y0 + 9, fill="#ff5252", outline="")
            if блок.память:
                cv.create_oval(x0, y0, x0 + 9, y0 + 9, fill="#40c4ff", outline="")

    # ------------------------------------------------------------- сервис ---
    def _наведение(self, event: tk.Event) -> None:
        c = self._координата(event)
        блок = self.world.блоки.get(c)
        if блок is None:
            self._статус(f"{c}: пусто")
        else:
            self._статус(
                f"{c} цвет={блок.цвет} заблокирован={блок.заблокирован} "
                f"память={json.dumps(блок.память, ensure_ascii=False)} "
                f"сигнал={json.dumps(блок.сигнал, ensure_ascii=False)}")

    def _статус(self, текст: str) -> None:
        self.статус.config(text=текст[:300])

    def _спросить_json(self, заголовок: str, подсказка: str) -> Optional[dict]:
        ответ = simpledialog.askstring(заголовок, подсказка, parent=self.root)
        if ответ is None:
            return None
        if not ответ.strip():
            return {}
        try:
            данные = json.loads(ответ)
            if not isinstance(данные, dict):
                raise ValueError("ожидается JSON-объект")
            return данные
        except (json.JSONDecodeError, ValueError) as exc:
            messagebox.showerror("Некорректный JSON", str(exc), parent=self.root)
            return None

    def сохранить_мир(self) -> None:
        путь = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if путь:
            self.world.save(путь)
            self._статус(f"Мир сохранён: {путь}")

    def загрузить_мир(self) -> None:
        путь = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if путь:
            self.world = World.load(путь)
            self.world.наблюдатели.append(lambda msg: self.перерисовать())
            self.перерисовать()
            self._статус(f"Мир загружен: {путь}")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    RedstoneApp().run()


if __name__ == "__main__":
    main()
