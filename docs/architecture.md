# Initial architecture

The application starts as a local-first monorepo. The frontend communicates with a localhost-only FastAPI backend. Financial domain rules belong in backend services and repositories; the frontend is responsible for presentation, forms, and user interaction.

The first vertical slice is the health check and application shell. Currency-aware accounts, categories, transactions, and migrations will be added in subsequent focused slices.
