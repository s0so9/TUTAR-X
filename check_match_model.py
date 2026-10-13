"""Match modelindeki alanları kontrol et."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Match

db_path = os.path.join(os.path.dirname(__file__), 'backend', 'football_intelligence.db')
engine = create_engine(f'sqlite:///{db_path}')
Session = sessionmaker(bind=engine)
session = Session()

match = session.query(Match).first()

print("Match model attributes:")
for attr in dir(match):
    if not attr.startswith('_'):
        try:
            value = getattr(match, attr)
            print(f"  {attr}: {type(value).__name__} = {value}")
        except:
            print(f"  {attr}: <property/method>")

session.close()