FROM node:20-alpine
WORKDIR /app/admin-frontend
COPY admin-frontend/package.json admin-frontend/package-lock.json ./
RUN npm ci
COPY admin-frontend .
EXPOSE 5174
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
