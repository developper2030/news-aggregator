# 📋 قائمة المهام اليدوية — Atlas News
> **تُحدَّث تلقائياً كلما اكتُشفت مهمة يدوية جديدة**
> المهام اليدوية = تتطلب تسجيل دخول لخدمة خارجية، أو إنشاء حساب، أو تصميم، أو قرار بشري لا يمكن أتمتته.

---

## 🔴 فوري — يعطّل وظائف حالية

### 1. إضافة `GEMINI_API_KEY` في GitHub Secrets
| | |
|--|--|
| **الأثر** | AI summaries معطّلة في كل run على CI — الموقع يُنشر بدون ملخصات |
| **الخطوات** | github.com → repo → Settings → Secrets and variables → Actions → New repository secret |
| **الاسم** | `GEMINI_API_KEY` |
| **القيمة** | `AIzaSyBL5mjg1N793EgtUj4iK-fdYTGSfshTR_0` |
| **الوقت** | ~2 دقيقة |

---

### 2. تقديم كل sitemaps في Google Search Console
| | |
|--|--|
| **الأثر** | Google News لا يكتشف مقالات الـ 48h — لا فهرسة أخبار |
| **الرابط** | https://search.google.com/search-console → Sitemaps |
| **الـ sitemaps المطلوبة (10)** | |

```
https://atlasnews.solvixi.com/sitemap.xml          ← AR
https://atlasnews.solvixi.com/news-sitemap.xml      ← AR

https://atlasnews.solvixi.com/en/sitemap.xml
https://atlasnews.solvixi.com/en/news-sitemap.xml

https://atlasnews.solvixi.com/fr/sitemap.xml
https://atlasnews.solvixi.com/fr/news-sitemap.xml

https://atlasnews.solvixi.com/es/sitemap.xml
https://atlasnews.solvixi.com/es/news-sitemap.xml

https://atlasnews.solvixi.com/tr/sitemap.xml
https://atlasnews.solvixi.com/tr/news-sitemap.xml
```
| **الوقت** | ~10 دقائق |

---

## 🔴 أمان — يجب معالجته قريباً

### 3. تغيير كلمة مرور لوحة التحكم الافتراضية
| | |
|--|--|
| **المشكلة** | كلمة المرور الافتراضية موجودة في الكود المصدري — مكشوفة لأي شخص يقرأ الـ repo |
| **الخطوة اليدوية** | قرر كلمة مرور قوية جديدة (12+ حرف) |
| **بعد القرار** | شريكك يُنجز التغيير برمجياً في `admin.py` |
| **الوقت** | دقيقة واحدة (الاختيار فقط) |

---

## 🟠 تحقيق الدخل — مطلوب قبل AdSense

### 4. إنشاء حساب Google AdSense
| | |
|--|--|
| **الرابط** | https://adsense.google.com |
| **المتطلبات** | حساب Google + الموقع راسخ 90+ يوم بمحتوى حقيقي |
| **بعد الموافقة** | أخبر شريكك بـ Publisher ID (مثال: `pub-1234567890123456`) → سيُفعَّل `ads.txt` تلقائياً |
| **التوقع** | موافقة خلال 1-4 أسابيع |
| **العائد المتوقع** | $600-2,400/شهر عند 100K زيارة/شهر |

---

### 5. إنشاء حساب Google Analytics 4 + إضافة Measurement ID
| | |
|--|--|
| **الرابط** | https://analytics.google.com → Create Property |
| **الخطوات** | إنشاء Property جديد → Web → أدخل `atlasnews.solvixi.com` → انسخ Measurement ID |
| **الشكل** | `G-XXXXXXXXXX` |
| **بعد الحصول عليه** | أضفه في `config/sources.json` (ستجد حقل `ga_id` جاهزاً) |
| **الأهمية** | شرط لـ AdSense + Search Console ربط + قياس الزيارات |
| **الوقت** | ~15 دقيقة |

---

## 🟠 SEO — يُحسّن الفهرسة

