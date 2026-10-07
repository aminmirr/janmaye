# Category taxonomy — implemented 2026-10-08, still UNREVIEWED

Amin approved this without reading it. **Review it** (names, grouping, the per-book
assignments) before treating it as settled; changing it later is cheap — edit
`categories.json` (and `migrate_categories.py`'s mapping, then re-run it).

Modelled on Goodreads / Amazon / Audible / Kobo / Blinkist: a small set of broad groups
(7–10) with a few genres inside each. A book carries 1–3 subgenre ids (first = primary);
its groups are derived from them. The list is closed: a new subgenre means editing
`categories.json`, not free-typing at publish time.

## Groups and subgenres

| Group | Subgenres |
|---|---|
| **Business & Management** کسب‌وکار و مدیریت | Management & Leadership مدیریت و رهبری · Startups & Entrepreneurship کارآفرینی و استارتاپ · Strategy & Performance استراتژی و سنجش عملکرد · Marketing & Sales بازاریابی و فروش |
| **Money & Economics** پول و اقتصاد | Economics اقتصاد · Finance & Investing مالی و سرمایه‌گذاری · Personal Finance مالی شخصی |
| **Technology & Computing** فناوری و رایانش | Software Engineering مهندسی نرم‌افزار · Databases & Data Systems پایگاه داده · Data Science & Analytics علم داده و تحلیل · AI & Machine Learning هوش مصنوعی · Privacy & Security حریم خصوصی و امنیت |
| **Science & Math** علم و ریاضی | Statistics & Mathematics آمار و ریاضی · Nature & Life Sciences طبیعت و علوم زیستی · Food & Health غذا و سلامت · Systems & Complexity سیستم‌ها و پیچیدگی |
| **Politics & Society** سیاست و جامعه | Political Theory نظریه‌ی سیاسی · Democracy & Authoritarianism دموکراسی و استبداد · Sociology & Culture جامعه‌شناسی و فرهنگ |
| **Mind & Philosophy** ذهن و فلسفه | Philosophy فلسفه · Psychology روان‌شناسی · Thinking & Decision-making تفکر و تصمیم‌گیری |
| **Self-Development** رشد فردی | Productivity & Career بهره‌وری و شغل · Creativity خلاقیت · Life Design سبک زندگی |
| **History & Biography** تاریخ و زندگی‌نامه | World History تاریخ جهان · Biography زندگی‌نامه |

No book yet in: Marketing & Sales, AI & Machine Learning, Sociology & Culture, and the
whole History & Biography group — they are there so the next book has a home.

## Assignment of the 21 published books (first = primary)

- Moving the Needle with Lean OKRs — Management & Leadership, Strategy & Performance
- Key Performance Indicators — Strategy & Performance, Management & Leadership
- Good to Great — Management & Leadership, Strategy & Performance
- Lean Analytics — Startups & Entrepreneurship, Data Science & Analytics
- Naked Statistics — Statistics & Mathematics
- Exploratory Data Analysis — Statistics & Mathematics, Data Science & Analytics
- Introductory Econometrics for Finance — Finance & Investing, Statistics & Mathematics
- Die with Zero — Personal Finance, Life Design
- The Constitution of Liberty — Political Theory, Economics
- The Narrow Corridor — Democracy & Authoritarianism, Economics
- Autocracy Inc — Democracy & Authoritarianism
- The Open Society and Its Enemies — Political Theory, Philosophy
- The Psychology of Totalitarianism — Democracy & Authoritarianism, Psychology
- Honeybee Democracy — Nature & Life Sciences
- FOOD (Potter & Hotchkiss) — Food & Health
- Thinking in Systems — Systems & Complexity, Thinking & Decision-making
- Cloud Native Database — Databases & Data Systems
- Designing Data-Intensive Applications — Databases & Data Systems, Software Engineering
- Database Anonymization — Privacy & Security, Databases & Data Systems
- Learning Domain-Driven Design — Software Engineering
- Show Your Work! — Creativity, Productivity & Career
