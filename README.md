# Запуск — ветка `fable_opus_3D_2`

Python 3.10+. Из корня репозитория (`C:\DDOs`):

## 3D от первого лица (Ursina, Minecraft-style)

```powershell
pip install -r redstone/requirements.txt
python -m redstone.view3d
```

или:

```powershell
python -m redstone --fps
```

**Управление:** WASD + мышь · `1`–`9` — инструменты · ЛКМ — действие · ПКМ — снести · `C` — цвет блока · `F5`/`F9` — сохранить/загрузить мир · `Escape` — курсор

## Изометрический 3D (tkinter)

```powershell
python -m redstone
```

## Консольная демо

```powershell
python -m redstone.demo
```

## Тесты

```powershell
python -m unittest discover -s redstone/tests -p "test_*.py"
```

Логика блоков (`генерация`, `передача`, `соединение`, `выделение`, …) — в `redstone/core.py`; оба 3D-режима вызывают `World.dispatch` с теми же сообщениями.
