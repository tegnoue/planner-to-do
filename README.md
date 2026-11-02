# Task Planner

Aplicação pessoal de tarefas com FastAPI, PostgreSQL, Poetry e frontend HTML/Tailwind/JavaScript.

## Executar

1. `cp .env.example .env`
2. `docker compose up -d db`
3. `poetry install`
4. `poetry run uvicorn app.main:app --reload`
5. Acesse `http://localhost:8000` (API docs em `/docs`).

As tabelas são criadas no primeiro startup para facilitar o início local. Antes de produção, substitua `create_all` por migrações Alembic. A API não inclui autenticação nesta primeira versão; todos os dados compartilham o mesmo espaço pessoal.
