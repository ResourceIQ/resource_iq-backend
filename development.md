# FastAPI Backend - Development

## Local Development Setup

### Setting up the environment

1. **Create and activate a virtual environment**

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

3. **Install dependencies**

```bash
pip install -e .
```

4. **Set up your `.env` file**

Create a `.env` file in the root directory with your configuration:

```env
DOMAIN=localhost
ENVIRONMENT=local
BACKEND_CORS_ORIGINS=["http://localhost","http://localhost:8000"]
SECRET_KEY=your-secret-key-here
PROJECT_NAME="FastAPI Backend"

# Database
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_DB=app
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-postgres-password

# First superuser
FIRST_SUPERUSER=admin@example.com
FIRST_SUPERUSER_PASSWORD=your-admin-password
```

5. **Set up PostgreSQL**

Make sure PostgreSQL is installed and running. Create the database:

```sql
CREATE DATABASE app;
```

6. **Run migrations**

```bash
alembic upgrade head
```

7. **Create initial data**

```bash
python -m app.initial_data
```

### Running the Development Server

Start the FastAPI development server:

```bash
fastapi dev app/main.py
```


## Database Migrations with Alembic

This project uses [Alembic](https://alembic.sqlalchemy.org/) for database migrations.

### Creating a new migration

After changing your models in `app/models.py`, create a new migration:

```bash
alembic revision --autogenerate -m "Description of changes"
```

### Applying migrations

Apply all pending migrations:

```bash
alembic upgrade head
```

### Rolling back migrations

Roll back one migration:

```bash
alembic downgrade -1
```

### Viewing migration history

```bash
alembic history
```

## Testing

Run tests using pytest:

```bash
pytest
```

Run tests with coverage:

```bash
pytest --cov=app
```

## Code Formatting and Linting

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

### Format code

```bash
bash scripts/format.sh
```

### Lint code

```bash
bash scripts/lint.sh
```

## Project Structure

```
resource_iq-backend/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── models.py            # SQLModel database models
│   ├── crud.py              # CRUD operations
│   ├── initial_data.py      # Script to create initial data
│   ├── api/
│   │   ├── main.py          # API router
│   │   ├── deps.py          # Dependencies (DB session, current user)
│   │   └── routes/          # API route modules
│   ├── core/
│   │   ├── config.py        # Settings and configuration
│   │   ├── db.py            # Database connection
│   │   └── security.py      # Security utilities (password hashing, JWT)
│   └── alembic/             # Database migrations
├── tests/                   # Test files
├── scripts/                 # Utility scripts
├── pyproject.toml           # Project dependencies and configuration
└── alembic.ini              # Alembic configuration
```

## API Endpoints

Once running, you can explore all available endpoints in the interactive documentation at:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>

Main endpoint groups:

- `/api/v1/login` - Authentication (login, password recovery)
- `/api/v1/users` - User management
- `/api/v1/items` - Item CRUD operations

## Environment Variables

Key environment variables in the `.env` file:

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Secret key for JWT tokens | Generate with `secrets.token_urlsafe(32)` |
| `POSTGRES_SERVER` | PostgreSQL host | `localhost` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `POSTGRES_DB` | Database name | `app` |
| `POSTGRES_USER` | Database user | `postgres` |
| `POSTGRES_PASSWORD` | Database password | Your secure password |
| `FIRST_SUPERUSER` | Initial admin email | `admin@example.com` |
| `FIRST_SUPERUSER_PASSWORD` | Initial admin password | Your secure password |

## Tips for Learning

1. **Start with the API docs**: Visit `http://localhost:8000/docs` to see all available endpoints
2. **Explore the code**: 
   - Look at `app/main.py` to understand how FastAPI apps are structured
   - Check `app/models.py` to see how database models are defined
   - Review `app/api/routes/` to understand API endpoint implementation
3. **Use the interactive docs**: Test API endpoints directly from the Swagger UI
4. **Read the tests**: The `tests/` directory has examples of how to test your API
5. **Modify and experiment**: Try adding new fields to models or creating new endpoints

Adminer: <http://localhost.tiangolo.com:8080>

Traefik UI: <http://localhost.tiangolo.com:8090>

MailCatcher: <http://localhost.tiangolo.com:1080>
