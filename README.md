# my-tool-database

A personal database to track small code tools/snippets across different programs, platforms, and scenarios.

## Project structure

- **data/**
  - `tools.db` — SQLite database (ignored in git, local only)
  - `tools.csv` — CSV export of all tools (tracked in git)
- **scripts/**
  - `tool_db.py` — CLI tool to manage the database
- **snippets/** — Code snippets linked to entries
- **README.md** — Project documentation

## Features

- Track tools/snippets with metadata (language, platform, tags, purpose, etc.)
- Store data in SQLite (`tools.db`), but version-control via CSV (`tools.csv`)
- Import/export between DB and CSV
- Search and list tools via CLI

## Quick start

```bash
# Initialize database
python scripts/tool_db.py init

# Add a new tool
python scripts/tool_db.py add --name colab_auto_disconnect \
  --language python --version 3.12.11 --platform colab \
  --purpose "自動存檔並斷開 Colab 連線" \
  --tags "colab, auto_disconnect" \
  --snippet-path snippets/colab_auto_disconnect.ipynb

# List all tools
python scripts/tool_db.py list

# Export CSV (commit this file to git)
python scripts/tool_db.py export-csv data/tools.csv
```
## 備註
持續更新中...關於README的內容並不一定百分百正確，有錯誤的部分還請指證！