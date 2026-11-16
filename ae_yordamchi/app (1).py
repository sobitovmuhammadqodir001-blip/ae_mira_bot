"""AE Yordamchi: Telegram bot, Mini App va doimiy webhook navbati."""
import asyncio
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
import time
import uuid
from collections import defaultdict
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (BufferedInputFile, FSInputFile, InlineKeyboardButton,
                           InlineKeyboardMarkup, Update, WebAppInfo, BotCommand)
from dotenv import load_dotenv
from sqlalchemy import (MetaData, Table, Column, String, Text, Integer, BigInteger,
                        Float, select, insert, update, delete, func)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()
ROOT = Path(__file__).parent
TZ = ZoneInfo('Asia/Tashkent')
LOG = logging.getLogger('ae')
SYSTEM = ('Sen AE Corporation yaratgan AE Yordamchisan. Aloqa: @sobitovv_o8. '
          'Faqat o‘zbek tilida lotin yozuvida aniq va foydali javob ber. '
          'Bilmagan narsani to‘qima. Internet, qurilma yoki tashqi xizmatga '
          'ulanmagansan; bajarmagan ishingni bajarildi dema.')


def authenticate(raw, token, now=None):
    """Telegram Mini App imzosini va bir soatlik amal muddatini tekshirish."""
    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    data = dict(pairs)
    if len(data) != len(pairs):
        raise ValueError('Takrorlangan maydon')
    received = data.pop('hash', '')
    key = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    check = '\n'.join(f'{k}={v}' for k, v in sorted(data.items()))
    expected = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    age = (time.time() if now is None else now) - int(data.get('auth_date', '0'))
    if not hmac.compare_digest(expected, received) or not -30 <= age <= 3600:
        raise ValueError('Telegram tasdig‘i eskirgan yoki noto‘g‘ri')
    user = json.loads(data['user'])
    if not isinstance(user.get('id'), int) or user['id'] <= 0:
        raise ValueError('Foydalanuvchi aniqlanmadi')
    return user['id']


meta = MetaData()
users = Table('users', meta, Column('id', BigInteger, primary_key=True),
              Column('day', String(10)), Column('requests', Integer, default=0))
topics = Table('topics', meta, Column('id', String(32), primary_key=True),
               Column('uid', BigInteger, nullable=False, index=True),
               Column('title', String(80)), Column('created', Float))
messages = Table('messages', meta, Column('id', String(32), primary_key=True),
                 Column('topic', String(32), nullable=False, index=True),
                 Column('uid', BigInteger, nullable=False), Column('role', String(12)),
                 Column('text', Text), Column('created', Float))
usage = Table('usage', meta, Column('id', String(32), primary_key=True),
              Column('uid', BigInteger, index=True), Column('day', String(10)),
              Column('kind', String(20)), Column('input', Integer, default=0),
              Column('output', Integer, default=0), Column('characters', Integer, default=0))
inbox = Table('inbox', meta, Column('id', BigInteger, primary_key=True),
              Column('payload', Text), Column('state', String(16), index=True),
              Column('created', Float))


