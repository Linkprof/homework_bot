import os
import logging
import time
from datetime import datetime
import sys
from http import HTTPStatus

from dotenv import load_dotenv
import requests
import telegram

from exceptions import (HttpResponseError,
                        StatusUnknown,
                        TelegramError)


load_dotenv()


PRACTICUM_TOKEN = os.getenv('TOKEN_YANDEX')
TELEGRAM_TOKEN = os.getenv('TOKEN_TELEGRAM')
TELEGRAM_CHAT_ID = os.getenv('TOKEN_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens() -> bool:
    """Проверяем достпуность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot: telegram.bot.Bot, message: str) -> None:
    """Отправка сообщения в Telegram."""
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )
        logging.debug(f'Сообщение - "{message}", отправлено успешно')

    except telegram.error.TelegramError as error:
        message = f'Не удалось отправить сообщение из-за ошибки {error}'
        logging.error(message)
        raise TelegramError(message)


def get_api_answer(timestamp: int) -> dict:
    """Запрос к единственному эндпоинту API-сервиса."""
    response = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {"from_date": timestamp},
    }
    try:
        response = requests.get(**response)
        if response.status_code != HTTPStatus.OK:
            message = (f'Параметры запроса: {response.url}',
                       f'Статус ответа API: {response.status_code}',
                       f'Контент ответа: {response.text}',)
            raise HttpResponseError(message)

    except requests.exceptions.RequestException as error:
        message = f'Эндпоинт {ENDPOINT}, недоступен! Ошибка: {error}.'
        raise ConnectionError(message)

    return response.json()


def check_response(response: dict) -> list:
    """Проверка ответа API на наличие нужных ключей и типов данных."""
    logging.info('Проверка ответа API')

    if not isinstance(response, dict):
        message = 'Ответ API не являтеся словарем!'
        logging.error(message)
        raise TypeError(message)

    if 'homeworks' not in response:
        message = 'Нет нужного ключа homeworks в ответе API!'
        logging.error(message)
        raise KeyError(message)

    if 'current_date' not in response:
        message = 'Нет нужного ключа current_date в ответе API!'
        logging.error(message)
        raise KeyError(message)

    homeworks = response['homeworks']

    if not isinstance(homeworks, list):
        message = 'Формат данных по ключу "homeworks", не является списком!'
        logging.error(message)
        raise TypeError(message)

    return homeworks


def parse_status(homework: dict) -> str:
    """
    Парсим статус домашней работы.
    Содержащий вердикт из словаря HOMEWORK_VERDICTS.
    """
    if 'homework_name' not in homework:
        message = 'В ответе API нет ключа "homework_name".'
        logging.error(message)
        raise KeyError(message)

    homework_name = homework.get('homework_name')

    if 'status' not in homework:
        message = 'В ответе API отсутстует ключ "status".'
        logging.error(message)
        raise KeyError(message)

    status_work = homework.get('status')

    verdict = HOMEWORK_VERDICTS.get(status_work)

    if status_work not in HOMEWORK_VERDICTS:
        message = f'Неизвестный статус домашней работы: {status_work}'
        logging.error(message)
        raise StatusUnknown(message)

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        message = 'Отсутствуют одна или несколько переменных окружения'
        logging.critical(message)
        sys.exit(message)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    old_status_homework = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response.get('current_date', timestamp)
            homeworks = check_response(response)

            if homeworks:
                homeworks = homeworks[0]
                message = parse_status(homeworks)
                logging.debug('Новый статус')
            else:
                message = (f'За период от {datetime.fromtimestamp(timestamp)}'
                           'до настоящего'
                           ' момента изменения статуса домашней работы нет.')
                logging.debug('Новых статусов нет')
            if message != old_status_homework:
                send_message(bot, message)
                old_status_homework = message
            else:
                logging.debug('Данное сообщение уже было отправлено')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.exception(message)
            if message != old_status_homework:
                send_message(bot, message)
                old_status_homework = message
            else:
                logging.debug(f'Данное сообщение о {error}'
                              ' уже было отправлено')

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s, %(levelname)s, %(message)s, %(name)s',
        stream=sys.stdout
    )
    main()
