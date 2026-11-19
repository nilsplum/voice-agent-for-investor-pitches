"""The HTTP routes, one module per audience: public, auth (the one login), founder (`/api/my`) and
team (`/api/team`). Every route is `async def` and reaches the database only through `db.run_db`."""
