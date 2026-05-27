# News Aggregator

**ملخص الأخبار الأسبوعي** — أداة تجمع عناوين الأخبار من مواقع متعددة بدون API أو RSS، وتُنشئ موقعاً ثابتاً بتصميم صحفي احترافي.

## الميزات

- **5 تصنيفات**: سياسة، اقتصاد، تكنولوجيا، رياضة، صحة وعلوم
- **14 مصدراً** عربياً وعالمياً مع CSS selectors مخصصة
- **تصميم صحفي** على طراز المواقع الإخبارية الكبرى
- **وضع مظلم / فاتح** مع حفظ التفضيل
- **بحث فوري** داخل الأخبار (client-side)
- **شريط أخبار عاجلة** متحرك
- **متجاوب تماماً** مع الهواتف والأجهزة اللوحية
- **جاهز لـ Google AdSense** (meta tags, Schema.org, صفحة خصوصية)
- **لوحة تحكم** كاملة لإدارة المصادر والتصنيفات
- **تشغيل تلقائي** عبر GitHub Actions (يومياً)
- **أمان محسّن**: XSS prevention، URL sanitization، token-based auth

## الإعداد المحلي

```bash
# 1. تثبيت المتطلبات
pip install -r requirements.txt

# 2. تشغيل الجلب وتوليد الموقع
python run.py
```

النتيجة في `static/index.html`.

## لوحة التحكم

```bash
python admin.py
```

تفتح لوحة تحكم على `http://127.0.0.1:8080`. 

- **كلمة المرور الافتراضية**: `newsadmin123`
- **لتغييرها**: `set ADMIN_PASSWORD=كلمة_المرور_الجديدة` (Windows) أو `export ADMIN_PASSWORD=...` (Linux/Mac)

### ميزات لوحة التحكم
- إضافة/حذف التصنيفات والمصادر
- تعديل CSS selectors لكل مصدر
- تشغيل الجلب وتوليد الموقع مباشرة
- معاينة المخرجات في الوقت الفعلي

## إضافة مصادر جديدة

عبر لوحة التحكم (موصى به)، أو بتعديل `config/sources.json` يدوياً:

```json
{
  "name": "اسم الموقع",
  "url": "https://example.com",
  "selectors": {
    "article_selector": "article, .post",
    "heading_tags": ["h2", "h3"],
    "exclude_classes": ["footer", "nav", "sidebar"],
    "exclude_id_patterns": ["footer", "nav"],
    "min_title_length": 20
  }
}
```

## Google AdSense

الموقع مُهيَّأ مسبقاً لـ AdSense:

1. `static/privacy.html` — صفحة الخصوصية (مطلوبة)
2. `static/about.html` — صفحة من نحن (مطلوبة)
3. مناطق إعلانية جاهزة في `index.html` (ابحث عن `<!-- Google AdSense -->`)
4. Schema.org structured data مضاف
5. جميع meta tags المطلوبة موجودة

**بعد الحصول على الموافقة**: أدرج كود AdSense في المناطق المخصصة داخل `generate_site.py`.

## النشر على GitHub Pages

1. ارفع المستودع إلى GitHub
2. فعّل GitHub Pages من مجلد `static/`
3. الـ Action يُشغّل الجلب يومياً وينشر التحديثات تلقائياً
4. حدّث رابط الـ canonical في `generate_site.py` وملف `robots.txt`

## بنية الملفات

```
├── run.py                  ← نقطة الدخول الرئيسية
├── admin.py                ← لوحة التحكم (HTTP server)
├── generate_site.py        ← مولّد الموقع الثابت
├── config/
│   ├── sources.json        ← إعدادات المصادر
│   └── loader.py           ← قارئ الإعدادات
├── scraper/scrape.py       ← محرك الكشط
├── database/
│   ├── schema.sql          ← مخطط SQLite
│   └── db.py               ← طبقة قاعدة البيانات
├── static/                 ← الموقع الناتج (مُنشأ تلقائياً)
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   ├── privacy.html
│   └── about.html
└── tests/test_parser.py    ← اختبارات وحدة
```

## الترخيص

MIT
