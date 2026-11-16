# AE Yordamchi — ishga tushirish

Bu haqiqiy bot kodi va Telegram Mini App boshlang‘ich versiyasi. Mira’ning kodi yoki yopiq API’sidan foydalanmaydi. Matn uchun OpenAI Responses API, ovozdan matn uchun OpenAI Transcriptions API, ixtiyoriy ovozli javob uchun ElevenLabs ishlatiladi. Bot faqat shaxsiy chatlarda ishlaydi.

## Qaysi kalitlar kerak?

| Qiymat | Qayerdan olinadi | Vazifasi |
|---|---|---|
| BOT_TOKEN | Telegram’dagi rasmiy @BotFather | Botni ulash |
| OPENAI_API_KEY | https://platform.openai.com/api-keys | AI javob va ovozdan matn |
| ELEVENLABS_API_KEY | ElevenLabs hisobingiz | Yangi matndan ovoz yaratish, ixtiyoriy |
| ELEVENLABS_VOICE_ID | ElevenLabs’dagi tanlangan ovoz | Yangi javoblarning ovozi, ixtiyoriy |
| WEBHOOK_SECRET | Render avtomatik yaratadi yoki o‘zingiz tasodifiy yaratasiz | Webhook so‘rovini tasdiqlash |
| DATABASE_URL | O‘zingizning tashqi PostgreSQL xizmatingiz | Xabarlar, mavzular, sarf va navbatni saqlash |
| ADMIN_ID | O‘zingizning raqamli Telegram user ID’ingiz | Xatolar haqida xabar va admin hisobi |

Kalitlarni chatga, GitHub’ga yoki brauzer kodiga yozmang. `.env.example` ichida haqiqiy kalit yo‘q. Kalitlar Render Environment’da saqlanadi. OpenAI va ElevenLabs xarajatlari hisobingiz tarifiga bog‘liq; kod bepul beriladi, cheksiz bepul AI va’da qilinmaydi. OpenAI hisobida API’dan foydalanish imkoniyati va mablag‘/kredit mavjudligini tekshiring.

## Siz yuborgan ovoz

`audio/namuna.mp3` — aynan biriktirgan MP3 faylingizning nusxasi. `/sample`, botdagi “Ovoz namunasi” va Mini App’dagi “Siz yuborgan ovoz” shu yozuvni ijro etadi. U salomlashuvga mosligi tekshirilmagan, shuning uchun avtomatik salomlashuv sifatida yuborilmaydi.

Har bir yangi javob aynan shu ohangda o‘qilishi uchun yozuv olingan ovozning ElevenLabs `VOICE_ID` qiymati kerak. MP3’dan `VOICE_ID` yoki API kaliti chiqarib olinmaydi. Ular bo‘lmasa bot matnda ishlaydi va ovoz namunasi tinglanadi; yangi ovozli javob tugmasi sozlama kerakligini aytadi. Ovoz klonlash bajarilmagan, audio boshqa xizmatga yuklanmagan. TTS mosligi va o‘zbekcha talaffuz tanlagan ovoz/modelingiz bilan tekshiriladi.

## GitHub → Render

1. ZIP’ni oching. Yangi GitHub repozitoriy yarating.
2. `ae_yordamchi` papkasining **ichidagi** barcha fayllarni, jumladan `static/` va `audio/` papkalarini repozitoriy ildiziga yuklang. ZIP’ning o‘zini yuklash yetarli emas. `.env` yuklamang.
3. Tashqi doimiy PostgreSQL bazasi yarating yoki mavjud bazangiz ulanishini oling. Bazaga TLS bilan ulanishni provayder ko‘rsatmasiga moslang; `postgres://`, `postgresql://` va `postgresql+asyncpg://` qo‘llanadi. SSL kerak bo‘lsa asyncpg uchun `?ssl=require` ishlatiladi; `sslmode` parametrini bevosita bermang.
4. Render’da “New → Blueprint” orqali GitHub repozitoriyni tanlang. `render.yaml` bot xizmatini yaratadi. Yoki qo‘lda Python Web Service: Build `pip install -r requirements.txt`, Start `python app.py`.
5. Environment’da `BOT_TOKEN`, `OPENAI_API_KEY`, `DATABASE_URL`, `ADMIN_ID` kiriting. Blueprint `WEBHOOK_SECRET` yaratadi; qo‘lda xizmatda kamida 32 belgili tasodifiy qiymat bering. `OPENAI_MODEL=gpt-4.1-mini` boshlang‘ich model, hisobingizdagi mavjud model bilan almashtirish mumkin.
6. Ixtiyoriy: `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID=eleven_v3`. Shu ovoz avval boshqa modeldan olingan bo‘lsa mos modelni tanlang.
7. Deploy qiling. Render `RENDER_EXTERNAL_URL` qiymatini beradi, webhook avtomatik o‘rnatiladi. Bitta bot tokeni uchun boshqa bot dasturini bir paytda ishlatmang: webhook manzili bittadir.
8. Telegram’da botga `/start` yuboring. “Ilovani ochish” tugmasi Mini App’ni ochadi. API imzosi haqiqiy Telegram sessiyasini tekshiradi; oddiy brauzerdagi ko‘rinish suhbatga ruxsat bermaydi.

