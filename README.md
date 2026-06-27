# NurseAI v1 - OET AI Coach for Indian Nurses

A comprehensive web application designed to help Indian nurses prepare for the Occupational English Test (OET) with AI-powered coaching, real-time feedback, and practice modules.

## Features

- **AI-Powered Scoring**: Uses OpenRouter's Gemini 2.0 Flash for detailed feedback on speaking, writing, listening, and reading
- **Speaking Practice**: Web Audio API-based voice recording with transcription and AI feedback
- **Writing Practice**: Submit written responses with AI evaluation
- **Mock Tests**: Full practice tests simulating real OET exam conditions
- **Progress Tracking**: Dashboard with detailed statistics and improvement tracking
- **Secure Authentication**: JWT-based auth with NextAuth.js and bcrypt hashing
- **Responsive Design**: Mobile-friendly UI with Tailwind CSS

## Tech Stack

- **Frontend**: Next.js 14 (App Router, TypeScript, Tailwind CSS)
- **Backend**: FastAPI (Python with async support)
- **Database**: SQLite with SQLAlchemy ORM
- **AI**: OpenRouter API (Gemini 2.0 Flash model)
- **Authentication**: NextAuth.js with JWT
- **Containerization**: Docker Compose for local development

## Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for local frontend development)
- Python 3.10+ (for local backend development)
- OpenRouter API key (get from https://openrouter.ai)

## Quick Start

### Using Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone <repo-url>
cd nurseai

# 2. Create .env file with your credentials
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY

# 3. Build and start services
docker-compose up --build

# 4. Access the application
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Local Development Setup

#### Frontend Setup

```bash
cd frontend
npm install
npm run dev
# Access at http://localhost:3000
```

#### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# Access at http://localhost:8000
```

## Environment Variables

Create a `.env` file in the root directory:

```
OPENROUTER_API_KEY=your_openrouter_api_key_here
SECRET_KEY=your_secret_key_for_jwt
NEXTAUTH_SECRET=your_nextauth_secret
NEXTAUTH_URL=http://localhost:3000
NEXT_PUBLIC_API_URL=http://localhost:8000
DATABASE_URL=sqlite:///./test.db
```

## Project Structure

```
nurseai/
├── frontend/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   ├── globals.css
│   │   ├── auth/
│   │   ├── dashboard/
│   │   ├── practice/
│   │   ├── mock-test/
│   │   └── api/auth/
│   ├── src/
│   │   ├── components/
│   │   ├── lib/
│   │   └── types/
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   └── Dockerfile
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── models/
│   │   ├── routers/
│   │   ├── schemas/
│   │   └── services/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env
├── docker-compose.yml
└── README.md
```

## API Documentation

Once the backend is running, access interactive API docs at `http://localhost:8000/docs`

### Key Endpoints

- `POST /auth/register` - Register new user
- `POST /auth/login` - Login user
- `GET /auth/me` - Get current user info
- `GET /questions?module=speaking` - Get questions by module
- `POST /speaking/submit` - Submit speaking response
- `POST /scoring/submit` - Submit for AI scoring
- `GET /progress/stats` - Get user progress statistics

## OET Modules

The application covers all 4 OET modules:

1. **Speaking**: Real-time voice recording with transcription and feedback
2. **Writing**: Medical writing samples with AI evaluation
3. **Reading**: Comprehension questions with explanations
4. **Listening**: Audio-based questions with transcripts

## Scoring Criteria

The AI scores responses based on:

- **Fluency**: Speaking pace and naturalness
- **Vocabulary**: Medical terminology and word choice
- **Grammar**: Sentence structure and accuracy
- **Pronunciation**: Clarity and accent neutrality
- **Medical Communication**: Contextual appropriateness

## Contributing

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Commit changes: `git commit -am 'Add feature'`
3. Push to branch: `git push origin feature/your-feature`
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues or questions, please open an issue on the GitHub repository.

## Roadmap

- [ ] Speaking test with video recording
- [ ] Listening module with audio playback
- [ ] Reading comprehension module
- [ ] Writing task with templates
- [ ] Performance analytics dashboard
- [ ] Mobile app (React Native)
- [ ] Integration with real OET test format
- [ ] Multi-language support
