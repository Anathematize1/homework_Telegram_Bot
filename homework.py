import os
import logging
import time
import sys
from http import HTTPStatus

import requests
from requests import RequestException
from telebot import TeleBot
from telebot.apihelper import ApiException
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


def setup_logger():
    """Настраивает логирование."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] [%(funcName)s:%(lineno)d] %(message)s'
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger


logger = setup_logger()


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
    logger.debug('Попытка отправить сообщение в Telegram')
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Сообщение успешно отправлено: {message}')
    except (ApiException, RequestException) as error:
        logger.error(f'Ошибка при отправке сообщения: {error}')


def get_api_answer(timestamp):
    """Делает запрос к API и возвращает ответ."""
    payload = {'from_date': timestamp}
    logger.debug(f'запрос к {ENDPOINT}, с параметрами: {payload}')
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException as error:
        raise ConnectionError(
            f'Ошибка при запросе к {ENDPOINT}, '
            f'с параметрами {payload}: {error}'
        )
    if response.status_code != HTTPStatus.OK:
        raise ValueError(
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код ответа API: {response.status_code}'
        )

    return response.json()


def check_response(response):
    """Проверяет структуру ответа API."""
    logger.debug('Проверка структуры ответа API')
    if not isinstance(response, dict):
        raise TypeError(
            f'ответ API должен быть dict, получен: {type(response).__name__}'
        )

    if 'homeworks' not in response:
        raise KeyError('в ответе API отсутствует ключ homeworks')

    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError(
            f'В ответе API значение homeworks должно быть list, '
            f'получен: {type(homeworks).__name__}'
        )

    logger.debug('Проверка структуры ответа API прошла успешно!')

    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    logger.debug('Проверка статуса домашней работы')
    if 'homework_name' not in homework:
        raise KeyError('отсутствует ключ с названием домашней работы')

    if 'status' not in homework:

        raise KeyError('отсутствует ключ со статусом домашней работы')

    homework_name = homework['homework_name']
    status = homework['status']

    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус домашней работы: {status}')

    verdict = HOMEWORK_VERDICTS[status]

    logger.debug(
        f'Статус работы "{homework_name}" успешно обработан: {verdict}'
    )

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if not homeworks:
                logger.debug('В ответе API нет новых статусов.')
            else:
                message = parse_status(homeworks[0])
                send_message(bot, message)
                last_error_message = None

            timestamp = response.get('current_date', int(time.time()))

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)

            if message != last_error_message:
                send_message(bot, message)
                last_error_message = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
