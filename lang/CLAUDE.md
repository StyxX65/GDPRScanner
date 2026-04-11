# lang/ — i18n Rules

- `en.json` is the source of truth. Always update `da.json` and `de.json` when adding or changing keys.
- `/api/langs` globs both `*.json` and `*.lang` — both formats coexist.
- Loader in `app_config.py` prefers `.json`, falls back to `.lang`.
- JS: `t(key, default)` — Python: `LANG.get(key, default)`
- No emojis or symbol prefixes in translation values used as button labels.
