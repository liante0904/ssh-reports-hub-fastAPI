"""Shared, side-effect-free report API response normalization."""

import json
from datetime import datetime


VIEW_TO_API_KEY_MAP = {
    'firm_id': 'firm_id', 'board_id': 'board_id', 'firm_nm': 'firm_nm', 'mkt_tp': 'mkt_tp',
    'report_date': 'report_date', 'article_title': 'article_title', 'telegram_url': 'telegram_url',
    'pdf_file_url': 'pdf_file_url', 'writer': 'writer', 'gemini_summary': 'gemini_summary',
    'tags': 'tags', 'stock_names': 'stock_names', 'sector': 'sector', 'target_price': 'target_price',
    'rating': 'rating', 'revision_type': 'revision_type', 'report_type': 'report_type',
    'stock_tickers': 'stock_tickers', 'save_at': 'save_at', 'report_unique_key': 'report_unique_key',
    'source_url': 'source_url', 'summary_time': 'summary_time', 'summary_model': 'summary_model',
    'telegram_sent': 'telegram_sent', 'report_id': 'report_id',
}


def parse_json_field(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    return []


def view_row_to_api_item(row) -> dict:
    if isinstance(row, dict) and 'report_id' in row and 'pdf_archive' in row:
        return row
    mapping = row._mapping if hasattr(row, '_mapping') else row
    item = {api_key: mapping.get(view_col) for view_col, api_key in VIEW_TO_API_KEY_MAP.items()}
    item['is_direct'] = (str(mapping.get('is_direct', '')) == 'Y') or None
    item['send_user'] = None
    item['scraped_at'] = mapping.get('scraped_at') or mapping.get('save_at')
    if isinstance(item['scraped_at'], datetime):
        item['scraped_at'] = item['scraped_at'].isoformat()
    elif isinstance(item['scraped_at'], str):
        item['scraped_at'] = item['scraped_at'].replace(' ', 'T', 1)
    for field in ('tags', 'stock_names', 'stock_tickers'):
        item[field] = parse_json_field(item.get(field))
    item['pdf_archive'] = {key[4:]: mapping.get(key) for key in ('pdf_report_id', 'pdf_file_path', 'pdf_file_size', 'pdf_page_count', 'pdf_archive_status', 'pdf_file_name', 'pdf_has_text', 'pdf_is_encrypted', 'pdf_storage_backend', 'pdf_storage_key', 'pdf_author', 'pdf_created_at', 'pdf_updated_at', 'pdf_last_accessed_at')} if mapping.get('pdf_report_id') is not None else None
    item['fnguide_summary'] = {key[3:]: mapping.get(key) for key in ('fs_summary_id', 'fs_source_page_url', 'fs_report_date', 'fs_company_name', 'fs_company_code', 'fs_report_title', 'fs_summary_text', 'fs_opinion', 'fs_target_price', 'fs_prev_close', 'fs_provider', 'fs_author', 'fs_article_url', 'fs_pdf_url', 'fs_report_key', 'fs_item_rank', 'fs_sync_status', 'fs_created_at', 'fs_updated_at')} if mapping.get('fs_summary_id') is not None else None
    if item.get('target_price') is not None:
        try:
            item['target_price'] = float(item['target_price'])
        except (ValueError, TypeError):
            pass
    return item


def collection_response(request, items: list, limit: int, offset: int, has_more: bool) -> dict:
    return {'items': [view_row_to_api_item(row) for row in items], 'hasMore': has_more, 'limit': limit, 'offset': offset, 'count': len(items), 'links': [{'rel': 'self', 'href': str(request.url)}, {'rel': 'first', 'href': str(request.url.include_query_params(offset=0))}]}
