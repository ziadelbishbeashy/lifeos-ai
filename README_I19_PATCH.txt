LifeOS AI — I19 Constrained Agent Runtime patch

Copy the included backend/ and frontend/ folders into the existing LifeOS project and replace matching files.

IMPORTANT: I19 adds a new Alembic migration/table for auditable agent runs.
After copying:

  cd backend
  py -3.11 -m alembic -c migrations/alembic.ini upgrade head
  py -3.11 -m alembic -c migrations/alembic.ini heads
  py -3.11 -m pytest -q

Then:

  cd ..\frontend
  npm run build
  npm run css:check

Expected migration head after upgrade: 20260831_0001

I18 remains working but intentionally NOT marked product-final; further UI/UX polish can continue independently.
