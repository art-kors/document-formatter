import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.schemas.document import DocumentInput
from app.schemas.orchestrator_result import OrchestratorResult


def write_analysis_log(
    *,
    document: DocumentInput,
    result: OrchestratorResult,
    runtime_modes: Dict[str, str],
    source_format: str,
    file_size_bytes: int,
    parsing_time_ms: int,
    request_wall_time_ms: int,
    request_cpu_time_ms: int,
) -> str:
    log_dir = _resolve_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc)
    payload = _build_compact_payload(
        timestamp=timestamp,
        document=document,
        result=result,
        runtime_modes=runtime_modes,
        source_format=source_format,
        file_size_bytes=file_size_bytes,
        parsing_time_ms=parsing_time_ms,
        request_wall_time_ms=request_wall_time_ms,
        request_cpu_time_ms=request_cpu_time_ms,
    )
    payload['human_summary'] = _build_human_summary(payload)

    filename = f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{_safe_slug(document.document_id or document.meta.filename or 'document')}.json"
    path = log_dir / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(path)


def _resolve_log_dir() -> Path:
    env_value = (os.getenv('ANALYSIS_LOG_DIR') or 'logs').strip()
    return Path(env_value)


def _build_compact_payload(
    *,
    timestamp: datetime,
    document: DocumentInput,
    result: OrchestratorResult,
    runtime_modes: Dict[str, str],
    source_format: str,
    file_size_bytes: int,
    parsing_time_ms: int,
    request_wall_time_ms: int,
    request_cpu_time_ms: int,
) -> Dict[str, Any]:
    memory_stats = _read_memory_stats()
    return {
        'timestamp_utc': timestamp.isoformat(),
        'document_id': document.document_id,
        'filename': document.meta.filename,
        'standard_id': document.standard_id,
        'source_format': source_format,
        'file_size_bytes': file_size_bytes,
        'observed_pages': _observed_page_count(document),
        'sections_count': len(document.sections),
        'paragraphs_count': len(document.paragraphs),
        'tables_count': len(document.tables),
        'figures_count': len(document.figures),
        'chat_mode': runtime_modes.get('chat_mode', 'default'),
        'embed_mode': runtime_modes.get('embed_mode', 'default'),
        'local_chat_model': os.getenv('LOCAL_CHAT_MODEL', ''),
        'local_embedding_model': os.getenv('LOCAL_EMBEDDING_MODEL', ''),
        'request_wall_time_ms': request_wall_time_ms,
        'request_cpu_time_ms': request_cpu_time_ms,
        'parsing_time_ms': parsing_time_ms,
        'analysis_time_ms': result.processing_time_ms,
        'status': result.status,
        'total_issues': result.summary.total_issues,
        'critical_issues': result.summary.critical,
        'warning_issues': result.summary.warning,
        'info_issues': result.summary.info,
        'fixable_issues': result.summary.fixable,
        'issues_by_type': result.summary.by_type,
        'agents_run': result.agents_run,
        'agents_failed': result.agents_failed,
        'cpu_count': os.cpu_count(),
        'cpu_name': platform.processor(),
        'system_memory_total_mb': memory_stats.get('total_mb'),
        'system_memory_available_mb': memory_stats.get('available_mb'),
        'system_memory_load_percent': memory_stats.get('load_percent'),
        'process_rss_mb': memory_stats.get('process_rss_mb'),
        'process_peak_rss_mb': memory_stats.get('process_peak_rss_mb'),
        'platform': platform.platform(),
        'python': sys.version.split()[0],
    }


def _build_human_summary(payload: Dict[str, Any]) -> str:
    lines = [
        'Статистика запуска проверки документа',
        f"Документ: {payload.get('filename') or '-'} (id: {payload.get('document_id') or '-'})",
        f"Стандарт: {payload.get('standard_id') or '-'}",
        f"Формат источника: {payload.get('source_format') or '-'}",
        f"Размер файла: {_format_bytes(payload.get('file_size_bytes'))}",
        f"Страницы по данным parser: {payload.get('observed_pages') if payload.get('observed_pages') is not None else 'не определены'}",
        f"Структура: разделов {payload.get('sections_count', 0)}, абзацев {payload.get('paragraphs_count', 0)}, таблиц {payload.get('tables_count', 0)}, рисунков {payload.get('figures_count', 0)}",
        f"Режимы моделей: chat={payload.get('chat_mode')}, embedding={payload.get('embed_mode')}",
        f"Локальная chat-модель: {payload.get('local_chat_model') or 'не задана'}",
        f"Локальная embedding-модель: {payload.get('local_embedding_model') or 'не задана'}",
        f"Время: весь запрос {payload.get('request_wall_time_ms')} мс, CPU {payload.get('request_cpu_time_ms')} мс, парсинг {payload.get('parsing_time_ms')} мс, анализ {payload.get('analysis_time_ms')} мс",
        f"Результат: статус {payload.get('status')}, всего ошибок {payload.get('total_issues')}, критических {payload.get('critical_issues')}, warning {payload.get('warning_issues')}, info {payload.get('info_issues')}, автоисправимых {payload.get('fixable_issues')}",
        f"Ошибки по типам: {_format_issue_types(payload.get('issues_by_type') or {})}",
        f"Агенты: отработали {_format_agents(payload.get('agents_run') or [])}; с ошибками {_format_failed_agents(payload.get('agents_failed') or {})}",
        f"Система: CPU потоков {payload.get('cpu_count') if payload.get('cpu_count') is not None else 'не определено'}, имя CPU {payload.get('cpu_name') or 'не определено'}",
        f"Память: всего {payload.get('system_memory_total_mb') if payload.get('system_memory_total_mb') is not None else 'не определено'} МБ, доступно {payload.get('system_memory_available_mb') if payload.get('system_memory_available_mb') is not None else 'не определено'} МБ, загрузка {payload.get('system_memory_load_percent') if payload.get('system_memory_load_percent') is not None else 'не определено'}%, RSS процесса {payload.get('process_rss_mb') if payload.get('process_rss_mb') is not None else 'не определено'} МБ, peak RSS {payload.get('process_peak_rss_mb') if payload.get('process_peak_rss_mb') is not None else 'не определено'} МБ",
        f"Окружение: {payload.get('platform') or '-'}, Python {payload.get('python') or '-'}",
    ]
    return '\n'.join(lines)