class Store:
    def __init__(self, url):
        if url.startswith(('postgres://', 'postgresql://')):
            url = 'postgresql+asyncpg://' + url.split('://', 1)[1]
        self.engine = create_async_engine(url, pool_pre_ping=True)

    async def start(self):
        async with self.engine.begin() as c:
            await c.run_sync(meta.create_all)
            await c.execute(update(inbox).where(inbox.c.state == 'processing').values(state='queued'))

    async def rows(self, stmt):
        async with self.engine.connect() as c:
            return [dict(r) for r in (await c.execute(stmt)).mappings().all()]

    async def execute(self, stmt):
        async with self.engine.begin() as c:
            return await c.execute(stmt)

    async def topic(self, uid, tid=None):
        stmt = select(topics).where(topics.c.uid == uid)
        if tid:
            stmt = stmt.where(topics.c.id == tid)
        found = await self.rows(stmt.order_by(topics.c.created.desc()).limit(1))
        if found:
            return found[0]
        if tid:
            raise web.HTTPNotFound(text='Mavzu topilmadi')
        return await self.new_topic(uid)

    async def new_topic(self, uid, title='Yangi mavzu'):
        row = dict(id=uuid.uuid4().hex, uid=uid, title=title[:80], created=time.time())
        await self.execute(insert(topics).values(**row))
        return row

    async def reserve(self, uid, limit):
        day = datetime.now(TZ).date().isoformat()
        try:
            await self.execute(insert(users).values(id=uid, day=day, requests=0))
        except IntegrityError:
            pass
        async with self.engine.begin() as c:
            await c.execute(update(users).where(users.c.id == uid, users.c.day != day)
                            .values(day=day, requests=0))
            result = await c.execute(update(users).where(users.c.id == uid, users.c.requests < limit)
                                     .values(requests=users.c.requests + 1).returning(users.c.id))
            return result.scalar_one_or_none() is not None

    async def record(self, uid, kind, **counts):
        await self.execute(insert(usage).values(id=uuid.uuid4().hex, uid=uid,
                           day=datetime.now(TZ).date().isoformat(), kind=kind, **counts))

    async def enqueue(self, payload):
        try:
            await self.execute(insert(inbox).values(id=payload['update_id'],
                payload=json.dumps(payload), state='queued', created=time.time()))
            return True
        except IntegrityError:
            return False


