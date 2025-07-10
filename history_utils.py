import os
import time
import traceback
import asyncio
import re

# 路径常量
HISTORY_FILE = os.path.expanduser("~/.zsh_history")
USER_HISTORY_FILE = os.path.expanduser("~/.user_zsh_history")
HISTORY_ALL_FILE = os.path.expanduser("~/.zsh_history_all")

# 全局缓存变量
history_cache = {"HISTORY_FILE": [], "USER_HISTORY_FILE": [], "HISTORY_ALL_FILE": []}
last_modified_time = {"HISTORY_FILE": 0.0, "USER_HISTORY_FILE": 0.0, "HISTORY_ALL_FILE": 0.0}
last_cache_load_time = {"HISTORY_FILE": 0.0, "USER_HISTORY_FILE": 0.0, "HISTORY_ALL_FILE": 0.0}
write_recent_calls = {}
lock = asyncio.Lock()

# 新增：命令内存暂存
pending_commands = {}  # session -> (cmd, ts)

def load_file_to_cache(file_path, cache_key, reload_interval=120):
    """
    加载文件内容到缓存中，如果文件未修改或距离上次加载未超过 reload_interval 秒，则直接使用缓存。
    :param file_path: 文件路径
    :param cache_key: 缓存键
    :param reload_interval: 最小重新加载间隔时间（秒），默认为 120 秒
    :return: 文件内容（列表形式，每行作为一个元素）
    """
    global history_cache, last_modified_time, last_cache_load_time

    if not os.path.exists(file_path):
        return []

    current_time = time.time()
    if (current_time - last_cache_load_time[cache_key]) < reload_interval:
        return history_cache[cache_key]

    modified_time = os.path.getmtime(file_path)
    if modified_time > last_modified_time[cache_key]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
                history_cache[cache_key] = file.readlines()
            last_modified_time[cache_key] = modified_time
            last_cache_load_time[cache_key] = current_time
        except Exception as e:
            print(traceback.format_exc())
            print(f"Error loading file {file_path}: {e}")
            return []
    else:
        last_cache_load_time[cache_key] = current_time

    return history_cache[cache_key]

async def write_command_suggestions(session, partial_command):
    """
    只暂存到内存，不立即写入。
    """
    if len(partial_command) < 8:
        return ""
    cmd = partial_command.strip()
    if re.match(r"^\d+\s+", cmd):
        return ""
    if re.match(r"^cd\s+cd\s+", cmd):
        return ""
    if len(cmd.split()) < 2:
        return ""
    if "print" in cmd:
        return ""
    global pending_commands
    pending_commands[session] = (cmd, time.time())

async def flush_pending_commands():
    """
    定时批量写入历史文件，写入前做前缀去重。
    """
    global pending_commands, lock
    now = time.time()
    to_write = []
    # 取出停留超过2秒的命令
    for session, (cmd, ts) in list(pending_commands.items()):
        if now - ts > 2:
            to_write.append(cmd)
            del pending_commands[session]
    if not to_write:
        return
    async with lock:
        history_cmds = []
        if os.path.exists(HISTORY_ALL_FILE):
            with open(HISTORY_ALL_FILE, "r", encoding="utf-8", errors="ignore") as file:
                history_cmds = [line.strip() for line in file.readlines()[-100:] if line.strip()]
        # 合并、去重
        all_cmds = history_cmds + to_write
        filtered_cmds = filter_prefix_cmds(all_cmds)
        # 只写入新命令且是被保留的
        for cmd in to_write:
            if cmd in filtered_cmds and cmd not in history_cmds:
                with open(HISTORY_ALL_FILE, "a", encoding="utf-8", errors="ignore") as file:
                    file.write(cmd + "\n")

async def periodic_flush():
    while True:
        await flush_pending_commands()
        await asyncio.sleep(1)

def filter_prefix_cmds(cmds, min_len=8):
    # 先按长度降序排列
    cmds = sorted([c for c in cmds if len(c) >= min_len], key=lambda x: -len(x))
    result = []
    for i, cmd in enumerate(cmds):
        is_prefix = False
        for j, other in enumerate(cmds):
            if i != j and other.startswith(cmd):
                is_prefix = True
                break
        if not is_prefix:
            result.append(cmd)
    return result 