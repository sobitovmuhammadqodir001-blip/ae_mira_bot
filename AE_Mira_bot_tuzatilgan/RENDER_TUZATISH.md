# Render joylashini tuzatish

`Publish directory python app.py. does not exist!` xabari Python dasturi ishga tushishidan oldin chiqadi. Render `python app.py.` qiymatini nashr papkasi deb qidirgan. Bu xabar bot ichidagi Python xatosini ko‘rsatmaydi. pip yangilanishi haqidagi notice ham asosiy sabab emas.

## Nimalar tuzatildi?

- Yangiroq ovoz funksiyasiga ega `app (1).py` asosiy `ae_yordamchi/app.py` nomiga keltirildi. Ikkita turli dastur qoldirilmadi.
- `render.yaml` repozitoriy ildiziga ko‘chirildi, `type: web` va `rootDir: ae_yordamchi` belgilandi.
- Ovoz sozlamalari Blueprint’ga qo‘shildi: `TTS_PROVIDER=edge`, `TTS_VOICE=uz-UZ-SardorNeural`. Bu ovoz namunasini klonlash emas, boshqa TTS ovozidir. Foydalanuvchi yuborgan MP3 `audio/namuna.mp3` ichida o‘z holicha saqlangan.

## GitHub’ga yuklash

ZIP’ni oching. `render.yaml` GitHub repozitoriyning eng yuqori qismida, `ae_yordamchi` esa uning yonidagi papka bo‘lsin. Eski `ae_yordamchi/app (1).py` nusxasini olib tashlang. `ae_yordamchi/app.py`ni yangi fayl bilan almashtiring. `audio/`, `static/`, `requirements.txt` va boshqa fayllar ham arxivdagi joyida qolsin.

## Render’da qo‘lda Web Service yaratish

Noto‘g‘ri Static Site’ning Publish Directory maydonini o‘zgartirish botni ishga tushirmaydi. Render’da New → Web Service orqali shu repozitoriyni ulang. Mavjud PostgreSQL bazasini saqlang, uni qayta yaratish shart emas.

| Maydon | Qiymat |
|---|---|
| Language | Python 3 |
| Branch | main |
| Root Directory | ae_yordamchi |
| Build Command | pip install -r requirements.txt |
| Start Command | python app.py |
| Health Check Path | /health |

Start Command oxiriga nuqta qo‘ymang. Ushbu xizmatda Publish Directory maydoni bo‘lmasligi kerak. Region bazangiz bilan bir xil bo‘lsin. Qo‘lda Web Service yaratilganda `render.yaml` Environment sozlamalarini avtomatik ko‘chirmaydi.

Avvalgi haqiqiy `BOT_TOKEN`, `OPENAI_API_KEY`, `DATABASE_URL`, `ADMIN_ID`, `WEBHOOK_SECRET` qiymatlarini yangi Web Service Environment’iga o‘tkazing. `PYTHON_VERSION=3.12.10`, `OPENAI_MODEL=gpt-4.1-mini`, `TTS_PROVIDER=edge`, `TTS_VOICE=uz-UZ-SardorNeural`, `DAILY_REQUEST_LIMIT=50` qo‘shing. Kalitlarni GitHub’ga yuklamang.

Blueprint orqali yaratmoqchi bo‘lsangiz New → Blueprint tanlang: ildizdagi `render.yaml` Web Service va papka yo‘lini belgilaydi. Muhitning maxfiy qiymatlarini baribir kiritish kerak.

## Tekshiruv chegarasi

Python sintaksisi, suhbat va ruxsat testlari hamda ovoz funksiyasining soxta provayder bilan ishlashi mahalliy tekshiriladi. Haqiqiy kalitlar, Render sessiyasi, PostgreSQL serveri va TTS tarmoq xizmati bilan ishga tushirish bu tekshiruvga kirmaydi. Arxiv Render’dagi allaqachon yaratilgan xizmat turini o‘zi o‘zgartirmaydi.

Rasmiy ko‘rsatmalar: https://render.com/docs/web-services va https://render.com/docs/static-sites
