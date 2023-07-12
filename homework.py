import os
import logging
import time
import sys
from http import HTTPStatus

from dotenv import load_dotenv
import requests
import telegram

from exceptions import HttpResponseError


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


def check_tokens():
    """Проверяем достпуность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
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
        raise AssertionError(message)


def get_api_answer(timestamp):
    """Запрос к единственному эндпоинту API-сервиса."""
    RESPONSE = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {"from_date": timestamp},
    }
    try:
        response = requests.get(**RESPONSE)
        if response.status_code != HTTPStatus.OK:
            message = (f'Параметры запроса: {response.url}',
                       f'Статус ответа API: {response.status_code}',
                       f'Контент ответа: {response.text}',)
            raise HttpResponseError(message)

    except Exception as error:
        message = f'Эндпоинт {ENDPOINT}, недоступен! Ошибка: {error}.'
        raise HttpResponseError(message)

    return response.json()


def check_response(response):
    """Проверка ответа API на наличие нужных ключей и типов данных."""
    logging.info('Проверка ответа API')

    if not isinstance(response, dict):
        message = 'Ответ API не являтеся словарем!'
        logging.error(message)
        raise TypeError(message)

    if 'homeworks' not in response and 'current_date' not in response:
        message = 'Нет нужного ключа в ответе API!'
        logging.error(message)
        raise KeyError(message)

    homeworks = response.get('homeworks')

    if not isinstance(homeworks, list):
        message = 'Формат данных по ключу "homeworks", не является списком!'
        logging.error(message)
        raise TypeError(message)

    return homeworks


def parse_status(homework):
    """
    Парсим статус домашней работы.
    Содержащий вердикт из словаря HOMEWORK_VERDICTS.
    """
    homework_name = homework.get('homework_name')

    if 'homework_name' not in homework:
        message = 'В ответе API нет ключа "homework_name".'
        logging.error(message)
        raise KeyError(message)

    status_work = homework.get('status')

    if 'status' not in homework:
        message = 'В ответе API отсутстует ключ "status".'
        logging.error(message)
        raise KeyError(message)

    verdict = HOMEWORK_VERDICTS.get(status_work)

    if status_work not in HOMEWORK_VERDICTS:
        message = f'Неизвестный статус домашней работы: {status_work}'
        logging.error(message)
        raise KeyError(message)

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical(
            'Отсутствуют переменные окружения',
            'Программа принудительно остановлена!'
        )
        exit()

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    old_status_homework = ''
    old_exception = ''

    while True:

        try:
            response_get_api = get_api_answer(timestamp)
            timestamp = response_get_api.get('current_date')
            homeworks = check_response(response_get_api)

            if not homeworks:
                message = 'Нет домашних работ'
                logging.debug(message)

            new_status_homework = parse_status(homeworks[0])

            if new_status_homework != old_status_homework:
                message = new_status_homework
                send_message(bot, message)
                old_status_homework = new_status_homework

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(error.__context__)
            new_exception = message
            if new_exception != old_exception:
                send_message(bot, message)
                old_exception = new_exception

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s, %(levelname)s, %(message)s, %(name)s',
        stream=sys.stdout
    )
    main()
