# JARVIS — Персональный голосовой ИИ-ассистент

Локальный голосовой ассистент в стиле дворецкого для Windows с GPU NVIDIA.
Слышит команду → распознаёт через Whisper на GPU → отвечает через Claude API
→ озвучивает локально через Silero TTS.

---

## Требования

| Компонент | Минимум |
|---|---|
| ОС | Windows 10 / 11 (x64) |
| GPU | NVIDIA с поддержкой CUDA 12.1 |
| Python | 3.11 |
| RAM | 8 ГБ (рекомендуется 16 ГБ) |
| Микрофон | любой, видимый в системе |

---

## Установка

### 1. Создать виртуальное окружение

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 2. Установить PyTorch с CUDA 12.1 (для NVIDIA GPU)

```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
```

Проверка:
```powershell
python -c "import torch; print(torch.cuda.is_available())"
```
Должно напечатать `True`.

### 3. Установить остальные зависимости

```powershell
pip install -r requirements.txt
```

> Если `pyaudio` не ставится — попробуйте неофициальное колесо для вашей версии Python:
> ```powershell
> pip install pipwin
> pipwin install pyaudio
> ```

### 4. Создать и заполнить `.env`

```powershell
copy .env.example .env
notepad .env
```

Укажите в файле:

- **`ANTHROPIC_API_KEY`** — получите на [console.anthropic.com](https://console.anthropic.com)
- **`PORCUPINE_ACCESS_KEY`** — бесплатно на [picovoice.ai](https://picovoice.ai)

Опционально:
- `SILERO_SPEAKER` — `aidar` (мужской), `baya`/`kseniya`/`xenia` (женские)
- `WHISPER_MODEL` — `tiny` / `base` / `small` / `medium` / `large-v3`
- `JARVIS_LOG_LEVEL` — `DEBUG` / `INFO` / `WARNING` / `ERROR`

### 5. Запустить

```powershell
python main.py
```

Подождите ~30 секунд на первой загрузке моделей (Whisper, Silero).
После приветствия «Джарвис активирован. Слушаю, Сэр.» — скажите **«Джарвис»**
и задайте вопрос.

---

## Использование

### Голосовые команды

| Фраза | Действие |
|---|---|
| «Джарвис, …» | wake word — начало записи команды |
| «очисти историю» | сброс краткосрочной памяти диалога |
| «стоп» / «выход» / «выключись» | завершение программы |

### Что запоминается надолго (SQLite)

Ассистент автоматически извлекает и сохраняет в `jarvis_memory.db`:

- «Меня зовут Алексей» → `person.name = Алексей`
- «Я работаю в Яндексе» → `person.workplace = Яндексе`
- «Мне 30 лет» → `person.age = 30»
- «Я люблю кофе» → `preference.likes = кофе»
- и т.д.

Эти факты автоматически подмешиваются в контекст Claude.

---

## Структура проекта

```
jarvis/
├── main.py                  # Точка входа, главный цикл
├── config.py                # Настройки, константы, ключи API
├── requirements.txt         # Все зависимости с версиями
├── .env.example             # Шаблон переменных окружения
├── README.md                # Этот файл
├── core/
│   ├── __init__.py
│   ├── listener.py          # Wake word (Porcupine) + запись с VAD
│   ├── stt.py               # faster-whisper STT
│   ├── brain.py             # Claude API + системный промпт
│   ├── tts.py               # Silero TTS (torch.hub)
│   └── speaker.py           # Воспроизведение через sounddevice
└── memory/
    ├── __init__.py
    ├── short_term.py        # История диалога (deque, 20 msg)
    └── long_term.py         # SQLite — факты о пользователе
```

---

## Как это работает

```
[Микрофон]
    ↓ PyAudio — захват звука
    ↓ Porcupine — обнаружение wake word 'Джарвис'
    ↓ faster-whisper (GPU) — Speech-to-Text

[Оркестратор — main.py]
    ↕ SQLite — краткосрочная и долгосрочная память

    ↓ Anthropic SDK — Claude claude-sonnet-4-6 (streaming)

    ↓ Silero TTS (CPU/GPU) — Text-to-Speech
    ↓ sounddevice — воспроизведение

[Динамики]
```

1. **Porcupine** слушает микрофон, почти не нагружая CPU.
2. После «Джарвис» — VAD пишет речь, пока не наступит тишина 1.5 сек.
3. **faster-whisper** транскрибирует аудио на GPU (< 1 сек).
4. **Claude** (streaming) генерирует ответ в стиле дворецкого.
5. **Silero TTS** синтезирует голос локально, без интернета.
6. **sounddevice** проигрывает WAV через динамики.

---

## Возможные проблемы

### `OSError: [Errno -9999] Unanticipated host error` (sounddevice)

Не выбрано устройство вывода. Откройте `config.py` и проверьте наличие
динамиков в системе. Также можно явно указать device в `play_audio()`.

### `faster-whisper` ругается на CUDA

Проверьте, что PyTorch установлен с CUDA-индексом:
```powershell
python -c "import torch; print(torch.version.cuda)"
```
Должно быть `12.1` или выше. Если нет — переустановите torch по шагу 2.

### `pvporcupine` — `Invalid access key`

Проверьте `PORCUPINE_ACCESS_KEY` в `.env` — он отличается от шаблона.

### Silero не загружается

Требуется интернет при первом запуске (модель качается из torch.hub).
После — работает локально.

---

## Логи

Все события пишутся в `jarvis.log` (ротация по 2 МБ × 3 файла) и в консоль.
Уровень — `INFO` по умолчанию, переключается через `JARVIS_LOG_LEVEL`.

---

## Лицензия

Личное использование.