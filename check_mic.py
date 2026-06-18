import time
import numpy as np

try:
    import pyaudio
except ImportError:
    print("Ошибка: библиотека pyaudio не установлена. Запустите в venv: pip install pyaudio")
    exit(1)

def main():
    p = pyaudio.PyAudio()
    
    print("=== Список аудиоустройств ввода (микрофонов) ===")
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    
    default_device_index = p.get_default_input_device_info().get('index', -1)
    
    for i in range(0, numdevices):
        device_info = p.get_device_info_by_host_api_device_index(0, i)
        if device_info.get('maxInputChannels') > 0:
            default_marker = " [ПО УМОЛЧАНИЮ]" if device_info.get('index') == default_device_index else ""
            print(f"Индекс {device_info.get('index')}: {device_info.get('name')}{default_marker}")
            
    print("\n=== Тестирование микрофона по умолчанию ===")
    print("Сейчас мы откроем микрофон и будем показывать уровень громкости в реальном времени.")
    print("Пожалуйста, скажите что-нибудь или постучите по микрофону.")
    print("Нажмите Ctrl+C для выхода.\n")
    
    try:
        # Открываем поток
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024
        )
        
        while True:
            # Читаем данные с микрофона
            raw = stream.read(1024, exception_on_overflow=False)
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            
            # Вычисляем уровень RMS (энергию/громкость)
            if samples.size > 0:
                rms = np.sqrt(np.mean(np.square(samples)))
                # Масштабируем для удобного отображения в консоли
                level = int(rms / 100)
                meter = "█" * min(level, 50) + "░" * max(0, 50 - level)
                print(f"\rГромкость: {rms:5.1f} | {meter}", end="", flush=True)
            time.sleep(0.05)
            
    except KeyboardInterrupt:
        print("\n\nТест завершен.")
    except Exception as e:
        print(f"\nОшибка при работе с микрофоном: {e}")
    finally:
        if 'stream' in locals() and stream.is_active():
            stream.stop_stream()
            stream.close()
        p.terminate()

if __name__ == "__main__":
    main()
