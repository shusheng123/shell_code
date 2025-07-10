import re
import time
import traceback
import asyncio
import requests
import yaml
import os
from history_utils import load_file_to_cache, HISTORY_FILE, USER_HISTORY_FILE, HISTORY_ALL_FILE, lock

recent_calls = {}
ai_recent_calls = {}

# 读取配置
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

_config = load_config()
ARK_API_KEY = _config.get("ark_api_key", "")
ARK_API_URL = _config.get("ark_api_url", "")


async def get_command_suggestions_v2(session, partial_command):
    global recent_calls
    current_time = time.time()
    async with lock:
        if session in recent_calls:
            last_call_time = recent_calls[session]
            if current_time - last_call_time < 2:
                return "skipping"
        recent_calls[session] = current_time
    if "." in partial_command:
        keywords = partial_command.lower().split(".")
    else:
        keywords = partial_command.lower().split()
    suggestions = []
    user_suggestions = []
    all_suggestions = []
    def remove_special_characters(input_string):
        cleaned_string = re.sub(r'[^\w\s/]', '', input_string)
        cleaned_string = re.sub(r'\s+', ' ', cleaned_string)
        return cleaned_string.strip()
    try:
        history_lines = load_file_to_cache(HISTORY_FILE, "HISTORY_FILE")
        user_history_lines = load_file_to_cache(USER_HISTORY_FILE, "USER_HISTORY_FILE")
        all_history_lines = load_file_to_cache(HISTORY_ALL_FILE, "HISTORY_ALL_FILE")
        for line in user_history_lines:
            if "print" in line:
                continue
            if all(keyword in line.lower() for keyword in keywords):
                line = line.strip()
                user_suggestions.append(remove_special_characters(line))
        for line in all_history_lines:
            if "print" in line:
                continue
            if all(keyword in line.lower() for keyword in keywords):
                all_suggestions.append(remove_special_characters(line))
        for line in history_lines:
            if "print" in line:
                continue
            match = re.search(r";(.*)", line)
            if match:
                command = match.group(1).strip()
                if all(keyword in command.lower() for keyword in keywords):
                    suggestions.append(remove_special_characters(command))
    except Exception as e:
        print(traceback.format_exc())
        print(f"Error processing history: {e}")
        return ""
    def is_valid_cmd(cmd):
        if re.match(r"^\d+\s+", cmd):
            return False
        if re.match(r"^cd\s+cd\s+", cmd):
            return False
        # if len(cmd.split()) < 2:
        #     return False
        if "print" in cmd:
            return False
        return True
    result = []
    for cmd in user_suggestions + all_suggestions + suggestions:
        if is_valid_cmd(cmd) and cmd not in result:
            result.append(cmd)
    return result[:10]

async def get_command_suggestions_from_ai(session, partial_command):
    if len(partial_command) < 5:
        return ""
    global ai_recent_calls
    current_time = time.time()
    async with lock:
        if session in ai_recent_calls:
            last_call_time = ai_recent_calls[session]
            if current_time - last_call_time < 2:
                return "skipping"
        ai_recent_calls[session] = current_time
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ARK_API_KEY}"
    }
    sys_prompt = """
    你是一位Linux大师，精通各种Linux命令。你的任务是根据用户提供的操作描述生成相应的Linux命令。
    请仔细阅读以下用户需求描述：
    <description>
    {{DESCRIPTION}}
    </description>
    在生成命令时，请遵循以下规则：
    - 以JSON格式输出结果。
    - 确保生成的命令准确对应描述中的操作。
    - 如果描述中有多种可能的操作，选择最常见或最合理的一种。
    - 直接返回 linux 命令
    - 返回的 content 只有 json 只有一个键值对，键名为 command，值为命令。
      示例JSON输出如下：
        {
        "command": "ping www.baidu.com",
        }
    """
    data = {
        "model": "doubao-1-5-lite-32k-250115",
        "messages": [
            {"role": "user", "content": sys_prompt + '\n' +  partial_command}
        ]
    }
    response = requests.post(ARK_API_URL, headers=headers, json=data)
    if response.status_code == 200:
        response_data = response.json()
        content = response_data["choices"][0]["message"]["content"]
        pattern = r'"command":\s*"(.*?)"'
        match = re.search(pattern, content)
        if match:
            command_value = match.group(1)
            return command_value
        else:
            return ""
    else:
        return "" 