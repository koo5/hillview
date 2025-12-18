FROM oven/bun:1-debian AS builder

USER root
# Create non-root user
RUN groupadd -g 1001 nodejs && \
    useradd svelte -u 1001 -G nodejs



WORKDIR /app

# Copy package files
#COPY package.json bun.lock ./

COPY . .
#bun.lock package.json tsconfig.json svelte.config.* vite.config.ts tauri-plugin-hillview ./

COPY src/routes/+page.server.ts.ssr src/routes/+page.server.ts
COPY src/routes/+page.svelte.ssr    src/routes/+page.svelte

# Install dependencies
RUN bun install # --frozen-lockfile

#COPY src ./src
#COPY src-tauri/icons ./src-tauri/icons


# Build the app with Node adapter
ENV ADAPTER=node
RUN bun run build

EXPOSE 3000
USER svelte

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=3000

#RUN cat src/routes/+page.svelte

CMD ["node", "build/index.js"]
