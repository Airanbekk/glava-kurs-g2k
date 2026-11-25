# Манифест конвейера

Команда: g2k (1 участник)
Тег заморозки: `freeze-v1` (ставится перед выдачей теста)

## Модели

| Этап | Модель | Версия | Где работает | Что уходит наружу | Как заменить |
| --- | --- | --- | --- | --- | --- |
| Учебный слой | Claude Sonnet 5.5 | `claude-sonnet-5-5` | облако Anthropic (через Claude Code по подписке) | текст главы | `LLM_MODEL` / `LLM_BACKEND` в `.env` |
| Задания курса | Claude Sonnet 5.5 | `claude-sonnet-5-5` | облако Anthropic | текст шага (из слоя) | `LLM_MODEL` |
| Спецификация ролика | Claude Sonnet 5.5 | `claude-sonnet-5-5` | облако Anthropic | утверждения узла | `LLM_MODEL` |
| Модуль проверки | Claude Opus 5.5 | `claude-opus-5-5` | облако Anthropic | пакет, страницы главы, кадры | `LLM_MODEL_REVIEW` |
| Озвучка | Microsoft Neural TTS (ru-RU-DmitryNeural, запасной ru-RU-SvetlanaNeural; kk-KZ доступны) | edge-tts 7.x | облако Microsoft | только текст сценария | `voice` в `g2k/video.py` |
| Иллюстрации | — (генерации нет) | — | локально, код | ничего | — |

Альтернативные бэкенды без изменения кода: Anthropic API по ключу (`LLM_BACKEND=api`), локальная модель через OpenAI-совместимый сервер vLLM/Ollama (`LLM_BACKEND=openai`, `LLM_BASE_URL`).

## Инструменты

| Инструмент | Версия | Для чего | Данные наружу |
| --- | --- | --- | --- |
| Python | 3.11 | конвейер | нет |
| jsonschema | 4.x | проверка по общим схемам | нет |
| rapidfuzz | 3.x | авторемонт почти дословных цитат | нет |
| Pillow, NumPy | — | кадры роликов из модели состояния | нет |
| FFmpeg (imageio-ffmpeg) | 7.x | сборка видео, громкость −16 LUFS | нет |
| KaTeX | 0.16.11 | формулы в курсе офлайн (встроены в HTML) | нет |
| Claude Code CLI | 2.1 | доступ к модели по подписке | см. «Модели» |

Лицензии: KaTeX — MIT; FFmpeg — LGPL; Python-библиотеки — MIT/BSD/Apache. Шрифт кадров — Segoe UI из системы.

## Запуск

Одна команда на главу: `python run.py build <глава>`; ролик: `python run.py video <глава>`; проверка: `python run.py check <глава>`.
