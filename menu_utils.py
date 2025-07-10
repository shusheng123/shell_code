import unicodedata
import asyncio

# 计算字符串在终端的显示宽度（中英文混合）
def visual_width(s):
    width = 0
    for c in s:
        if unicodedata.east_asian_width(c) in 'WF':
            width += 2
        else:
            width += 1
    return width

def safe_str(s):
    return s.replace("'", "").replace('"', '').replace("\\", '').replace('\n', ' ').replace('\r', '')

async def wait_for_user_input(session, suggestions, timeout=20):
    start_time = asyncio.get_event_loop().time()
    while True:
        if asyncio.get_event_loop().time() - start_time > timeout:
            await session.async_send_text('\n')
            return
        screen_contents = await session.async_get_screen_contents()
        num_lines = screen_contents.number_of_lines
        screen_text = []
        for i in range(num_lines):
            line_content = screen_contents.line(i)
            if line_content.string:
                screen_text.append(line_content.string)
        num_ber = find_full_number_from_end(screen_text[-1])
        if num_ber:
            selected_index = int(num_ber) - 1
            if 0 <= selected_index < len(suggestions):
                selected_command = suggestions[selected_index]
                await session.async_send_text("\b" * 100)
                await send_suggestion_to_shell(session, selected_command)
            break
        await asyncio.sleep(0.5)

def find_full_number_from_end(s):
    number = ""
    for char in reversed(s):
        if char.isdigit():
            number = char + number
        else:
            break
    return number

async def show_command_selection_menu(session, suggestions):
    try:
        if not suggestions:
            return
        suggestions = suggestions[:10]
        MENU_WIDTH = 40
        CMD_MAX_LEN = 30
        menu_lines = []
        menu_lines.append("┌" + "─" * (MENU_WIDTH - 2) + "┐")
        menu_lines.append("│{:^{width}}│".format("请选择", width=MENU_WIDTH - 5))
        menu_lines.append("├" + "─" * (MENU_WIDTH - 2) + "┤")
        for i, cmd in enumerate(suggestions):
            display_cmd = safe_str(cmd)
            if visual_width(display_cmd) > CMD_MAX_LEN:
                cut = 0
                w = 0
                for idx, c in enumerate(display_cmd):
                    w += 2 if unicodedata.east_asian_width(c) in 'WF' else 1
                    if w > CMD_MAX_LEN:
                        break
                    cut = idx + 1
                display_cmd = display_cmd[:cut] + '...'
            num = f"{i+1:2d}"
            line = f"│ {num}. {display_cmd}"
            pad = MENU_WIDTH - 1 - visual_width(line)
            line = line + " " * pad + "│"
            menu_lines.append(line)
        menu_lines.append("└" + "─" * (MENU_WIDTH - 2) + "┘")
        menu_lines.append("请输入编号：".ljust(MENU_WIDTH - 1))
        menu_lines.append(" " * (MENU_WIDTH - 1))
        menu_prompt = "\n".join(menu_lines)
        menu_prompt = menu_prompt.replace("'", "")
        await session.async_send_text("\b" * 100)
        await session.async_send_text(f"clear; printf '{menu_prompt}\\n'\n")
        await wait_for_user_input(session, suggestions)
    except Exception as e:
        print(f"Error showing command selection menu: {e}")

# send_suggestion_to_shell 依赖于主流程，建议保留在主入口或单独模块 

async def send_suggestion_to_shell(session, suggestion):
    try:
        if not suggestion:
            return
        screen_contents = await session.async_get_screen_contents()
        num_lines = screen_contents.number_of_lines
        screen_text = []
        for i in range(num_lines):
            line_content = screen_contents.line(i)
            if line_content.string:
                screen_text.append(line_content.string)
        input_length = len(screen_text[-1])
        if input_length > 0:
            await session.async_send_text("\b" * input_length)
        await asyncio.sleep(0.3)
        await session.async_send_text(suggestion)
    except Exception as e:
        print(f"Error sending suggestion to shell: {e}")