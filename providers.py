"""Bốn provider cùng một interface. Không chứa agent loop."""
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid

# Tự động đọc file .env nếu có (không cần cài thêm thư viện ngoài)
def _load_env_file():
    root = Path(__file__).resolve().parent
    env_path = root / '.env'
    if env_path.is_file():
        try:
            for line in env_path.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('export '):
                    line = line[7:].strip()
                if '=' in line:
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip().strip('\'"')
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass

_load_env_file()

CONFIG = {
    'openai': ('OPENAI_API_KEY', 'https://api.openai.com/v1/chat/completions'),
    'gemini': ('GEMINI_API_KEY', 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'),
    'openrouter': ('OPENROUTER_API_KEY', 'https://openrouter.ai/api/v1/chat/completions'),
    'anthropic': ('ANTHROPIC_API_KEY', 'https://api.anthropic.com/v1/messages'),
    'opencode': ('OPENCODE_GO_API_KEY', 'https://opencode.ai/inference/go/openai/v1/chat/completions'),
}


_last_call_time = 0.0


def post_json(url, headers, payload, max_retries=4):
    global _last_call_time
    # Chỉ áp dụng pacing đối với Google Gemini free tier để tránh 15 RPM
    if 'generativelanguage.googleapis.com' in url:
        now = time.time()
        elapsed = now - _last_call_time
        if elapsed < 4.2:
            time.sleep(4.2 - elapsed)
        _last_call_time = time.time()

    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', **headers})
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < max_retries:
                # Tự động chờ khi chạm giới hạn request rate limit của free tier
                retry_header = exc.headers.get('Retry-After') if exc.headers else None
                try:
                    wait_sec = float(retry_header) if retry_header else (15 + attempt * 5)
                except (ValueError, TypeError):
                    wait_sec = 15 + attempt * 5
                time.sleep(wait_sec)
                _last_call_time = time.time()
                continue
            # Do not print response bodies: they may contain account or request data.
            raise RuntimeError(f'Provider trả HTTP {exc.code}; kiểm tra model, key và quota.') from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f'Không kết nối được provider: {exc.reason}') from exc


class Provider:
    """complete(messages, schemas) -> {message, calls, finish, usage}.

    messages: system/user/assistant/tool theo format Chat Completions. message trả về
    cần được append nguyên vẹn; tool result có role, tool_call_id, content (JSON string).
    """
    def __init__(self, name, model):
        if name not in CONFIG:
            raise ValueError(f'Provider không hợp lệ: {name}')
        if not model:
            raise ValueError('Cần đặt MODEL là model có hỗ trợ tool calling.')
        self.name, self.model = name, model
        self.session_id = str(uuid.uuid4())
        key_name, self.url = CONFIG[name]

        # Cho phép ghi đè URL qua OPENAI_BASE_URL hoặc API_ENDPOINT
        if name == 'openai' and os.getenv('OPENAI_BASE_URL'):
            base = os.getenv('OPENAI_BASE_URL').rstrip('/')
            self.url = base if base.endswith('/chat/completions') else f'{base}/chat/completions'
        elif name == 'opencode':
            endpoint = os.getenv('API_ENDPOINT') or os.getenv('OPENCODE_API_ENDPOINT')
            if endpoint:
                base = endpoint.rstrip('/')
                self.url = base if base.endswith('/chat/completions') else f'{base}/chat/completions'

        self.key = os.getenv(key_name)
        if name == 'opencode' and not self.key:
            self.key = os.getenv('API_KEY')
        elif name == 'openai' and not self.key:
            self.key = os.getenv('API_KEY')

        if not self.key:
            raise ValueError(f'Thiếu {key_name}; xem README.md.')

    def complete(self, messages, schemas):
        if self.name == 'anthropic':
            return self._anthropic(messages, schemas)
        payload = {'model': self.model, 'messages': messages}
        if schemas:
            payload['tools'] = schemas
        headers = {
            'Authorization': f'Bearer {self.key}',
            'User-Agent': 'StatusAgentLab/1.0',
            'x-opencode-session': self.session_id,
        }
        data = post_json(self.url, headers, payload)
        choice = data['choices'][0]
        message = choice['message']
        calls = [{'id': c['id'], 'name': c['function']['name'], 'arguments': c['function']['arguments']} for c in message.get('tool_calls', [])]
        return {'message': message, 'calls': calls, 'finish': choice.get('finish_reason'), 'usage': data.get('usage', {})}

    def _anthropic(self, messages, schemas):
        system = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
        native = []
        for m in messages:
            if m['role'] == 'system':
                continue
            if m['role'] == 'assistant':
                blocks = []
                if m.get('content'):
                    blocks.append({'type': 'text', 'text': m['content']})
                for call in m.get('tool_calls', []):
                    blocks.append({'type': 'tool_use', 'id': call['id'], 'name': call['function']['name'], 'input': json.loads(call['function']['arguments'])})
                native.append({'role': 'assistant', 'content': blocks})
            elif m['role'] == 'tool':
                block = {'type': 'tool_result', 'tool_use_id': m['tool_call_id'], 'content': m['content']}
                if native and native[-1]['role'] == 'user' and isinstance(native[-1]['content'], list):
                    native[-1]['content'].append(block)
                else:
                    native.append({'role': 'user', 'content': [block]})
            else:
                native.append({'role': 'user', 'content': m['content']})
        tools = [{'name': x['function']['name'], 'description': x['function']['description'], 'input_schema': x['function']['parameters']} for x in schemas]
        payload = {'model': self.model, 'max_tokens': 1024, 'system': system, 'messages': native}
        if tools:
            payload['tools'] = tools
        data = post_json(self.url, {'x-api-key': self.key, 'anthropic-version': '2023-06-01'}, payload)
        blocks = data['content']
        calls = [{'id': b['id'], 'name': b['name'], 'arguments': json.dumps(b['input'], ensure_ascii=False)} for b in blocks if b['type'] == 'tool_use']
        text = '\n'.join(b['text'] for b in blocks if b['type'] == 'text')
        message = {'role': 'assistant', 'content': text or None}
        if calls:
            message['tool_calls'] = [{'id': c['id'], 'type': 'function', 'function': {'name': c['name'], 'arguments': c['arguments']}} for c in calls]
        reason = {'end_turn': 'stop', 'tool_use': 'tool_calls', 'max_tokens': 'length'}.get(data.get('stop_reason'), data.get('stop_reason'))
        return {'message': message, 'calls': calls, 'finish': reason, 'usage': data.get('usage', {})}
