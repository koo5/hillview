FROM oven/bun:1-debian AS builder

WORKDIR /app

COPY . .

COPY src/routes/+page.svelte.web src/routes/+page.svelte
COPY src/routes/+page.ts.web     src/routes/+page.ts
COPY src/routes/bestof/+page.ts.web src/routes/bestof/+page.ts
COPY src/routes/about/+page.ts.web      src/routes/about/+page.ts
COPY src/routes/contact/+page.ts.web    src/routes/contact/+page.ts
COPY src/routes/privacy/+page.ts.web    src/routes/privacy/+page.ts
COPY src/routes/terms/+page.ts.web      src/routes/terms/+page.ts
COPY src/routes/licensing/+page.ts.web  src/routes/licensing/+page.ts
COPY src/routes/download/+page.ts.web   src/routes/download/+page.ts
# Docker COPY interprets `[uid]` as a glob character class and silently fails,
# so we copy the photo/[uid] shadow via shell.
RUN cp "src/routes/photo/[uid]/+page.ts.web" "src/routes/photo/[uid]/+page.ts"

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
