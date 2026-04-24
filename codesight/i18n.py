import os

_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "scan_complete": "Scan Complete",
        "no_source_files": "No source files found.",
        "found_files": "Found {count} files in {dir}",
        "directory_not_found": "Directory not found: {path}",
        "config_error": "Config error: {error}",
        "analyzing": "Analyzing...",
        "scanning": "Scanning...",
        "files_analyzed": "{count} files analyzed",
        "files_failed": ", {count} failed",
        "tokens_total": " - {tokens} tokens total",
        "no_api_key": "No API key configured. Run: codesight config",
        "estimate_header": "Estimate {count} files, ~{prompt} in + ~{output} out tokens",
        "estimate_cost": "total ~{cost} on {model}",
        "estimate_dry_run": "No API call made. Drop --estimate to run for real.",
        "file_too_large": "File too large: {size}KB (limit: {limit}KB).",
        "file_not_found": "File not found: {path}",
        "provider_connection_ok": "Connection OK",
        "provider_connection_fail": "Connection failed",
    },
    "ru": {
        "scan_complete": "Скан завершён",
        "no_source_files": "Исходные файлы не найдены.",
        "found_files": "Найдено {count} файлов в {dir}",
        "directory_not_found": "Директория не найдена: {path}",
        "config_error": "Ошибка конфига: {error}",
        "analyzing": "Анализирую...",
        "scanning": "Сканирую...",
        "files_analyzed": "Проанализировано файлов: {count}",
        "files_failed": ", провалено: {count}",
        "tokens_total": " - всего токенов: {tokens}",
        "no_api_key": "API-ключ не настроен. Запусти: codesight config",
        "estimate_header": "Оценка: {count} файлов, ~{prompt} вход + ~{output} выход токенов",
        "estimate_cost": "итого ~{cost} на {model}",
        "estimate_dry_run": "API не вызывался. Убери --estimate чтобы запустить реально.",
        "file_too_large": "Файл слишком большой: {size}KB (лимит: {limit}KB).",
        "file_not_found": "Файл не найден: {path}",
        "provider_connection_ok": "Соединение OK",
        "provider_connection_fail": "Соединение не удалось",
    },
}

_DEFAULT_LANG = "en"
_current_lang = _DEFAULT_LANG


def set_language(lang: str | None) -> None:
    global _current_lang
    _current_lang = lang if lang and lang in _MESSAGES else _DEFAULT_LANG


def current_language() -> str:
    return _current_lang


def resolve_language(config_lang: str | None) -> str:
    # Precedence: env var CODESIGHT_LANG, config.language, default.
    env_lang = os.environ.get("CODESIGHT_LANG")
    for candidate in (env_lang, config_lang):
        if candidate and candidate in _MESSAGES:
            return candidate
    return _DEFAULT_LANG


def t(key: str, **kwargs) -> str:
    # Missing-key fallback: return the key itself so regressions are loud.
    table = _MESSAGES.get(_current_lang, _MESSAGES[_DEFAULT_LANG])
    template = table.get(key) or _MESSAGES[_DEFAULT_LANG].get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template


def available_languages() -> list[str]:
    return list(_MESSAGES.keys())
