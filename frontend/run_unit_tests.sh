#!/bin/bash
cd "$(dirname "$(readlink -f -- "$0")")"

bun install --frozen-lockfile
bun run test:unit
