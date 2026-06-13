"""3D-графический интерфейс (tkinter) для редстоун-мира — в стиле Minecraft.

Мир рисуется как набор воксельных кубов в изометрической проекции:
каждый блок — это куб с тремя видимыми гранями (верх — светлее, правый
бок — средний, левый бок — темнее), что даёт узнаваемый «майнкрафтовый»
объёмный вид. Слои по оси Z складываются друг на друга — можно строить
башни и многоэтажные конструкции.

Как и раньше, мышь не трогает блоки напрямую: каждый клик собирает
сообщение формата {"состояние": ..., "координата": (x, y, z),
"данные": {...}} и отправляет его в ``World.dispatch`` — тот же путь,
по которому идут сообщения из «программ» внутри блоков.

Управление:
    * слева — палитра инструментов (каждый инструмент = состояние);
    * ЛКМ — применить инструмент. Для «Генерации»: клик по верхней грани
      существующего куба ставит блок сверху (как в Minecraft), клик по
      пустому месту — ставит блок на активный слой Z;
    * ПКМ — уничтожить куб под курсором;
    * колесо мыши — переключение активного слоя Z;
    * Ctrl+колесо — приближение/отдаление (зум);
    * средняя кнопка мыши (или стрелки) — перемещение камеры (панорама);
    * наведение мыши — данные блока в строке состояния.
"""

from __future__ import annotations

import json
import math
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog
from typing import List, Optional, Sequence, Tuple

from redstone.core import Coord, World, СОСТОЯНИЯ, сообщение

# --- Геометрия изометрической проекции (2:1) -------------------------------
HW = 26              # половина ширины ромба грани (по экрану X)
HH = 13              # половина высоты ромба грани (по экрану Y)
CUBE_H = 28          # высота куба в пикселях (подъём на один слой Z)
СЕТКА = 16           # размер строительной площадки (клеток по X и Y)

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

# Инструменты, которые работают по уже существующему кубу под курсором.
_ПО_КУБУ = {
    СОСТОЯНИЯ["СОХРАНЕНИЕ"], СОСТОЯНИЯ["СТИРАНИЕ"], СОСТОЯНИЯ["ПЕРЕДАЧА"],
    СОСТОЯНИЯ["БЛОКИРОВКА"], СОСТОЯНИЯ["РАЗБЛОКИРОВКА"],
    СОСТОЯНИЯ["СНЯТИЕ_ВЫДЕЛЕНИЯ"], СОСТОЯНИЯ["СОЕДИНЕНИЕ"],
    СОСТОЯНИЯ["РАЗЪЕДИНЕНИЕ"],
}


