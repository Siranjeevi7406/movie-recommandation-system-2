# CinePick — Complete Movie Recommendation Website

CinePick is a responsive full-stack movie discovery and recommendation platform built with React, Tailwind CSS, Django REST Framework, SQLite, JWT, TMDB, and OMDb.

## Features

- Search movies and filter by genre, year, language, and rating
- Movie details, cast, director, runtime, backdrop, and related titles
- Official YouTube trailer embeds
- Real IMDb ratings through OMDb, with a safe TMDB-rating fallback
- OTT availability for a configurable region (India by default)
- User registration and JWT login
- Persistent personal watchlist and 1–10 user ratings
- Content-based recommendations calculated from saved and highly rated genres
- Responsive dark UI, loading states, error states, pagination, tests, and Docker deployment

## Required API accounts

1. Create a free TMDB account and copy its **API Read Access Token**.
2. Request an OMDb API key. This is optional; without it CinePick displays the TMDB score.

## Local setup on Windows

### Backend

```powershell
cd cinepick\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `backend/.env`:

```env
DJANGO_SECRET_KEY=replace-this-with-a-long-random-value
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
FRONTEND_URL=http://localhost:5173
TMDB_API_TOKEN=your-tmdb-read-access-token
OMDB_API_KEY=your-omdb-key
OTT_REGION=IN
DATABASE_NAME=db.sqlite3
```

Then run:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Frontend

Open a second terminal:

```powershell
cd cinepick\frontend
copy .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173`.

## Tests and production build

```powershell
cd backend
python manage.py test

cd ..\frontend
npm run build
```

## Docker

After creating `backend/.env`:

```bash
docker compose up --build
```

Open `http://localhost:8080`.

## API routes

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health/` | Health check |
| GET | `/api/genres/` | Movie genres |
| GET | `/api/movies/` | Search and discover |
| GET | `/api/movies/{id}/` | Full details, trailer, IMDb and OTT |
| POST | `/api/auth/register/` | Create account |
| POST | `/api/auth/login/` | Obtain JWT tokens |
| POST | `/api/auth/refresh/` | Refresh access token |
| GET/POST | `/api/watchlist/` | List or save movies |
| DELETE | `/api/watchlist/{tmdb_id}/` | Remove saved movie |
| GET/PUT/DELETE | `/api/ratings/{tmdb_id}/` | Manage personal rating |
| GET | `/api/recommendations/` | Personalized recommendations |

## Data notes

- OTT results are provider availability data for the configured country. The provider link is supplied by TMDB and availability can change.
- IMDb ratings come from OMDb, which is not affiliated with IMDb.
- API secrets remain in Django and are never shipped in the React bundle.
