# tAI — пошаговая установка

Всегда-включённый ИИ-агент в Telegram (Claude Code + постоянная память + кросс-вендор Codex/Gemini).

---

## Этап 0. Подготовить заранее
- Компьютер **macOS или Linux** + интернет.
- **Аккаунт Claude** (подписка/логин Anthropic) — «мозг» и оплата, у вас свой.
- **Отдельный Telegram-бот**: токен от **@BotFather** + свой **chat_id** от **@userinfobot**.
- **Код tAI**: доступ к приватному репозиторию (вас добавили collaborator / дали deploy-key) ЛИБО zip-архив.
- macOS: ничего вручную ставить не нужно — Docker поднимется сам (Colima).

## Этап 1. Получить код
**Вариант A — через GitHub-доступ:**
```
git clone git@github.com:zhamanov-seabus/tAI-clean.git
cd tAI
```
**Вариант B — из zip:** распаковать архив, `cd tAI`.

> Приватный репозиторий: one-liner `curl … | bash` не сработает (нужен токен). Используйте clone по доступу или zip.

## Этап 2. Установка (автомат)
```
./install.sh
```
Сам ставит: зависимости (uv, docker/colima, tmux, expect), **Postgres+pgvector в Docker (порт 5544, без sudo)**, миграции, память, демон-скрипты, watchdog, конфиг, агентов codex/gemini. Демон пока НЕ запускается — это правильно.

*(Опция: `./install.sh --system-pg` — использовать локальный Postgres на 5432 вместо Docker.)*

## Этап 3. Логин в Claude
```
claude
```
Разовый вход по ссылке/коду (ваш аккаунт Anthropic).

## Этап 4. Плагин Telegram (в той же сессии `claude`)
```
/plugin      → установить 'telegram' (claude-plugins-official)
```

## Этап 5. Настройка бота
```
claudet setup      # спросит токен @BotFather + chat_id, всё пропишет
```
Затем в сессии `claude`:
```
/telegram:configure     → вставить токен
/telegram:access        → одобрить свой chat_id
```

## Этап 6. Запуск и проверка
```
claudet up
claudet doctor         # все пункты ✓?
```
Заполнить `~/tai/CLAUDE.md` (имя владельца + контекст проекта).
Написать боту в Telegram → агент отвечает.

---

## Управление
```
claudet status        # состояние демона
claudet logs          # логи
claudet restart       # перезапуск
claudet down          # остановить
claudet attach        # войти в живую сессию (tmux)
```

## Удаление
```
bash ~/tAI/uninstall.sh           # снести (данные памяти + токен оставит)
bash ~/tAI/uninstall.sh --purge   # + стереть БД памяти и токен
```

## Что нельзя автоматизировать (и почему)
1. **Логин в Claude** — авторизация в вашем аккаунте (браузер).
2. **Установка плагина telegram** — в текущей версии Claude Code нет CLI-установки плагинов, только `/plugin`.
3. **Токен бота + chat_id** — секрет, вводится вручную в `claudet setup`.

Всё остальное — автомат. Итого ~5–10 минут на чистой машине.
