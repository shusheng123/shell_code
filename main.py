import iterm2
import time
import traceback
import asyncio
import history_utils
from history_utils import write_command_suggestions
from suggestion_utils import get_command_suggestions_v2, get_command_suggestions_from_ai
from menu_utils import show_command_selection_menu, send_suggestion_to_shell
import re
import shlex

COMMON_COMMANDS = [
    "ls", "cd", "cat", "tail", "head", "grep", "awk", "sed", "find", "echo", "rm", "cp", "mv",
    "python", "pip", "git", "docker", "ssh", "scp", "ps", "top", "htop", "kill", "chmod", "chown",
    "tar", "zip", "unzip", "curl", "wget", "make", "gcc", "g++", "vim", "nano", "less", "more",
    "service", "systemctl", "journalctl", "ifconfig", "ip", "netstat", "ss", "ping", "traceroute"
]

def is_normal_command(cmd):
    cmd = cmd.strip()
    # 不能是空、纯数字、纯符号
    if not cmd or re.fullmatch(r"[\\d\\W]+", cmd):
        return False
    # 不能有中文
    if re.search(r"[\u4e00-\u9fff]", cmd):
        return False
    # 必须有空格（有参数），且长度大于5
    if " " not in cmd or len(cmd) < 5:
        return False
    # 必须以常见命令开头
    first_word = cmd.split()[0]
    if first_word not in COMMON_COMMANDS:
        return False
    # shlex 拆分能通过
    try:
        shlex.split(cmd)
    except Exception:
        return False
    return True

session_locks, session_task_status = {}, {}


async def main(connection):
    component = iterm2.StatusBarComponent(
        short_description="Command Predictor",
        detailed_description="Predicts the next command based on history",
        knobs=[],
        exemplar="Suggestions: ls, cd",
        update_cadence=1,
        identifier="com.example.command-predictor",
    )
    @iterm2.StatusBarRPC
    async def command_predictor_coroutine(knobs):
        app = await iterm2.async_get_app(connection)
        window = app.current_window if app else None
        if window is None:
            return "No window"
        tab = window.current_tab
        if tab is None:
            return "No tab"
        session = tab.current_session
        if session is None:
            return "No session"
        global session_locks, session_task_status
        if session not in session_locks:
            session_locks[session] = asyncio.Lock()
        async with session_locks[session]:
            if session in session_task_status and session_task_status[session]:
                return
            session_task_status[session] = True
            try:
                screen_contents = await session.async_get_screen_contents()
                num_lines = screen_contents.number_of_lines
                screen_text = []
                for i in range(num_lines):
                    line_content = screen_contents.line(i)
                    if line_content.string:
                        screen_text.append(line_content.string)
                screen_text = screen_text[-1]
                if "➜  ~" in screen_text:
                    word = screen_text.split("➜  ~")[-1].strip()
                elif "✗" in screen_text:
                    word = screen_text.split("✗")[-1].strip()
                elif "➜" in screen_text:
                    word = ' '.join(screen_text.split("➜")[-1].strip().split(" ")[1:])
                elif "$" in screen_text:
                    word = screen_text.split("$")[-1].strip()
                elif ")" in screen_text:
                    word = screen_text.split(")")[-1].strip()
                else:
                    return ""
                if word and word.endswith("ges"):
                    try:
                        send_msg = word.split("ges")[0].strip()
                        suggestions = await get_command_suggestions_v2(session, send_msg)
                        if suggestions == "skipping" or not suggestions:
                            return
                        await show_command_selection_menu(session, suggestions)
                    except Exception as e:
                        print(traceback.format_exc())
                    return
                elif word and word.endswith("gesi"):
                    try:
                        send_msg = word.split("gesi")[0].strip()
                        suggestions = await get_command_suggestions_from_ai(session, send_msg)
                        if suggestions == "skipping" or not suggestions:
                            return
                        await send_suggestion_to_shell(session, suggestions)
                    except Exception as e:
                        print(traceback.format_exc())
                    return
                else:
                    if not is_normal_command(word):
                        return ""
                    await write_command_suggestions(session, word)
            except Exception as e:
                return f"Error: {e}"
            finally:
                time.sleep(0.5)
                session_task_status[session] = False
    asyncio.create_task(history_utils.periodic_flush())
    await component.async_register(connection, command_predictor_coroutine)

# 运行主程序
if __name__ == "__main__":
    iterm2.run_forever(main) 