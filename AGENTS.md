# AGENTS.md

## Cursor Cloud specific instructions

This repo contains two layers, but only one is runnable from source:

- `redstone/` (Python) — a self-contained Minecraft-redstone-style block simulation engine with a Tkinter GUI and a console demo. This is the only product with source code present and is what can be built/run/tested.
- The Elixir "Pusher" app described in `README.md` (`mix.exs`, `mix.lock`, `tables.sql`) has no source: its `apps/`, `config/`, `envs/`, and `docs/` directories are absent, so it cannot be compiled or run. Treat the Elixir README/mix files as documentation only; do not provision Clickhouse/Kafka/etc.

### redstone (Python)

- Requires Python 3.10+ (stdlib only; `redstone/requirements.txt` lists no third-party packages). The GUI additionally needs the system `python3-tk` package (already installed in the VM snapshot).
- Run all commands from the repo root so the `redstone` package import path resolves.
- Console demo (headless, no display needed): `python3 -m redstone.main --demo`
- GUI: needs an X display. A VNC desktop is available at `DISPLAY=:1`, so run `DISPLAY=:1 python3 -m redstone.main` (optional `--z <layer>` selects the Z slice). Without a display, Tkinter `Tk()` will fail — use `--demo` instead.
- No automated test suite, linter config, or git hooks exist for the Python code. A quick sanity check is `python3 -c "import compileall; compileall.compile_dir('redstone', quiet=1)"`.
- Domain vocabulary in the code/messages is intentionally in Russian (e.g. `состояние`, `координата_воздействия`, `передаваемые_данные`).
