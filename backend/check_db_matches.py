"""Check matches in database."""
from app.database.session import SessionLocal
from app.database.models import Match
from datetime import datetime, timezone

session = SessionLocal()
matches = session.query(Match).all()
print(f'Total matches in DB: {len(matches)}')

for m in matches[:10]:
    status_val = m.status.value if hasattr(m.status, 'value') else str(m.status)
    print(f'{m.id[:8]}... {m.scheduled_at} - {status_val}')

session.close()
