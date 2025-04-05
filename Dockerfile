FROM klakegg/hugo:latest AS builder
WORKDIR /src
COPY . .
RUN hugo

#Serve the static files with Nginx
FROM nginx:stable-alpine
LABEL maintainer="Your Name <your.email@example.com>"

#Remove default Nginx welcome page
RUN rm -rf /usr/share/nginx/html/*

# Copy static files from the local 'public' directory (created by 'hugo')
COPY --from=builder /src/public /usr/share/nginx/html

# Expose port 80 (Nginx default) within the container
EXPOSE 80

# Command to run Nginx in the foreground
CMD ["nginx", "-g", "daemon off;"]