def _format_bytes(value: Any) -> str:
    if not isinstance(value, int):
        return 'не определен'
    if value < 1024:
        return f'{value} Б'
    if value < 1024 * 1024:
        return f'{value / 1024:.1f} КБ'
    return f'{value / (1024 * 1024):.2f} МБ'


def _format_issue_types(value: Dict[str, Any]) -> str:
    if not value:
        return 'нет данных'
    return ', '.join(f'{key}: {count}' for key, count in sorted(value.items()))


def _format_agents(value: list[str]) -> str:
    return ', '.join(value) if value else 'нет данных'


def _format_failed_agents(value: Dict[str, Any]) -> str:
    if not value:
        return 'нет'
    return ', '.join(f'{key}: {error}' for key, error in value.items())


def _observed_page_count(document: DocumentInput) -> Optional[int]:
    pages = [item.position.page for item in document.paragraphs if item.position.page]
    pages.extend(item.position.page for item in document.tables if item.position.page)
    pages.extend(item.position.page for item in document.figures if item.position.page)
    return max(pages) if pages else None


def _safe_slug(value: str) -> str:
    normalized = ''.join(ch if ch.isalnum() else '_' for ch in value.lower())
    collapsed = '_'.join(part for part in normalized.split('_') if part)
    return collapsed[:80] or 'document'


def _read_memory_stats() -> Dict[str, Optional[int]]:
    if sys.platform.startswith('linux'):
        return _read_linux_memory_stats()
    if sys.platform.startswith('win'):
        return _read_windows_memory_stats()
    return {
        'total_mb': None,
        'available_mb': None,
        'load_percent': None,
        'process_rss_mb': None,
        'process_peak_rss_mb': None,
    }


def _read_linux_memory_stats() -> Dict[str, Optional[int]]:
    total_mb = None
    available_mb = None
    rss_mb = None
    try:
        for line in Path('/proc/meminfo').read_text(encoding='utf-8').splitlines():
            if line.startswith('MemTotal:'):
                total_mb = int(line.split()[1]) // 1024
            elif line.startswith('MemAvailable:'):
                available_mb = int(line.split()[1]) // 1024
        for line in Path('/proc/self/status').read_text(encoding='utf-8').splitlines():
            if line.startswith('VmRSS:'):
                rss_mb = int(line.split()[1]) // 1024
                break
    except Exception:
        pass

    load_percent = None
    if total_mb and available_mb is not None and total_mb > 0:
        load_percent = int(round(((total_mb - available_mb) / total_mb) * 100))
    return {
        'total_mb': total_mb,
        'available_mb': available_mb,
        'load_percent': load_percent,
        'process_rss_mb': rss_mb,
        'process_peak_rss_mb': None,
    }


def _read_windows_memory_stats() -> Dict[str, Optional[int]]:
    try:
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ('dwLength', wintypes.DWORD),
                ('dwMemoryLoad', wintypes.DWORD),
                ('ullTotalPhys', ctypes.c_ulonglong),
                ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong),
                ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong),
                ('ullAvailVirtual', ctypes.c_ulonglong),
                ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
            ]

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ('cb', wintypes.DWORD),
                ('PageFaultCount', wintypes.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t),
                ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t),
                ('PeakPagefileUsage', ctypes.c_size_t),
            ]

        memory = MEMORYSTATUSEX()
        memory.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)

        return {
            'total_mb': int(memory.ullTotalPhys // (1024 * 1024)),
            'available_mb': int(memory.ullAvailPhys // (1024 * 1024)),
            'load_percent': int(memory.dwMemoryLoad),
            'process_rss_mb': int(counters.WorkingSetSize // (1024 * 1024)) if ok else None,
            'process_peak_rss_mb': int(counters.PeakWorkingSetSize // (1024 * 1024)) if ok else None,
        }
    except Exception:
        return {
            'total_mb': None,
            'available_mb': None,
            'load_percent': None,
            'process_rss_mb': None,
            'process_peak_rss_mb': None,
        }
