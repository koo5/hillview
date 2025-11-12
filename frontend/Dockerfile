FROM oven/bun:1-alpine AS builder

WORKDIR /app

# Copy package files
#COPY package.json bun.lock ./

# Copy source code
COPY . .
#bun.lock package.json tsconfig.json svelte.config.* vite.config.ts tauri-plugin-hillview ./
COPY src/routes/+page.server.ts.ssr src/routes/+page.server.ts
COPY src/routes/+page.svelte.ssr    src/routes/+page.svelte

# Install dependencies
RUN bun install # --frozen-lockfile

COPY src ./src
COPY src-tauri/icons ./src-tauri/icons

# Build the app with Node adapter
ENV ADAPTER=node
RUN bun run build

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S svelte -u 1001 -G nodejs

USER svelte

EXPOSE 3000

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=3000

CMD ["node", "build/index.js"]
