# Sinov natijasi

2026-11-16 kuni Python 3.12 muhitida 16 ta avtomatik sinov muvaffaqiyatli o‘tdi. Python kompilyatsiyasi va Mini App JavaScript sintaksisi ham tekshirildi. Audio namunasining SHA-256 qiymati foydalanuvchi yuborgan fayl bilan bir xil.

Tekshirildi: haqiqiy shakldagi Telegram imzosi, buzilgan/eskirgan/takrorlangan imzo maydonlarini rad etish; mavzu egasi bo‘yicha ruxsat; parallel kunlik limit; kun almashishi; webhook update ID takrori; soxta AI javobi bilan suhbat konteksti va token yozilishi; Unicode PDF; autentifikatsiyasiz HTTP so‘rovini rad etish; noto‘g‘ri webhook siri; sahifa va audio faylining HTTP orqali berilishi.

Haqiqiy Telegram bot tokeni, OpenAI va ElevenLabs API kalitlari mavjud bo‘lmagani sabab ushbu xizmatlarga haqiqiy so‘rov yuborilmadi. PostgreSQL serveriga ulanish va Render deploy bajarilmadi. Ovoz o‘xshashligi, model sifati va Telegram Mini App ichidagi vizual ko‘rinish qurilmada sinovdan o‘tkazilmadi.

Sinovni qaytarish: `python -m unittest discover -s tests -v`.

Tuzatish: yangi Edge TTS yo‘li soxta provayder bilan va noma’lum TTS provayderini rad etish qo‘shimcha tekshirildi. Haqiqiy ovoz tarmoq xizmati tekshirilmagan.
