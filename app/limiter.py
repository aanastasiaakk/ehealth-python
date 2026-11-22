"""Обмеження кількості одночасних запитів (ЛР7, оптимізація №1).

Проблема з ЛР4. FastAPI виконує звичайні (не async) функції в пулі з
40 потоків. Кожен запит спершу бере з'єднання з базою (залежність
`get_db` + перевірка користувача), а потім чекає вільний потік, щоб
виконати сам ендпоінт. Коли одночасних запитів стає більше, ніж
з'єднань у пулі (30), виникає замкнене коло: потоки чекають на
з'єднання, а з'єднання тримають запити, що чекають на потоки. Сервер
зависає повністю, навіть /health.

Рішення — «турнікет» на вході: одночасно обробляється не більше
`max_concurrent_requests` (40) запитів, а з'єднань у пулі більше (50).
Тоді на кожен запит гарантовано є з'єднання, і коло розірвано. Решта
запитів чекає в черзі (це дешево: черга — у циклі подій, без потоків).
Якщо запит простояв у черзі довше за `request_queue_timeout`, він одразу
отримує 503 «сервер зайнятий» замість хвилинного зависання.

/health не обмежується: перевірка живучості має відповідати завжди.
"""

import asyncio
import json

BUSY_BODY = json.dumps({"detail": "Server is busy, please retry"}).encode()


class ConcurrencyLimitMiddleware:
    def __init__(
        self,
        app,
        limit: int,
        queue_timeout: float,
        exempt_paths: tuple[str, ...] = ("/health", "/metrics"),
    ):
        self.app = app
        self.limit = limit
        self.queue_timeout = queue_timeout
        self.exempt_paths = exempt_paths
        self._semaphore: asyncio.Semaphore | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_semaphore(self) -> asyncio.Semaphore:
        # Семафор прив'язаний до циклу подій, тому створюємо його в тому
        # циклі, де він використовується (у тестах цикли бувають різні)
        loop = asyncio.get_running_loop()
        if self._semaphore is None or self._loop is not loop:
            self._semaphore = asyncio.Semaphore(self.limit)
            self._loop = loop
        return self._semaphore

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in self.exempt_paths:
            return await self.app(scope, receive, send)

        semaphore = self._get_semaphore()
        try:
            await asyncio.wait_for(semaphore.acquire(), self.queue_timeout)
        except asyncio.TimeoutError:
            await _send_busy(send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            semaphore.release()


async def _send_busy(send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 503,
            "headers": [
                (b"content-type", b"application/json"),
                (b"retry-after", b"1"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": BUSY_BODY})
