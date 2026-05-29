# 📣 Atlas News — Marketing Toolkit

أدوات تسويق **مشروعة 100%** لنشر الموقع ونموّه. لا اختراق، لا سبام، لا تجاوز لقوانين المنصات — فقط APIs رسمية ومحتوى ذكي.

## المحتويات

| الملف | الغرض |
|-------|-------|
| `launch-posts.md` | منشورات إطلاق جاهزة بـ5 لغات لكل منصة — انسخ والصق |
| `auto_post.py` | سكريبت نشر تلقائي من RSS الموقع إلى Telegram + Mastodon |
| `.posted.json` | (يُنشأ تلقائياً) سجل ما نُشر لتجنب التكرار — لا تحرّره |

---

## 🤖 auto_post.py — النشر التلقائي الشرعي

ينشر أحدث أخبار الموقع تلقائياً على **قناة Telegram** و/أو **حساب Mastodon** عبر APIs الرسمية لكل منصة. يقرأ RSS الموقع نفسه، يتجنّب التكرار، ويحترم حدود المعدّل.

### الإعداد — Telegram (الأسهل والأقوى، مجاني تماماً)

1. افتح **@BotFather** على تيليجرام → `/newbot` → اتبع الخطوات → انسخ الـ token.
2. أنشئ قناة عامة (public channel) باسم مثل `@atlasnews`.
3. أضف البوت كـ **مشرف (administrator)** في القناة.
4. اضبط متغيرات البيئة:

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
export TELEGRAM_CHANNEL_ID="@atlasnews"
```

### الإعداد — Mastodon (شبكة مفتوحة المصدر، مجانية)

1. على نسختك (مثلاً mastodon.social): **Preferences → Development → New application**.
2. الصلاحية المطلوبة: `write:statuses`. انسخ الـ access token.

```bash
export MASTODON_BASE_URL="https://mastodon.social"
export MASTODON_ACCESS_TOKEN="xxxxxxxx"
```

> اضبط ما تملكه فقط — السكريبت ينشر على المنصات المُهيّأة فقط.

### الاستخدام

```bash
# معاينة بلا نشر (ابدأ دائماً بهذا للتأكد):
python marketing/auto_post.py --lang en --max 3 --dry-run

# نشر آخر 3 أخبار إنجليزية:
python marketing/auto_post.py --lang en --max 3

# لغة أخرى:
python marketing/auto_post.py --lang ar --max 2

# feed محدّد:
python marketing/auto_post.py --feed https://atlasnews.solvixi.com/rss-tech.xml --max 2
```

### الأتمتة 24/7 (اختياري)

#### عبر cron (خادم/جهاز يعمل دائماً):
```bash
# كل 3 ساعات — ينشر آخر خبرين بالإنجليزية والعربية
0 */3 * * * cd /path/to/project && TELEGRAM_BOT_TOKEN=... TELEGRAM_CHANNEL_ID=@atlasnews python marketing/auto_post.py --lang en --max 2
30 */3 * * * cd /path/to/project && TELEGRAM_BOT_TOKEN=... TELEGRAM_CHANNEL_ID=@atlasnews_ar python marketing/auto_post.py --lang ar --max 2
```

#### عبر GitHub Actions (موصى به — مجاني):
أضف المفاتيح في **Settings → Secrets**، ثم workflow يستدعي السكريبت كل بضع ساعات.
(يمكن لشريكك إنشاء هذا الـ workflow عند الطلب.)

---

## 🚫 ما لا يفعله هذا التولكيت (بوضوح)

- ❌ لا يسجّل دخولاً لحسابات شخصية ولا يخزّن كلمات مرور
- ❌ لا يتجاوز captcha أو أنظمة كشف البوتات
- ❌ لا spam، لا mass-DM، لا follow/unfollow farming
- ❌ لا ينتحل هوية ولا ينشر محتوى مضلّلاً

كل ما يفعله: ينشر روابط محتوانا على قنواتنا الخاصة عبر APIs رسمية. هذا ما يفعله كل ناشر محترف.

---

## 📈 خارطة طريق التسويق (البشري — الأهم)

1. **Telegram channel** + auto_post → حضور تلقائي 24/7
2. **منشورات الإطلاق** (`launch-posts.md`) على X/FB/LinkedIn — موزّعة على أيام
3. **Reddit/HN** — Show HN + r/SideProject (كن صادقاً، اطلب رأياً)
4. **Google News Publisher** (مهمة يدوية) → آلاف الزيارات العضوية
5. **Newsletter** أسبوعي — حلقة وصل لا تعتمد على خوارزميات أحد
6. **SEO** (مبنيّ بالفعل) → النموّ العضوي طويل المدى