class Service:
    def __init__(self):
        self.token = os.getenv('BOT_TOKEN', '')
        self.key = os.getenv('OPENAI_API_KEY', '')
        self.secret = os.getenv('WEBHOOK_SECRET', '')
        self.url = (os.getenv('PUBLIC_URL') or os.getenv('RENDER_EXTERNAL_URL', '')).rstrip('/')
        self.model = os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')
        self.admin = int(os.getenv('ADMIN_ID') or '0')
        self.limit = int(os.getenv('DAILY_REQUEST_LIMIT', '50'))
        self.db = Store(os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./data/bot.db'))
        self.bot = Bot(self.token)
        self.dp = Dispatcher()
        self.locks = defaultdict(asyncio.Lock)
        self.active = {}
        self.selected = {}
        self.jobs = set()
        self.session = None
        self.ready = False
        self.bind_handlers()

    async def error(self, uid, exc):
        code = secrets.token_hex(4)
        # Xato matni foydalanuvchi xabari yoki kalitni o‘z ichiga olishi mumkin.
        LOG.error('Xato kodi=%s turi=%s', code, type(exc).__name__)
        if self.admin:
            with suppress(Exception):
                await self.bot.send_message(self.admin,
                    f'Xato: {code}\nFoydalanuvchi: {uid}\nTuri: {type(exc).__name__}')
        return f'So‘rov bajarilmadi. Keyinroq urinib ko‘ring. Xato kodi: {code}'

    async def openai(self, path, payload=None, form=None):
        headers = {'Authorization': f'Bearer {self.key}'}
        async with self.session.post('https://api.openai.com/v1/' + path,
                json=payload, data=form, headers=headers,
                timeout=aiohttp.ClientTimeout(total=100)) as r:
            if r.status >= 400:
                raise RuntimeError(f'OpenAI HTTP {r.status}')
            return await r.json()

    async def answer(self, uid, tid, text):
        async with self.locks[uid]:
            await self.db.topic(uid, tid)
            if not await self.db.reserve(uid, self.limit):
                raise web.HTTPTooManyRequests(text='Bugungi AI so‘rov limiti tugadi.')
            history = await self.db.rows(select(messages).where(messages.c.topic == tid,
                messages.c.uid == uid).order_by(messages.c.created.desc()).limit(20))
            content = [{'role': r['role'], 'content': r['text']} for r in reversed(history)]
            content.append({'role': 'user', 'content': text})
            result = await self.openai('responses', {'model': self.model,
                'instructions': SYSTEM, 'input': content, 'store': False, 'max_output_tokens': 1600})
            answer = '\n'.join(c['text'] for item in result.get('output', [])
                if item.get('type') == 'message' for c in item.get('content', [])
                if c.get('type') == 'output_text')
            if not answer:
                raise RuntimeError('Bo‘sh AI javobi')
            counts = result.get('usage', {})
            await self.db.record(uid, 'text', input=counts.get('input_tokens', 0),
                                 output=counts.get('output_tokens', 0))
            now = time.time()
            async with self.db.engine.begin() as c:
                for offset, role, value in [(0, 'user', text), (.001, 'assistant', answer)]:
                    await c.execute(insert(messages).values(id=uuid.uuid4().hex, topic=tid,
                        uid=uid, role=role, text=value, created=now + offset))
                if not history:
                    await c.execute(update(topics).where(topics.c.id == tid,
                        topics.c.uid == uid).values(title=text[:60]))
            return answer

    async def latest(self, uid, tid):
        await self.db.topic(uid, tid)
        rows = await self.db.rows(select(messages.c.text).where(messages.c.topic == tid,
            messages.c.uid == uid, messages.c.role == 'assistant')
            .order_by(messages.c.created.desc()).limit(1))
        if not rows:
            raise web.HTTPBadRequest(text='Avval javob oling.')
        return rows[0]['text']

    async def speech(self, uid, text):
        provider = os.getenv('TTS_PROVIDER', 'edge').strip().lower()
        if provider == 'edge':
            import edge_tts
            async with self.locks[uid]:
                if not await self.db.reserve(uid, self.limit):
                    raise web.HTTPTooManyRequests(text='Bugungi AI so‘rov limiti tugadi.')
                text = text[:3000].strip()
                if not text:
                    raise web.HTTPBadRequest(text='Ovoz uchun matn topilmadi.')
                voice = os.getenv('TTS_VOICE', 'uz-UZ-SardorNeural').strip()
                async def synthesize():
                    audio = bytearray()
                    async for chunk in edge_tts.Communicate(text, voice).stream():
                        if chunk['type'] == 'audio':
                            audio.extend(chunk['data'])
                            if len(audio) > 10 * 1024 * 1024:
                                raise RuntimeError('Ovoz hajmi chegaradan oshdi')
                    if not audio:
                        raise RuntimeError('Ovoz xizmati bo‘sh javob qaytardi')
                    return bytes(audio)
                data = await asyncio.wait_for(synthesize(), timeout=100)
                await self.db.record(uid, 'tts', characters=len(text))
                return data
        if provider != 'elevenlabs':
            raise web.HTTPBadRequest(text='TTS_PROVIDER edge yoki elevenlabs bo‘lsin.')
        key, voice = os.getenv('ELEVENLABS_API_KEY'), os.getenv('ELEVENLABS_VOICE_ID')
        if not key or not voice:
            raise web.HTTPBadRequest(text='Yangi ovozli javob uchun ELEVENLABS_API_KEY va '
                'ELEVENLABS_VOICE_ID sozlanishi kerak. MP3 — tayyor namuna.')
        async with self.locks[uid]:
            if not await self.db.reserve(uid, self.limit):
                raise web.HTTPTooManyRequests(text='Bugungi AI so‘rov limiti tugadi.')
            text = text[:3000]
            async with self.session.post(f'https://api.elevenlabs.io/v1/text-to-speech/{voice}',
                params={'output_format': 'mp3_44100_128'}, headers={'xi-api-key': key},
                json={'text': text, 'model_id': os.getenv('ELEVENLABS_MODEL_ID', 'eleven_v3')},
                timeout=aiohttp.ClientTimeout(total=100)) as r:
                if r.status != 200:
                    raise RuntimeError(f'ElevenLabs HTTP {r.status}')
                data = await r.read()
            await self.db.record(uid, 'tts', characters=len(text))
            return data

    def keyboard(self, tid):
        rows = [[InlineKeyboardButton(text='🔊 Ovozda tinglash', callback_data=f'tts:{tid}'),
                 InlineKeyboardButton(text='📄 PDF qilish', callback_data=f'pdf:{tid}')],
                [InlineKeyboardButton(text='🛑 To‘xtatish', callback_data='stop'),
                 InlineKeyboardButton(text='🎙 Ovoz namunasi', callback_data='sample')]]
        if self.url:
            rows.append([InlineKeyboardButton(text='✨ Ilovani ochish',
                web_app=WebAppInfo(url=self.url))])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def selected_topic(self, uid):
        return await self.db.topic(uid, self.selected.get(uid))

    def bind_handlers(self):
        dp = self.dp
        dp.message.filter(F.chat.type == 'private')

        @dp.message(Command('start', 'help'))
        async def start(m):
            if m.chat.type != 'private':
                return
            t = await self.selected_topic(m.from_user.id)
            await m.answer('Assalomu alaykum! Men AE Yordamchiman.\n'
                'Matn yoki ovozli xabar yuboring.\n\n'
                '/new — yangi mavzu\n/topics — mavzular\n/rename yangi nom — nomlash\n'
                '/clear — joriy mavzu xabarlarini o‘chirish\n/stop — to‘xtatish\n'
                '/sample — siz yuborgan ovoz namunasi\n'
                '/stats — bugungi foydalanish\n\nAE Corporation | @sobitovv_o8',
                reply_markup=self.keyboard(t['id']))

        @dp.message(Command('stop'))
        async def stop(m):
            task = self.active.get(m.from_user.id)
            if task and not task.done():
                task.cancel()
            await m.answer('To‘xtatish so‘rovi qabul qilindi.')

        @dp.message(Command('sample'))
        async def sample(m):
            await m.answer_audio(FSInputFile(ROOT / 'audio/namuna.mp3'),
                                 title='AE Yordamchi — siz yuborgan ovoz namunasi')

        @dp.message(Command('new', 'topics', 'rename', 'clear'))
        async def topic_commands(m):
            uid = m.from_user.id
            if m.chat.type != 'private':
                return
            if uid in self.active:
                return await m.answer('Avval joriy javobni kuting yoki /stop yuboring.')
            command, _, arg = m.text.partition(' ')
            async with self.locks[uid]:
                if command.split('@')[0] == '/new':
                    t = await self.db.new_topic(uid, arg or 'Yangi mavzu')
                    self.selected[uid] = t['id']
                    return await m.answer('Yangi mavzu ochildi.')
                t = await self.selected_topic(uid)
                if command.split('@')[0] == '/clear':
                    await self.db.execute(delete(messages).where(messages.c.uid == uid,
                                                                 messages.c.topic == t['id']))
                    return await m.answer('Joriy mavzu xabarlari o‘chirildi.')
                if command.split('@')[0] == '/rename':
                    if not arg.strip():
                        return await m.answer('/rename Yangi nom shaklida yozing.')
                    await self.db.execute(update(topics).where(topics.c.id == t['id'],
                        topics.c.uid == uid).values(title=arg.strip()[:80]))
                    return await m.answer('Mavzu nomi yangilandi.')
                ts = await self.db.rows(select(topics).where(topics.c.uid == uid)
                    .order_by(topics.c.created.desc()).limit(30))
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                    text=x['title'], callback_data='topic:' + x['id'])] for x in ts])
                await m.answer('Mavzuni tanlang:', reply_markup=kb)

        @dp.message(Command('stats'))
        async def stats(m):
            uid = m.from_user.id
            day = datetime.now(TZ).date().isoformat()
            rows = await self.db.rows(select(usage).where(usage.c.uid == uid, usage.c.day == day))
            ins, outs = sum(x['input'] for x in rows), sum(x['output'] for x in rows)
            price_in, price_out = os.getenv('INPUT_USD_PER_MILLION'), os.getenv('OUTPUT_USD_PER_MILLION')
            cost = (f'\nMatn uchun taxminiy sarf: ${(ins * float(price_in) + outs * float(price_out))/1e6:.4f}'
                    if price_in and price_out else '\nDollar narxi sozlanmagan; tokenlar hisoblanmoqda.')
            await m.answer(f'Bugun: {day} (Toshkent)\nBajarilgan amallar: {len(rows)}\n'
                           f'Kirish tokenlari: {ins}\nChiqish tokenlari: {outs}' + cost)

        @dp.message(Command('admin'))
        async def admin(m):
            if m.from_user.id != self.admin:
                return
            count = await self.db.rows(select(func.count().label('n')).select_from(users))
            await m.answer(f'Foydalanuvchilar: {count[0]["n"]}\nModel: {self.model}\n'
                           f'Kunlik so‘rov limiti: {self.limit}')

        @dp.callback_query()
        async def callback(q):
            await q.answer()
            if not q.message or q.message.chat.type != 'private':
                return
            uid = q.from_user.id
            try:
                if q.data == 'stop':
                    task = self.active.get(uid)
                    if task and not task.done():
                        task.cancel()
                    return
                if q.data == 'sample':
                    return await q.message.answer_audio(FSInputFile(ROOT / 'audio/namuna.mp3'),
                                                         title='Siz yuborgan ovoz namunasi')
                kind, tid = q.data.split(':', 1)
                await self.db.topic(uid, tid)
                if kind == 'topic':
                    if uid in self.active:
                        return await q.message.answer('Avval joriy javobni kuting.')
                    self.selected[uid] = tid
                    return await q.message.answer('Mavzu tanlandi.')
                text = await self.latest(uid, tid)
                if kind == 'pdf':
                    await q.message.answer_document(BufferedInputFile(make_pdf(text), 'AE_javob.pdf'))
                elif kind == 'tts':
                    data = await self.speech(uid, text)
                    await q.message.answer_audio(BufferedInputFile(data, 'AE_javob.mp3'))
            except web.HTTPException as exc:
                await q.message.answer(exc.text)
            except Exception as exc:
                await q.message.answer(await self.error(uid, exc))

        @dp.message(F.text | F.voice)
        async def chat(m):
            uid = m.from_user.id
            if m.chat.type != 'private':
                return
            if uid in self.active:
                return await m.answer('Joriy javob tayyorlanmoqda. To‘xtatish: /stop')
            self.active[uid] = asyncio.current_task()
            waiting = None
            try:
                t = await self.selected_topic(uid)
                waiting = await m.answer('O‘ylayapman…', reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text='🛑 To‘xtatish', callback_data='stop')]]))
                text = m.text
                if m.voice:
                    if m.voice.file_size and m.voice.file_size > 10 * 1024 * 1024:
                        return await m.answer('Ovozli xabar 10 MB dan oshmasin.')
                    if m.voice.duration > 120:
                        return await m.answer('Ovozli xabar 2 daqiqadan oshmasin.')
                    if not await self.db.reserve(uid, self.limit):
                        return await m.answer('Bugungi AI so‘rov limiti tugadi.')
                    buffer = io.BytesIO()
                    await self.bot.download(m.voice, destination=buffer)
                    form = aiohttp.FormData()
                    form.add_field('model', 'whisper-1')
                    form.add_field('file', buffer.getvalue(), filename='ovoz.ogg', content_type='audio/ogg')
                    text = (await self.openai('audio/transcriptions', form=form))['text']
                    await self.db.record(uid, 'stt')
                answer = await self.answer(uid, t['id'], text[:12000])
                for pos in range(0, len(answer), 3500):
                    await m.answer(answer[pos:pos + 3500], reply_markup=self.keyboard(t['id']))
            except asyncio.CancelledError:
                await m.answer('Javob tayyorlash to‘xtatildi. Provayder sarfi hisoblangan bo‘lishi mumkin.')
            except web.HTTPException as exc:
                await m.answer(exc.text)
            except Exception as exc:
                await m.answer(await self.error(uid, exc))
            finally:
                self.active.pop(uid, None)
                if waiting:
                    with suppress(Exception):
                        await waiting.delete()