def _осветлить(hex_цвет: str, k: float) -> str:
    """Затемнить/осветлить hex-цвет умножением на коэффициент k."""
    try:
        s = hex_цвет.lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        r, g, b = (int(s[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return hex_цвет
    f = lambda v: max(0, min(255, int(v * k)))
    return f"#{f(r):02x}{f(g):02x}{f(b):02x}"


def _в_клетке(px: float, py: float, полигон: Sequence[Tuple[float, float]]) -> bool:
    """Тест «точка внутри многоугольника» (алгоритм трассировки луча)."""
    внутри = False
    n = len(полигон)
    j = n - 1
    for i in range(n):
        xi, yi = полигон[i]
        xj, yj = полигон[j]
        if (yi > py) != (yj > py) and \
                px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            внутри = not внутри
        j = i
    return внутри


class RedstoneApp:
    def __init__(self, world: Optional[World] = None) -> None:
        self.world = world or World()
        self.world.наблюдатели.append(lambda msg: self.перерисовать())

        self.инструмент = СОСТОЯНИЯ["ГЕНЕРАЦИЯ"]
        self.слой_z = 0
        self.цвет_выделения = "#ffd54f"
        self.цвет_блока = "#8d6e63"

        # Камера: смещение и масштаб изометрической проекции.
        self.cam_x = 360.0
        self.cam_y = 150.0
        self.масштаб = 1.0

        # Промежуточные состояния для двухшаговых/тянущих инструментов.
        self._первая_точка: Optional[Coord] = None    # соединение/разъединение
        self._начало_тяги: Optional[Coord] = None      # выделение/перемещение
        self._наведённый: Optional[Coord] = None        # куб под курсором
        self._наведённая_клетка: Optional[Coord] = None # клетка пола под курсором
        self._пан: Optional[Tuple[float, float, float, float]] = None

        self.root = tk.Tk()
        self.root.title("Редстоун 3D — Minecraft style")
        self._построить_интерфейс()
        self.перерисовать()

    # ------------------------------------------------------------------ UI ---
    def _построить_интерфейс(self) -> None:
        панель = tk.Frame(self.root, padx=6, pady=6)
        панель.pack(side=tk.LEFT, fill=tk.Y)

        tk.Label(панель, text="Инструменты",
                 font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self._кнопки = {}
        for имя, состояние in ИНСТРУМЕНТЫ:
            b = tk.Button(панель, text=имя, width=16,
                          command=lambda s=состояние: self.выбрать_инструмент(s))
            b.pack(pady=1)
            self._кнопки[состояние] = b

        tk.Label(панель, text="").pack()
        tk.Button(панель, text="Цвет блока…", width=16,
                  command=self.выбрать_цвет_блока).pack(pady=1)
        self._метка_блока = tk.Label(панель, text="      ", bg=self.цвет_блока)
        self._метка_блока.pack(pady=1)
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

        кадр_зум = tk.Frame(панель)
        кадр_зум.pack(pady=2)
        tk.Label(кадр_зум, text="Вид:").pack(side=tk.LEFT)
        tk.Button(кадр_зум, text="–", width=2,
                  command=lambda: self.зум(1 / 1.15)).pack(side=tk.LEFT)
        tk.Button(кадр_зум, text="+", width=2,
                  command=lambda: self.зум(1.15)).pack(side=tk.LEFT)
        tk.Button(кадр_зум, text="⌂", width=2,
                  command=self.сбросить_вид).pack(side=tk.LEFT)

        tk.Label(панель, text="").pack()
        tk.Button(панель, text="Сохранить мир…", width=16,
                  command=self.сохранить_мир).pack(pady=1)
        tk.Button(панель, text="Загрузить мир…", width=16,
                  command=self.загрузить_мир).pack(pady=1)

        self.W, self.H = 760, 560
        self.canvas = tk.Canvas(self.root, width=self.W, height=self.H,
                                bg="#0d1b2a", highlightthickness=0)
        self.canvas.pack(side=tk.TOP, padx=6, pady=6)
        self.canvas.bind("<Button-1>", self._лкм_нажатие)
        self.canvas.bind("<ButtonRelease-1>", self._лкм_отпускание)
        self.canvas.bind("<B1-Motion>", self._наведение)
        self.canvas.bind("<Button-3>", self._пкм)
        self.canvas.bind("<Motion>", self._наведение)
        # Панорама камеры средней кнопкой мыши.
        self.canvas.bind("<Button-2>", self._пан_старт)
        self.canvas.bind("<B2-Motion>", self._пан_тяга)
        # Колесо: слой Z; Ctrl+колесо — зум. (Windows/Mac и Linux.)
        self.canvas.bind("<MouseWheel>", self._колесо)
        self.canvas.bind("<Control-MouseWheel>", self._колесо_зум)
        self.canvas.bind("<Button-4>", self._колесо)
        self.canvas.bind("<Button-5>", self._колесо)
        self.canvas.bind("<Control-Button-4>", self._колесо_зум)
        self.canvas.bind("<Control-Button-5>", self._колесо_зум)
        # Панорама стрелками.
        self.root.bind("<Left>", lambda e: self._сдвиг_камеры(40, 0))
        self.root.bind("<Right>", lambda e: self._сдвиг_камеры(-40, 0))
        self.root.bind("<Up>", lambda e: self._сдвиг_камеры(0, 40))
        self.root.bind("<Down>", lambda e: self._сдвиг_камеры(0, -40))

        self.статус = tk.Label(self.root, anchor="w", justify=tk.LEFT,
                               font=("TkFixedFont", 9))
        self.статус.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=(0, 6))

        self.выбрать_инструмент(self.инструмент)

    # ------------------------------------------------------- состояние UI ---
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

    def выбрать_цвет_блока(self) -> None:
        цвет = colorchooser.askcolor(self.цвет_блока)[1]
        if цвет:
            self.цвет_блока = цвет
            self._метка_блока.config(bg=цвет)

    def _сменить_слой(self) -> None:
        try:
            self.слой_z = int(self._спин_z.get())
        except ValueError:
            self.слой_z = 0
        self.перерисовать()

    def _установить_слой(self, z: int) -> None:
        self.слой_z = z
        self._спин_z.delete(0, tk.END)
        self._спин_z.insert(0, str(z))
        self.перерисовать()

    def зум(self, k: float) -> None:
        self.масштаб = max(0.3, min(3.0, self.масштаб * k))
        self.перерисовать()

    def сбросить_вид(self) -> None:
        self.cam_x, self.cam_y, self.масштаб = 360.0, 150.0, 1.0
        self.перерисовать()

    def _сдвиг_камеры(self, dx: float, dy: float) -> None:
        self.cam_x += dx
        self.cam_y += dy
        self.перерисовать()

    # ------------------------------------------- изометрическая проекция ---
    def _проекция(self, x: float, y: float, z: float) -> Tuple[float, float]:
        s = self.масштаб
        sx = self.cam_x + (x - y) * HW * s
        sy = self.cam_y + (x + y) * HH * s - z * CUBE_H * s
        return sx, sy

    def _клетка_по_экрану(self, px: float, py: float, z: int) -> Coord:
        """Обратная проекция точки экрана на плоскость слоя z → клетка пола."""
        s = self.масштаб
        fx = (px - self.cam_x) / (HW * s)                       # = x - y
        fy = (py - self.cam_y + z * CUBE_H * s) / (HH * s)      # = x + y
        xc = (fx + fy) / 2
        yc = (fy - fx) / 2
        return (math.floor(xc), math.floor(yc), z)

    def _грани_куба(self, c: Coord):
        """Вернуть три видимые грани куба как списки экранных точек.

        Возвращает (верх, правая, левая) — каждая грань это 4 точки.
        """
        x, y, z = c
        p = self._проекция
        P000, P100 = p(x, y, z), p(x + 1, y, z)
        P010, P110 = p(x, y + 1, z), p(x + 1, y + 1, z)
        P001, P101 = p(x, y, z + 1), p(x + 1, y, z + 1)
        P011, P111 = p(x, y + 1, z + 1), p(x + 1, y + 1, z + 1)
        верх = [P001, P101, P111, P011]
        правая = [P100, P110, P111, P101]   # грань +x (вправо-вниз)
        левая = [P010, P110, P111, P011]    # грань +y (влево-вниз)
        return верх, правая, левая

    @staticmethod
    def _ключ_порядка(c: Coord) -> Tuple[int, int]:
        # Художниковый алгоритм: дальние (меньше x+y) и нижние рисуем раньше.
        return (c[0] + c[1], c[2])

    def _куб_под_курсором(self, px: float, py: float) -> Optional[Coord]:
        """Топовый куб под точкой экрана (перебор спереди назад)."""
        порядок = sorted(self.world.блоки, key=self._ключ_порядка, reverse=True)
        for c in порядок:
            for грань in self._грани_куба(c):
                if _в_клетке(px, py, грань):
                    return c
        return None

    # ------------------------------------------------------- события мыши ---
    def _лкм_нажатие(self, event: tk.Event) -> None:
        if self.инструмент in (СОСТОЯНИЯ["ВЫДЕЛЕНИЕ"], СОСТОЯНИЯ["ПЕРЕМЕЩЕНИЕ"]):
            self._начало_тяги = self._клетка_по_экрану(event.x, event.y, self.слой_z)
            return
        self._применить_инструмент(event)

    def _лкм_отпускание(self, event: tk.Event) -> None:
        if self._начало_тяги is None:
            return
        начало = self._начало_тяги
        конец = self._клетка_по_экрану(event.x, event.y, self.слой_z)
        self._начало_тяги = None

        if self.инструмент == СОСТОЯНИЯ["ВЫДЕЛЕНИЕ"]:
            self._отправить(сообщение(
                СОСТОЯНИЯ["ВЫДЕЛЕНИЕ"], начало,
                {"область": [list(начало), list(конец)],
                 "цвет": self.цвет_выделения},
            ))
        elif self.инструмент == СОСТОЯНИЯ["ПЕРЕМЕЩЕНИЕ"]:
            якорь = self._куб_под_курсором(*self._экран_клетки(начало)) or начало
            сдвиг = tuple(конец[i] - начало[i] for i in range(3))
            self._отправить(сообщение(
                СОСТОЯНИЯ["ПЕРЕМЕЩЕНИЕ"], якорь, {"сдвиг": list(сдвиг)},
            ))
        else:
            self.перерисовать()

    def _экран_клетки(self, c: Coord) -> Tuple[float, float]:
        return self._проекция(c[0] + 0.5, c[1] + 0.5, c[2])

    def _пкм(self, event: tk.Event) -> None:
        куб = self._куб_под_курсором(event.x, event.y)
        цель = куб or self._клетка_по_экрану(event.x, event.y, self.слой_z)
        self._отправить(сообщение(СОСТОЯНИЯ["УНИЧТОЖЕНИЕ"], цель))

    def _пан_старт(self, event: tk.Event) -> None:
        self._пан = (event.x, event.y, self.cam_x, self.cam_y)

    def _пан_тяга(self, event: tk.Event) -> None:
        if self._пан is None:
            return
        x0, y0, cx, cy = self._пан
        self.cam_x = cx + (event.x - x0)
        self.cam_y = cy + (event.y - y0)
        self.перерисовать()

    def _колесо(self, event: tk.Event) -> None:
        delta = 1 if getattr(event, "delta", 0) > 0 or event.num == 4 else -1
        self._установить_слой(self.слой_z + delta)

    def _колесо_зум(self, event: tk.Event) -> None:
        вверх = getattr(event, "delta", 0) > 0 or event.num == 4
        self.зум(1.15 if вверх else 1 / 1.15)

    def _применить_инструмент(self, event: tk.Event) -> None:
        s = self.инструмент
        куб = self._куб_под_курсором(event.x, event.y)
        клетка = self._клетка_по_экрану(event.x, event.y, self.слой_z)

        if s == СОСТОЯНИЯ["ГЕНЕРАЦИЯ"]:
            # Клик по кубу — ставим блок сверху (как в Minecraft), иначе на слой.
            цель = (куб[0], куб[1], куб[2] + 1) if куб else клетка
            self._отправить(сообщение(s, цель, {"цвет": self.цвет_блока}))
            return

        # Дальше — инструменты, которым нужен существующий блок.
        цель = куб if (s in _ПО_КУБУ and куб) else клетка

        if s == СОСТОЯНИЯ["УНИЧТОЖЕНИЕ"]:
            self._отправить(сообщение(s, куб or клетка))
        elif s in (СОСТОЯНИЯ["БЛОКИРОВКА"], СОСТОЯНИЯ["РАЗБЛОКИРОВКА"]):
            self._отправить(сообщение(s, цель))
        elif s == СОСТОЯНИЯ["СОХРАНЕНИЕ"]:
            данные = self._спросить_json(
                "Сохранение данных",
                'Данные (JSON любой вложенности), например\n'
                '{"программа": [...], "метки": {"a": {"b": 1}}}:')
            if данные is not None:
                self._отправить(сообщение(s, цель, данные))
        elif s == СОСТОЯНИЯ["СТИРАНИЕ"]:
            ответ = simpledialog.askstring(
                "Стирание", "Ключи через запятую (пусто — стереть всё):",
                parent=self.root)
            if ответ is None:
                return
            ключи = [k.strip() for k in ответ.split(",") if k.strip()]
            self._отправить(сообщение(s, цель, {"ключи": ключи} if ключи else {}))
        elif s == СОСТОЯНИЯ["ПЕРЕДАЧА"]:
            данные = self._спросить_json(
                "Передача данных",
                'Передаваемые данные (JSON), например {"сигнал": {"уровень": 15}}:')
            if данные is not None:
                self._отправить(сообщение(s, цель, данные))
        elif s == СОСТОЯНИЯ["СНЯТИЕ_ВЫДЕЛЕНИЯ"]:
            self._отправить(сообщение(s, цель, {"все": True}))
        elif s in (СОСТОЯНИЯ["СОЕДИНЕНИЕ"], СОСТОЯНИЯ["РАЗЪЕДИНЕНИЕ"]):
            точка = куб or клетка
            if self._первая_точка is None:
                self._первая_точка = точка
                self._статус(f"{s}: первый блок {точка}, кликните второй")
            else:
                первый, self._первая_точка = self._первая_точка, None
                self._отправить(сообщение(s, первый, {"с": list(точка)}))

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
        self._нарисовать_пол()
        self._нарисовать_соединения()

        for c in sorted(self.world.блоки, key=self._ключ_порядка):
            self._нарисовать_куб(c, self.world.блоки[c])

        self._нарисовать_наведение()
        self._нарисовать_hud()

    def _нарисовать_пол(self) -> None:
        """Слабая изометрическая сетка строительной площадки на слое Z."""
        cv = self.canvas
        z = self.слой_z
        for i in range(СЕТКА + 1):
            a = self._проекция(i, 0, z)
            b = self._проекция(i, СЕТКА, z)
            cv.create_line(*a, *b, fill="#1b3a52")
            a = self._проекция(0, i, z)
            b = self._проекция(СЕТКА, i, z)
            cv.create_line(*a, *b, fill="#1b3a52")

    def _нарисовать_соединения(self) -> None:
        cv = self.canvas
        for c, блок in self.world.блоки.items():
            cx, cy = self._проекция(c[0] + 0.5, c[1] + 0.5, c[2] + 0.5)
            for сосед in блок.соединения:
                if сосед <= c or сосед not in self.world.блоки:
                    continue
                sx, sy = self._проекция(сосед[0] + 0.5, сосед[1] + 0.5, сосед[2] + 0.5)
                cv.create_line(cx, cy, sx, sy, fill="#80cbc4", width=2)

    def _нарисовать_куб(self, c: Coord, блок) -> None:
        cv = self.canvas
        верх, правая, левая = self._грани_куба(c)
        контур = "#ffffff" if блок.выделен else "#10202e"
        ширина = 2 if блок.выделен else 1

        cv.create_polygon(*sum(map(list, левая), []),
                          fill=_осветлить(блок.цвет, 0.62),
                          outline=контур, width=ширина)
        cv.create_polygon(*sum(map(list, правая), []),
                          fill=_осветлить(блок.цвет, 0.82),
                          outline=контур, width=ширина)
        cv.create_polygon(*sum(map(list, верх), []),
                          fill=_осветлить(блок.цвет, 1.18),
                          outline=контур, width=ширина)

        # Полупрозрачная подсветка выделения поверх верхней грани.
        if блок.выделен:
            cv.create_polygon(*sum(map(list, верх), []),
                              fill=self.цвет_выделения, outline="",
                              stipple="gray50")

        # Центр верхней грани — для значков состояния.
        tcx = sum(p[0] for p in верх) / 4
        tcy = sum(p[1] for p in верх) / 4

        if блок.заблокирован:
            cv.create_line(*верх[0], *верх[2], fill="#e53935", width=2)
            cv.create_line(*верх[1], *верх[3], fill="#e53935", width=2)
        if блок.сигнал is not None:
            cv.create_oval(tcx + 3, tcy - 6, tcx + 11, tcy + 2,
                          fill="#ff5252", outline="")
        if блок.память:
            cv.create_oval(tcx - 11, tcy - 6, tcx - 3, tcy + 2,
                          fill="#40c4ff", outline="")

    def _нарисовать_наведение(self) -> None:
        cv = self.canvas
        # Подсветка клетки пола под курсором (куда встанет блок).
        if self._наведённая_клетка is not None and self._наведённый is None:
            x, y, z = self._наведённая_клетка
            ромб = [self._проекция(x, y, z), self._проекция(x + 1, y, z),
                    self._проекция(x + 1, y + 1, z), self._проекция(x, y + 1, z)]
            cv.create_polygon(*sum(map(list, ромб), []),
                              fill="", outline="#ffe082", width=2)
        # Контур наведённого куба.
        if self._наведённый is not None and self._наведённый in self.world.блоки:
            for грань in self._грани_куба(self._наведённый):
                cv.create_polygon(*sum(map(list, грань), []),
                                  fill="", outline="#ffe082", width=2)

    def _нарисовать_hud(self) -> None:
        cv = self.canvas
        текст = (f"Слой Z: {self.слой_z}    Зум: {self.масштаб:.2f}    "
                 f"Блоков: {len(self.world.блоки)}")
        cv.create_text(10, 10, anchor="nw", fill="#e0f2f1", text=текст,
                       font=("TkDefaultFont", 9, "bold"))
        cv.create_text(10, self.H - 10, anchor="sw", fill="#90a4ae",
                       text="ЛКМ — инструмент · ПКМ — снести · колесо — слой · "
                            "Ctrl+колесо — зум · СКМ/стрелки — камера",
                       font=("TkDefaultFont", 8))

    # ------------------------------------------------------------- сервис ---
    def _наведение(self, event: tk.Event) -> None:
        куб = self._куб_под_курсором(event.x, event.y)
        клетка = self._клетка_по_экрану(event.x, event.y, self.слой_z)
        if (куб, клетка) != (self._наведённый, self._наведённая_клетка):
            self._наведённый, self._наведённая_клетка = куб, клетка
            self.перерисовать()

        if куб is not None:
            блок = self.world.блоки[куб]
            self._статус(
                f"{куб} цвет={блок.цвет} заблокирован={блок.заблокирован} "
                f"память={json.dumps(блок.память, ensure_ascii=False)} "
                f"сигнал={json.dumps(блок.сигнал, ensure_ascii=False)}")
        else:
            self._статус(f"{клетка}: пусто (слой Z={self.слой_z})")

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
