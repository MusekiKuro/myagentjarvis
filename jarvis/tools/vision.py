"""
tools/vision.py — Компьютерное зрение через LLM.

Делает скриншот экрана и отправляет его в OpenRouter (multimodal LLM)
для понимания происходящего на экране.
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

import requests

from jarvis import config

logger = logging.getLogger(__name__)


def _capture_screen() -> str | None:
    """Делает скриншот и возвращает его в формате base64."""
    try:
        import pyautogui
        import io
        
        screenshot = pyautogui.screenshot()
        # Сжимаем изображение, чтобы не отправлять слишком большой payload
        screenshot.thumbnail((1920, 1080))
        
        buffer = io.BytesIO()
        screenshot.save(buffer, format="JPEG", quality=80)
        img_bytes = buffer.getvalue()
        
        return base64.b64encode(img_bytes).decode('utf-8')
    except ImportError:
        logger.error("vision: pyautogui не установлен.")
        return None
    except Exception as e:
        logger.error("vision: ошибка создания скриншота: %s", e)
        return None


def analyze_screen(prompt: str = "Что сейчас изображено на экране? Опиши интерфейс и основные элементы.") -> str:
    """
    Делает скриншот текущего экрана и анализирует его с помощью Vision LLM.

    Args:
        prompt: Вопрос к модели о содержимом экрана.
    """
    img_b64 = _capture_screen()
    if not img_b64:
        return "Ошибка: не удалось сделать скриншот (возможно, не установлен pyautogui или Pillow)."

    # Используем модель, поддерживающую vision через OpenRouter
    vision_model = "google/gemini-2.5-flash"  # или другая подходящая модель
    
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://github.com/MusekiKuro/myagentjarvis",
        "X-Title": "JARVIS Assistant",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_b64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 500
    }
    
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if "choices" in data and len(data["choices"]) > 0:
            result_text = data["choices"][0]["message"]["content"]
            logger.info("vision: экран успешно проанализирован.")
            return f"Результат анализа экрана:\n{result_text}"
        else:
            return f"Ошибка API OpenRouter: {data}"
            
    except Exception as e:
        logger.error("vision: ошибка API: %s", e)
        return f"Ошибка при обращении к Vision API: {e}"
