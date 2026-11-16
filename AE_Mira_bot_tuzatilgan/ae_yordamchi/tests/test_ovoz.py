"""Yangi ovoz funksiyasi: tashqi xizmatga murojaatsiz sinov."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from aiohttp import web
from app import Service


class OvozSinovi(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {'BOT_TOKEN': '123456789:' + 'A' * 35,
            'DATABASE_URL': 'sqlite+aiosqlite:///:memory:', 'TTS_PROVIDER': 'edge'})
        self.env.start()
        self.service = Service()
        await self.service.db.start()

    async def asyncTearDown(self):
        await self.service.bot.session.close()
        await self.service.db.engine.dispose()
        self.env.stop()

    async def test_edge_audio(self):
        class Fake:
            def __init__(self, text, voice):
                self.text, self.voice = text, voice

            async def stream(self):
                yield {'type': 'audio', 'data': b'audio-sinov'}

        with patch.dict(sys.modules, {'edge_tts': SimpleNamespace(Communicate=Fake)}):
            self.assertEqual(await self.service.speech(42, 'Salom'), b'audio-sinov')

    async def test_noma_lum_provider(self):
        with patch.dict(os.environ, {'TTS_PROVIDER': 'noma_lum'}):
            with self.assertRaises(web.HTTPBadRequest):
                await self.service.speech(42, 'Salom')
