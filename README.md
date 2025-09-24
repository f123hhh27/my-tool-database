# my-tool-database
This repository contains code that I used across different programs, platforms, and scenarios.

## Personal Tools DB (SQLite + CSV)

- Track small code tools/snippets with metadata.
- DB: `data/tools.db` (SQLite, not versioned)
- CSV: `data/tools.csv` (versioned)
- Snippets: `snippets/`

### Quick start
```bash
python scripts/tool_db.py init
python scripts/tool_db.py add --name xxx --language python --platform colab --purpose "..." --tags "a,b" --snippet-path snippets/xxx.ipynb
python scripts/tool_db.py list
python scripts/tool_db.py export-csv data/tools.csv

### new tools
1. - colab_auto_disconnect | lang=Python 3.12.11 | plat=google_colab | tags=auto_disconnect,colab
  purpose: 自動存檔並斷開 Colab 連線
  link:    No
  snippet: snippets/colab_auto_disconnect.ipynb
  created: 2025-09-25 03:22:24 CST (2025-09-24T19:22:24Z) | updated: 2025-09-25 03:27:33 CST (2025-09-24T19:27:33Z)