`render.yaml` bazani avtomatik yaratmaydi. Tashqi bazasiz Render’da xotirani doimiy saqlash va’da qilinmaydi. Dastur Render’da SQLite’ni rad etadi. Render Free uyquga ketishi mumkin; birinchi so‘rov sekinlashishi mumkin. To‘xtovsiz ishlash uchun uyquga ketmaydigan xizmat tanlash kerak.

## Windows’da mahalliy ishlatish

Python 3.12 o‘rnatilgan bo‘lsin. Papka ichida PowerShell orqali:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.venv\Scripts\python.exe app.py
```

`.env` ichida `BOT_TOKEN`, `OPENAI_API_KEY` kiriting. `PUBLIC_URL` bo‘sh bo‘lsin. Mahalliy SQLite `data/bot.db` ichida saqlanadi, bot polling orqali ishlaydi. Shu rejimda Mini App tashqaridan ochilmaydi; Telegram tugmasi faqat ommaviy HTTPS manzili bilan ishlaydi. Bir token uchun mahalliy va Render xizmatlarini bir vaqtda yoqmang.

## Tayyor imkoniyatlar

- Matnli AI suhbat, har mavzu uchun oxirgi 20 xabardan kontekst.
- Mavzu yaratish, tanlash, nomlash, `/clear` bilan joriy tarixni o‘chirish.
- Telegram ovozli xabarini matnga aylantirish: 2 daqiqa / 10 MB gacha.
- Javobni PDF qilish, o‘zbekcha belgilar uchun biriktirilgan Unicode shrift.
- Sizning MP3’ingizni tinglash; sozlangan ElevenLabs ovozida yangi javoblar.
- Telegram chatida `/stop`; Mini App’da so‘rov tugaguncha yuborish bloklanadi.
- Har foydalanuvchi uchun kunlik 50 AI amal limiti; STT va keyingi matn javobi alohida hisoblanadi. Xato bo‘lgan urinish ham limitdan sarflanadi.
- `/stats` orqali token hisobi. INPUT_USD_PER_MILLION va OUTPUT_USD_PER_MILLION berilsa matn xarajatining taxmini; audio sarfi dollar hisobiga kirmaydi. TTS belgilar soni bazada saqlanadi.
- `/admin` faqat ADMIN_ID egasiga umumiy hisobni beradi.
- Xato kodi foydalanuvchiga, xato turi va user ID adminga. Kalitlar va xabar matni logga ataylab chiqarilmaydi.
- Webhook yangilanishlari bazaga yozilgandan so‘ng qabul qilinadi; bir update ID qayta qabul qilinsa takror navbatga qo‘shilmaydi.

## Amaliy chegaralar

Bu boshlang‘ich versiya. Internet qidiruvi, rasm/video generatsiyasi, rejalashtirilgan eslatmalar, xizmatlarni OAuth bilan ulash va DOCX yaratish qo‘shilmagan. Rasmda ko‘rsatilgan barcha funksiyalarni tayyor deb hisoblamang. Mini App’dagi ko‘rinish o‘sha konsept asosidagi haqiqiy sodda interfeysdir.

Faqat bitta xizmat nusxasini ishlating. So‘rov qayta ishlanayotganda server uzilsa navbat qayta olinadi; provayder allaqachon ishlagan bo‘lsa AI xarajati yoki javob takrorlanishi mumkin. Tashqi API bilan mutlaq “bir marta” kafolati berilmaydi. Bekor qilingan AI so‘roviga ham provayder sarf yozishi mumkin. Tanlangan Telegram mavzusi server qayta ishga tushganda so‘nggi yaratilgan mavzuga qaytadi; mavzularning o‘zi bazada qoladi.

Xabarlar bazada saqlanadi. Navbatdagi webhook payload’i bajarilgach tozalanadi; update ID takrorlarni rad etish uchun qoladi. `/clear` joriy mavzu xabarlarini o‘chiradi; hali navbatda turgan yangi so‘rovlar bajarilishi mumkin. Ushbu paket API kalitlaringizsiz haqiqiy Telegram/OpenAI/ElevenLabs integratsiyasi bilan sinovdan o‘tkazilmagan.

## Sinov

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Sinovlar imzo buzilishi va eskirishi, mavzu egasi bo‘yicha ruxsat, kunlik limit, webhook takrorini rad etish, soxta provayder orqali suhbat konteksti, PDF hamda autentifikatsiyasiz HTTP so‘rovlarini tekshiradi. Haqiqiy model sifati va ovoz bir xilligi kalitlar bilan keyin tekshiriladi.

## Rasmiy manbalar

- https://developers.openai.com/api/docs/guides/text
- https://docs.aiogram.dev/en/latest/dispatcher/webhook.html
- https://core.telegram.org/bots/api
- https://elevenlabs.io/docs/api-reference/text-to-speech/convert
- https://render.com/docs/free

PDF shrifti DejaVu Sans; litsenziyasi `static/SHRIFT_LITSENZIYASI.txt` faylida.
