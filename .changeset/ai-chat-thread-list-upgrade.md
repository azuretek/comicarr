---
"comicarr": patch
---

Fix the AI chat thread list returning HTTP 500 on ordinary page loads after upgrading past pre-library-chat installs. Schema validation now requires the complete schema for the *stamped* Alembic revision rather than the migration head, so `0002` databases missing `ai_chat_*` tables can reach `0003_library_chat` and the recent-chats endpoint can return an empty or populated list.
