"""
Creates all tables in the database. Run once after first deploy
(or whenever models change and you don't want to deal with migrations yet):

    python scripts/init_db.py

For a project this size, plain create_all() is fine. If this grows complex
enough to need real migrations later, switch to Alembic.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Base, engine
from models import models  # noqa: F401 (import registers the models with Base)

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print("✅ Tables created (or already existed).")
