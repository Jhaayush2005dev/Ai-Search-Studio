import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from core.config import SESSIONS_DIR

class SessionManager:
    """Manages chat session lifecycle, disk persistence, and conversation retrieval."""

    def __init__(self, sessions_dir: Path = SESSIONS_DIR):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_path(self, session_id: str) -> Path:
        # Sanitize session_id to avoid path traversal
        clean_id = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
        return self.sessions_dir / f"{clean_id}.json"

    def create_session(self, title: str = "New Conversation") -> Dict[str, Any]:
        """Creates and persists a new empty chat session."""
        now_iso = datetime.now().isoformat()
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        session_data = {
            "id": session_id,
            "title": title,
            "created_at": now_iso,
            "updated_at": now_iso,
            "messages": []
        }
        self._write_session(session_id, session_data)
        return session_data

    def _write_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        path = self._get_session_path(session_id)
        try:
            temp_path = path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if temp_path.exists():
                temp_path.replace(path)
            return True
        except Exception as e:
            print(f"Error saving session {session_id}: {e}")
            return False

    def save_session(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        title: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Updates and saves conversation messages to a session."""
        if not session_id:
            return None

        session_data = self.get_session(session_id)
        now_iso = datetime.now().isoformat()

        if not session_data:
            session_data = {
                "id": session_id,
                "title": title or "New Conversation",
                "created_at": now_iso,
                "updated_at": now_iso,
                "messages": []
            }

        session_data["messages"] = messages
        session_data["updated_at"] = now_iso

        # Auto-derive title from first user query if title is default or not set
        if title:
            session_data["title"] = title
        elif session_data.get("title") in ("New Conversation", "Untitled Session", "", None):
            for msg in messages:
                if msg.get("role") == "user" and msg.get("content"):
                    raw_content = msg["content"].strip().replace("\n", " ")
                    derived = raw_content[:45] + ("..." if len(raw_content) > 45 else "")
                    session_data["title"] = derived
                    break

        success = self._write_session(session_id, session_data)
        return session_data if success else None

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Loads a session by ID."""
        path = self._get_session_path(session_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading session {session_id}: {e}")
            return None

    def list_sessions(self, search_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all stored chat sessions, sorted by last updated descending."""
        sessions = []
        if not self.sessions_dir.exists():
            return []

        for p in self.sessions_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "id" in data:
                        sessions.append(data)
            except Exception:
                continue

        # Sort newest updated first
        sessions.sort(key=lambda s: s.get("updated_at", s.get("created_at", "")), reverse=True)

        if not search_query or not search_query.strip():
            return sessions

        q = search_query.strip().lower()
        filtered = []
        for s in sessions:
            title = str(s.get("title", "")).lower()
            if q in title:
                filtered.append(s)
                continue
            # Search in message contents
            found_in_msgs = False
            for m in s.get("messages", []):
                if q in str(m.get("content", "")).lower():
                    found_in_msgs = True
                    break
            if found_in_msgs:
                filtered.append(s)

        return filtered

    def rename_session(self, session_id: str, new_title: str) -> bool:
        """Renames a session."""
        session_data = self.get_session(session_id)
        if not session_data:
            return False
        session_data["title"] = new_title.strip() or "Untitled Session"
        session_data["updated_at"] = datetime.now().isoformat()
        return self._write_session(session_id, session_data)

    def delete_session(self, session_id: str) -> bool:
        """Deletes a session file from disk."""
        path = self._get_session_path(session_id)
        try:
            if path.exists():
                path.unlink()
                return True
        except Exception as e:
            print(f"Error deleting session {session_id}: {e}")
        return False

    def clear_all_sessions(self) -> bool:
        """Deletes all session files."""
        try:
            for p in self.sessions_dir.glob("*.json"):
                try:
                    p.unlink()
                except Exception:
                    pass
            return True
        except Exception as e:
            print(f"Error clearing all sessions: {e}")
            return False