### 6. تصميم `og-image.png` (صورة المشاركة)
| | |
|--|--|
| **المشكلة** | الموقع يستخدم `og-image.svg` — فيسبوك/تويتر/واتساب لا يقبلان SVG |
| **المطلوب** | صورة PNG بحجم **1200 × 630 بكسل** |
| **المحتوى المقترح** | شعار Atlas News + خلفية داكنة + "أخبار العالم بـ5 لغات" |
| **أدوات مجانية** | Canva.com → Custom size 1200×630 → تحميل PNG |
| **بعد التصميم** | ضع الملف في `static/og-image.png` وأخبر شريكك |
| **الوقت** | ~20 دقيقة |

---

## 🟠 مفاتيح API اختيارية

### 7. مفتاح MetalpriceAPI (أسعار المعادن)
| | |
|--|--|
| **الوضع الحالي** | `"metalpriceapi": ""` في `config/api_keys.json` — صفحة أسعار المعادن معطّلة |
| **الرابط** | https://metalpriceapi.com — خطة مجانية 100 طلب/شهر |
| **بعد الحصول على المفتاح** | أضفه في `config/api_keys.json` + في GitHub Secrets باسم `METALPRICEAPI_KEY` |

---

### 8. مفتاح Alpha Vantage (أسعار الأسهم والنفط)
| | |
|--|--|
| **الوضع الحالي** | `"alphavantage": ""` — أسعار النفط/أسهم معطّلة |
| **الرابط** | https://www.alphavantage.co/support/#api-key — مجاني 25 طلب/يوم |
| **بعد الحصول على المفتاح** | أضفه في `config/api_keys.json` + في GitHub Secrets باسم `ALPHAVANTAGE_KEY` |

---

## 🟡 قريباً — ميزات مخططة

### 9. إنشاء مشروع Supabase (لـ Emoji Reactions)
| | |
|--|--|
| **الأثر** | تفعيل ميزة ردود الفعل على المقالات (❤️ 👍 😮) |
| **الرابط** | https://supabase.com → New Project → Free tier |
| **المطلوب** | Project URL + anon public key |
| **بعد الإنشاء** | أخبر شريكك بالـ URL والـ key → سيُنجز التكامل كاملاً |

---

## 🟢 مستقبلي — عند النمو

### 10. حساب Google Play Developer (Android TWA)
| | |
|--|--|
| **التكلفة** | 25$ مرة واحدة |
| **الرابط** | https://play.google.com/console |
| **الشرط** | الموقع يحقق 10K+ زيارة/شهر |
| **بعد الإنشاء** | يوم عمل واحد لنشر "Atlas News" على متجر Google Play |

---

### 11. حساب Apple Developer (iOS App Store)
| | |
|--|--|
| **التكلفة** | 99$/سنة |
| **الشرط** | Mac + الموقع يحقق 50K+ زيارة/شهر |
| **ملاحظة** | يحتاج Xcode + اختبار RTL على iOS WebView |

---

### 12. تسجيل domain مستقل (اختياري)
| | |
|--|--|
| **الوضع الحالي** | الموقع على `atlasnews.solvixi.com` (subdomain) |
| **الاقتراح** | `atlasnews.com` أو `atlasnews.news` |
| **الشرط** | قرار تجاري + ~$10-15/سنة |

---

## ✅ مكتملة (للمرجعية)

| المهمة | تاريخ الإنجاز |
|--------|---------------|
| إضافة `CF_API_TOKEN` + `CF_ACCOUNT_ID` + `CF_PROJECT_NAME` في GitHub Secrets | 2026-05-27 |
| التحقق من الموقع في Google Search Console عبر meta tag | 2026-05-28 |
| إضافة `GROQ_API_KEY` في GitHub Secrets | 2026-05-28 |
| إصلاح Node.js 20 deprecation (FORCE_JAVASCRIPT_ACTIONS_TO_NODE24) | 2026-05-29 |

---

## 📌 ملاحظة للتحديث

هذا الملف يُحدَّث تلقائياً من شريكك كلما اكتُشفت مهمة جديدة تتطلب تدخلاً بشرياً.
البريد: developper2030@gmail.com