def make_pdf(text):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from xml.sax.saxutils import escape
    font = ROOT / 'static/DejaVuSans.ttf'
    if not font.exists():
        raise RuntimeError('PDF shrifti topilmadi')
    if 'AE' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('AE', str(font)))
    stream = io.BytesIO()
    style = ParagraphStyle('AE', fontName='AE', fontSize=11, leading=16)
    story = []
    for line in text.splitlines():
        story.extend([Paragraph(escape(line) or ' ', style), Spacer(1, 5)])
    SimpleDocTemplate(stream).build(story)
    return stream.getvalue()


def make_app(service):
    app = web.Application(client_max_size=256 * 1024)
    s = service

    async def health(request):
        worker = app.get('worker')
        healthy = s.ready and (worker is None or not worker.done())
        return web.json_response({'holat': 'tayyor' if healthy else 'boshlanmoqda'},
                                 status=200 if healthy else 503)

    async def index(request):
        return web.FileResponse(ROOT / 'static/index.html', headers={'Cache-Control': 'no-cache'})

    async def webhook(request):
        value = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not s.secret or not hmac.compare_digest(value, s.secret):
            raise web.HTTPForbidden(text='Ruxsat yo‘q')
        try:
            payload = await request.json()
            Update.model_validate(payload)
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(text='Noto‘g‘ri xabar')
        await s.db.enqueue(payload)
        return web.json_response({'ok': True})

    async def api(request):
        try:
            uid = authenticate(request.headers.get('X-Telegram-Init-Data', ''), s.token)
        except (ValueError, KeyError, TypeError):
            raise web.HTTPUnauthorized(text='Ilovani Telegram botidagi tugma orqali qayta oching.')
        action = request.match_info['action']
        try:
            data = await request.json() if request.method == 'POST' else {}
            if action == 'topics' and request.method == 'GET':
                rows = await s.db.rows(select(topics).where(topics.c.uid == uid)
                                      .order_by(topics.c.created.desc()).limit(100))
                if not rows:
                    rows = [await s.db.new_topic(uid)]
                return web.json_response(rows)
            if action == 'new' and request.method == 'POST':
                return web.json_response(await s.db.new_topic(uid))
            tid = data.get('topic') or request.query.get('topic')
            if not isinstance(tid, str) or len(tid) != 32:
                raise web.HTTPBadRequest(text='Mavzuni tanlang.')
            await s.db.topic(uid, tid)
            if action == 'messages' and request.method == 'GET':
                rows = await s.db.rows(select(messages.c.role, messages.c.text).where(
                    messages.c.uid == uid, messages.c.topic == tid).order_by(messages.c.created).limit(300))
                return web.json_response(rows)
            if action == 'chat' and request.method == 'POST':
                text = data.get('text', '')
                if not isinstance(text, str) or not 1 <= len(text.strip()) <= 12000:
                    raise web.HTTPBadRequest(text='1–12000 belgili xabar yozing.')
                if uid in s.active:
                    raise web.HTTPConflict(text='Joriy javobni kuting.')
                s.active[uid] = asyncio.current_task()
                try:
                    answer = await s.answer(uid, tid, text.strip())
                    return web.json_response({'text': answer})
                finally:
                    s.active.pop(uid, None)
            if action == 'rename' and request.method == 'POST':
                title = data.get('title', '')
                if not isinstance(title, str) or not title.strip():
                    raise web.HTTPBadRequest(text='Mavzu nomini yozing.')
                await s.db.execute(update(topics).where(topics.c.uid == uid,
                    topics.c.id == tid).values(title=title.strip()[:80]))
                return web.json_response({'ok': True})
            if action == 'pdf' and request.method == 'GET':
                return web.Response(body=make_pdf(await s.latest(uid, tid)), content_type='application/pdf')
            if action == 'tts' and request.method == 'POST':
                return web.Response(body=await s.speech(uid, await s.latest(uid, tid)), content_type='audio/mpeg')
            raise web.HTTPNotFound(text='Amal topilmadi')
        except web.HTTPException:
            raise
        except Exception as exc:
            return web.json_response({'xato': await s.error(uid, exc)}, status=500)

    async def worker():
        async def process(row):
            state = 'done'
            try:
                await s.dp.feed_update(s.bot, Update.model_validate_json(row['payload']))
            except asyncio.CancelledError:
                state = 'queued'
                raise
            except Exception as exc:
                state = 'failed'
                await s.error(0, exc)
            finally:
                values = {'state': state}
                if state in ('done', 'failed'):
                    values['payload'] = '{}'
                await s.db.execute(update(inbox).where(inbox.c.id == row['id']).values(**values))
        while True:
            if len(s.jobs) < 8:
                rows = await s.db.rows(select(inbox).where(inbox.c.state == 'queued')
                                      .order_by(inbox.c.created).limit(1))
                if rows:
                    row = rows[0]
                    changed = await s.db.execute(update(inbox).where(inbox.c.id == row['id'],
                        inbox.c.state == 'queued').values(state='processing').returning(inbox.c.id))
                    if changed.scalar_one_or_none() is not None:
                        job = asyncio.create_task(process(row))
                        s.jobs.add(job)
                        job.add_done_callback(s.jobs.discard)
            await asyncio.sleep(.15)

    async def startup(app):
        await s.db.start()
        s.session = aiohttp.ClientSession()
        await s.bot.set_my_commands([BotCommand(command=c, description=d) for c, d in [
            ('start', 'Yordamchini ochish'), ('new', 'Yangi mavzu'), ('topics', 'Mavzular'),
            ('sample', 'Ovoz namunasi'), ('stats', 'Foydalanish hisobi'), ('stop', 'To‘xtatish')]])
        if s.url:
            await s.bot.set_webhook(s.url + '/webhook', secret_token=s.secret,
                allowed_updates=['message', 'callback_query'], drop_pending_updates=False)
            app['worker'] = asyncio.create_task(worker())
        else:
            await s.bot.delete_webhook(drop_pending_updates=False)
            app['worker'] = asyncio.create_task(s.dp.start_polling(s.bot, handle_signals=False))
        s.ready = True

    async def shutdown(app):
        s.ready = False
        app['worker'].cancel()
        with suppress(asyncio.CancelledError):
            await app['worker']
        pending = list(s.jobs)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await s.session.close()
        await s.bot.session.close()
        await s.db.engine.dispose()

    app.router.add_get('/', index)
    app.router.add_get('/health', health)
    app.router.add_post('/webhook', webhook)
    app.router.add_route('*', '/api/{action}', api)
    async def sample_audio(request):
        return web.FileResponse(ROOT / 'audio/namuna.mp3')

    app.router.add_get('/audio/namuna.mp3', sample_audio)
    app.on_startup.append(startup)
    app.on_cleanup.append(shutdown)
    return app


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    Path('data').mkdir(exist_ok=True)
    required = ['BOT_TOKEN', 'OPENAI_API_KEY']
    if os.getenv('RENDER_EXTERNAL_URL') or os.getenv('PUBLIC_URL'):
        required += ['DATABASE_URL', 'WEBHOOK_SECRET']
    missing = [x for x in required if not os.getenv(x)]
    if missing:
        raise SystemExit('Sozlanmagan qiymatlar: ' + ', '.join(missing))
    if os.getenv('RENDER_EXTERNAL_URL') and 'sqlite' in os.getenv('DATABASE_URL', ''):
        raise SystemExit('Render uchun doimiy tashqi PostgreSQL DATABASE_URL kiriting.')
    if 'WEBHOOK_SECRET' in required:
        import re
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', os.getenv('WEBHOOK_SECRET', '')):
            raise SystemExit('WEBHOOK_SECRET: 32–256 ta lotin harfi, raqam, _ yoki - kerak.')
    web.run_app(make_app(Service()), host='0.0.0.0', port=int(os.getenv('PORT', '10000')),
                access_log=None, print=lambda _: None)
