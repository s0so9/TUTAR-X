# Football Intelligence Frontend

React + TypeScript + Vite frontend for the Football Intelligence platform.

## Architecture

```
frontend/
├── src/
│   ├── main.tsx                # Application entry point
│   ├── App.tsx                 # Root component
│   ├── api/                    # API client
│   │   ├── client.ts           # HTTP client configuration
│   │   └── endpoints/          # API endpoint functions
│   ├── components/             # Reusable components
│   │   ├── common/             # Common UI components
│   │   ├── match/              # Match-related components
│   │   ├── team/               # Team-related components
│   │   └── prediction/         # Prediction display components
│   ├── pages/                  # Page components
│   │   ├── Dashboard.tsx       # Gösterge Paneli
│   │   ├── Matches.tsx         # Maçlar
│   │   ├── MatchDetail.tsx     # Maç Detayı
│   │   ├── Teams.tsx           # Takımlar
│   │   ├── TeamDetail.tsx      # Takım Detayı
│   │   ├── Players.tsx         # Oyuncular
│   │   ├── PlayerDetail.tsx    # Oyuncu Detayı
│   │   ├── Predictions.tsx     # Tahminler
│   │   ├── Analytics.tsx       # Analiz
│   │   ├── Backtesting.tsx     # Geri Test
│   │   ├── Live.tsx            # Canlı
│   │   └── Settings.tsx        # Ayarlar
│   ├── hooks/                  # Custom React hooks
│   │   ├── useMatch.ts         # Match data hook
│   │   ├── usePrediction.ts    # Prediction data hook
│   │   └── useTeam.ts          # Team data hook
│   ├── types/                  # TypeScript types
│   │   ├── match.ts            # Match types
│   │   ├── prediction.ts       # Prediction types
│   │   ├── team.ts             # Team types
│   │   └── api.ts              # API types
│   ├── utils/                  # Utility functions
│   │   ├── format.ts           # Formatting utilities
│   │   └── probability.ts      # Probability display utilities
│   └── styles/                 # Global styles
│       └── global.css          # Global CSS
├── public/                     # Static assets
└── index.html                  # HTML entry point
```

## Technology Stack

- **React**: UI framework
- **TypeScript**: Type safety
- **Vite**: Build tool and dev server
- **React Router**: Client-side routing

## Setup

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Type check
npm run type-check

# Lint
npm run lint
```

## Development Principles

1. **Turkish UI**: User-facing text in Turkish, code in English
2. **Type Safety**: Full TypeScript coverage
3. **Component Modularity**: Small, focused, reusable components
4. **Dark Theme**: Professional dark interface
5. **Data Density**: High information density without clutter
6. **Responsive**: Mobile-friendly responsive layouts

## API Integration

The frontend connects to the backend API at `http://127.0.0.1:8002/api/v1/`.

Vite proxy configuration handles development CORS.

## Design System

- **Colors**: Dark theme with subtle borders
- **Typography**: Modern, clear hierarchy
- **Layout**: Professional cards and tables
- **Charts**: Data visualization where appropriate
- **Spacing**: Consistent spacing scale

## Turkish Labels

- Dashboard → Gösterge Paneli
- Matches → Maçlar
- Predictions → Tahminler
- Analytics → Analiz
- Backtesting → Geri Test
- Live → Canlı
- Teams → Takımlar
- Players → Oyuncular
- AI Analyst → AI Analisti
- Settings → Ayarlar

## Notes

- Keep technical identifiers in English
- User-facing strings in Turkish
- Never display mock data as real data
- Label development data clearly
