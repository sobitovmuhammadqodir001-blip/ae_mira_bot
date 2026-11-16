"""Tashqi kalitlarsiz xavfsizlik, saqlash va suhbat sinovlari."""
import asyncio
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import select, update

from app import authenticate, Store, Service, make_app, make_pdf, users, usage, messages

TOKEN = '123456789:' + 'A' * 35


def signed(uid=42, age=0):
    data = {'auth_date': str(int(time.time()) - age), 'user': json.dumps({'id': uid})}
    key = hmac.new(b'WebAppData', TOKEN.encode(), hashlib.sha256).digest()
    value = '\n'.join(f'{k}={v}' for k, v in sorted(data.items()))
    data['hash'] = hmac.new(key, value.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


class AuthTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(authenticate(signed(), TOKEN), 42)

    def test_tampered(self):
        with self.assertRaises(ValueError):
            authenticate(signed().replace('42', '43'), TOKEN)

    def test_expired(self):
        with self.assertRaises(ValueError):
            authenticate(signed(age=3700), TOKEN)

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            authenticate(signed() + '&auth_date=1', TOKEN)

    def test_pdf_unicode(self):
        data = make_pdf('O‘zbekcha: g‘oya, o‘qish, ta’lim. <sinov>')
        self.assertTrue(data.startswith(b'%PDF-'))
        self.assertGreater(len(data), 1000)


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store('sqlite+aiosqlite:///' + str(Path(self.tmp.name) / 'test.db'))
        await self.db.start()

    async def asyncTearDown(self):
        await self.db.engine.dispose()
        self.tmp.cleanup()

    async def test_topic_ownership(self):
        topic = await self.db.new_topic(42)
        with self.assertRaises(web.HTTPNotFound):
            await self.db.topic(43, topic['id'])

    async def test_quota(self):
        self.assertTrue(await self.db.reserve(42, 1))
        self.assertFalse(await self.db.reserve(42, 1))
        await self.db.execute(update(users).where(users.c.id == 42).values(day='2000-01-01'))
        self.assertTrue(await self.db.reserve(42, 1))

    async def test_quota_concurrent(self):
        await self.db.reserve(42, 100)
        result = await asyncio.gather(*(self.db.reserve(42, 3) for _ in range(10)))
        self.assertEqual(sum(result), 2)

    async def test_webhook_dedup(self):
        self.assertTrue(await self.db.enqueue({'update_id': 123}))
        self.assertFalse(await self.db.enqueue({'update_id': 123}))

    async def test_answer_and_context(self):
        with patch.dict(os.environ, {'BOT_TOKEN': TOKEN, 'DATABASE_URL': 'sqlite+aiosqlite:///:memory:'}):
            service = Service()
        await service.db.engine.dispose()
        service.db = self.db
        seen = []

        async def fake(path, payload=None, form=None):
            seen.append(payload)
            return {'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': 'Salom!'}]}],
                'usage': {'input_tokens': 10, 'output_tokens': 3}}

        service.openai = fake
        topic = await self.db.new_topic(42)
        self.assertEqual(await service.answer(42, topic['id'], 'Salom'), 'Salom!')
        await service.answer(42, topic['id'], 'Yana salom')
        self.assertEqual(len(seen[1]['input']), 3)
        self.assertFalse(seen[1]['store'])
        stats = await self.db.rows(select(usage).where(usage.c.uid == 42))
        self.assertEqual(sum(r['input'] for r in stats), 20)
        with self.assertRaises(web.HTTPNotFound):
            await service.answer(43, topic['id'], 'Begona')
        self.assertEqual(len(seen), 2)
        await service.bot.session.close()


class HTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with patch.dict(os.environ, {'BOT_TOKEN': TOKEN,
            'DATABASE_URL': 'sqlite+aiosqlite:///:memory:', 'WEBHOOK_SECRET': 'x' * 40}):
            self.s = Service()
        await self.s.db.start()
        app = make_app(self.s)
        app.on_startup.clear()
        app.on_cleanup.clear()
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.s.bot.session.close()
        await self.s.db.engine.dispose()

    async def test_no_auth(self):
        r = await self.client.get('/api/topics')
        self.assertEqual(r.status, 401)

    async def test_topics_and_cross_user(self):
        headers = {'X-Telegram-Init-Data': signed(42)}
        r = await self.client.get('/api/topics', headers=headers)
        self.assertEqual(r.status, 200)
        tid = (await r.json())[0]['id']
        r = await self.client.get('/api/messages?topic=' + tid,
                                  headers={'X-Telegram-Init-Data': signed(43)})
        self.assertEqual(r.status, 404)

    async def test_webhook_secret_and_duplicates(self):
        r = await self.client.post('/webhook', json={'update_id': 99})
        self.assertEqual(r.status, 403)
        for _ in range(2):
            r = await self.client.post('/webhook', json={'update_id': 99},
                headers={'X-Telegram-Bot-Api-Secret-Token': 'x' * 40})
            self.assertEqual(r.status, 200)

    async def test_audio_and_page(self):
        r = await self.client.get('/')
        self.assertEqual(r.status, 200)
        self.assertIn('AE Yordamchi', await r.text())
        r = await self.client.get('/audio/namuna.mp3')
        self.assertEqual(r.status, 200)
        self.assertEqual(await r.read(), Path('audio/namuna.mp3').read_bytes())


if __name__ == '__main__':
    unittest.main()
