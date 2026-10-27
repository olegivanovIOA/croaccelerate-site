# croaccelerate.com — новый сайт (static + headless WordPress)

```
site/
├── build.py                 # сборщик: шаблоны + контент + посты из WP → dist/
├── content.py               # тексты услуг, 4 кейса, FAQ (редактировать здесь)
├── site.config.json         # GTM ID, endpoint лидов, Calendly, контакты, WP API
├── templates/               # Jinja2-шаблоны страниц
├── static/                  # css (liquid glass), js (трекинг, формы, скоркард), img
├── static_root/             # _redirects (старые URL → новые), _headers, llms.txt
├── content/posts/*.md       # локальные статьи (первая — пиллар «Fractional CINO»)
├── content/pages/           # privacy, thank-you
├── apps-script/LeadCapture.gs   # формы → Google Sheet + email + Telegram
├── gtm/GTM-croaccelerate-container.json   # импорт в Tag Manager
├── wordpress/croaccelerate-headless.php   # mu-plugin для WP (headless-мост)
└── .github/workflows/       # rebuild.yml (каждые 6 ч), check.yml (проверка сборки)
```

## Локально
```bash
pip install -r requirements.txt
python build.py --offline      # без WordPress
python -m http.server -d dist 8000
```

## Как это работает
GitHub (исходники) → GitHub Actions собирает сайт (`build.py`, посты тянутся из WordPress по REST API) →
SFTP-заливка в корень WordPress на GoDaddy. Реальные файлы и папки (/services/, /cases/, /blog/, /static/ …)
веб-сервер отдаёт напрямую; всё остальное попадает в WordPress, где mu-плагин отдаёт статическую главную,
делает 301-редиректы со старых адресов и показывает статический 404. Админка, REST API и картинки
WordPress остаются на том же домене. DNS и хостинг не меняются.

Автодеплой: push в main · публикация/правка поста в WordPress · каждые 6 часов · вручную (Actions → Run workflow).
Аварийный выключатель: убрать `CRA_STATIC_HOME` из wp-config.php → на главной снова старый WordPress.

## Запуск
Пошагово — в чате/документе «CROAccelerate 2.0 — стратегия и запуск». Кратко:
1. Google Sheet + Apps Script → URL `/exec`.
2. GA4 + GTM (импорт `gtm/GTM-croaccelerate-container.json`).
3. GitHub: репозиторий `croaccelerate-site`, Secrets: `SFTP_HOST`, `SFTP_PORT`, `SFTP_USER`, `SFTP_PASSWORD`, `SFTP_PATH`;
   Variables: `GTM_ID`, `LEAD_ENDPOINT`.
4. WordPress: mu-плагин `wordpress/croaccelerate-headless.php` → `wp-content/mu-plugins/`, константы в wp-config.php.
5. Первый деплой → проверить → включить `CRA_STATIC_HOME` → сбросить кэш GoDaddy.
6. Search Console → sitemap.xml.

## Перед запуском
- Контакты и тексты — `site.config.json`, `content.py`; GTM ID и URL Apps Script — GitHub Variables `GTM_ID`, `LEAD_ENDPOINT`.
