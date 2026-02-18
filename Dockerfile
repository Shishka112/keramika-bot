# Используем официальный образ Python 3.11 как основу
FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости
# --no-cache-dir чтобы образ был меньше
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код бота в контейнер
COPY . .

# Указываем команду для запуска бота
CMD ["python", "bot.py"]