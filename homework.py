import os
import logging
import time
import sys

import requests
from telebot import TeleBot
from dotenv import load_dotenv


load_dotenv()

PRACTICUM_TOKEN = os.getenv('practicum_token')
TELEGRAM_TOKEN = os.getenv('telegram_token')
TELEGRAM_CHAT_ID = os.getenv('telegram_chat_id')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)


def setup_logger():
    """Настраивает логирование."""
    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)


def check_tokens():
    """Проверяет наличие обязательных переменных окружения."""
    tokens = {
        'practicum_token': PRACTICUM_TOKEN,
        'telegram_token': TELEGRAM_TOKEN,
        'telegram_chat_id': TELEGRAM_CHAT_ID,
    }

    missing = [name for name, value in tokens.items() if not value]

    if missing:
        error_message = (
            f'Отсутствуют следующие переменные окружения: {", ".join(missing)}'
        )
        logger.critical(error_message)
        raise EnvironmentError(error_message)


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Сообщение успешно отправлено: {message}')
    except Exception as error:
        logger.error(f'Ошибка при отправке сообщения: {error}')
        raise


def get_api_answer(timestamp):
    """Делает запрос к API и возвращает ответ."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException as error:
        error_message = f'Ошибка при запросе к API: {error}'
        logger.error(error_message)
        raise RuntimeError(error_message)

    if response.status_code != 200:
        error_message = (
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код ответа API: {response.status_code}'
        )
        logger.error(error_message)
        raise RuntimeError(error_message)

    return response.json()


def check_response(response):
    """Проверяет структуру ответа API."""
    if not isinstance(response, dict):
        error_message = 'ответ API должен быть словарем'
        logger.error(error_message)
        raise TypeError(error_message)

    if 'homeworks' not in response:
        error_message = 'в ответе API отсутствует ключ homeworks'
        logger.error(error_message)
        raise KeyError(error_message)

    if 'current_date' not in response:
        error_message = 'В ответе API отсутствует ключ current_date'
        logger.error(error_message)
        raise KeyError(error_message)

    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        error_message = 'В ответе API значение homeworks должно быть списком'
        logger.error(error_message)
        raise TypeError(error_message)
    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework:
        error_message = 'отсутствует ключ с названием домашней работы'
        logger.error(error_message)
        raise KeyError(error_message)

    if 'status' not in homework:
        error_message = 'отсутствует ключ со статусом домашней работы'
        logger.error(error_message)
        raise KeyError(error_message)

    homework_name = homework['homework_name']
    status = homework['status']

    if status not in HOMEWORK_VERDICTS:
        error_message = f'Неизвестный статус домашней работы: {status}'
        logger.error(error_message)
        raise ValueError(error_message)

    verdict = HOMEWORK_VERDICTS[status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    setup_logger()
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            timestamp = response.get('current_date', timestamp)

            if not homeworks:
                logger.debug('В ответе API нет новых статусов.')
                last_error_message = None
                time.sleep(RETRY_PERIOD)
                continue

            message = parse_status(homeworks[0])
            send_message(bot, message)
            last_error_message = None

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)

            if message != last_error_message:
                try:
                    send_message(bot, message)
                    last_error_message = message
                except Exception:
                    pass

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
