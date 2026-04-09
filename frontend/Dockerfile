FROM oven/bun:1-debian AS builder

WORKDIR /app

COPY . .

COPY src/routes/+page.server.ts.ssr src/routes/+page.server.ts
COPY src/routes/+page.svelte.ssr    src/routes/+page.svelte

# Install dependencies
RUN bun install --frozen-lockfile

# Build the app with Node adapter
ENV ADAPTER=node
RUN bun run build


FROM oven/bun:1-debian

# Create non-root user
RUN groupadd -g 1001 nodejs && \
    useradd svelte -u 1001 -G nodejs

WORKDIR /app

# Copy only the build output from the builder stage
COPY --from=builder --chown=svelte:nodejs /app/build ./build

EXPOSE 3000
USER svelte

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=3000

CMD ["bun", "build/index.js"]
