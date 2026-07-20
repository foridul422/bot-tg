AUTHOR = "https://t.me/Foridul_002"
WIDTH = 30


def format_result(title: str, body: str) -> str:
    line = "━" * WIDTH
    return (
        "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃       🔓 DECRYPTOR BOT       ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        "✅ DECRYPT COMPLETED\n"
        "📊 Status    : SUCCESS\n"
        f"📦 App       ➜ {title}\n\n"
        f"{line}\n"
        "📄 CONFIG JSON\n"
        f"{line}\n\n"
        f"{body}\n\n"
        f"{line}\n"
        f"BY : {AUTHOR}\n"
        f"{line}"
    )
