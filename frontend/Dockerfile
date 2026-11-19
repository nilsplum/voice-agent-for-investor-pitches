# The frontend image: Node (LTS) and the packages pinned in package-lock.json. The code itself is
# mounted by docker-compose.yml at /app; node_modules stays the image's (an anonymous volume).
# A changed dependency needs ./scripts/setup.sh (or any start, which rebuilds).
FROM node:26-slim

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
