#!/bin/bash
# SSL Certificate Setup Script for Smart Document Intelligence Platform
# This script automates Let's Encrypt SSL certificate acquisition

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DOMAIN=${1:-yourdomain.com}
EMAIL=${2:-admin@yourdomain.com}

# Validation
if [ "$DOMAIN" = "yourdomain.com" ]; then
    echo -e "${RED}ERROR: Please provide your actual domain name${NC}"
    echo "Usage: $0 yourdomain.com admin@yourdomain.com"
    exit 1
fi

echo -e "${YELLOW}============================================${NC}"
echo -e "${YELLOW}Setting up SSL for: ${DOMAIN}${NC}"
echo -e "${YELLOW}Email: ${EMAIL}${NC}"
echo -e "${YELLOW}============================================${NC}"

# Step 1: Install Certbot
echo -e "\n${GREEN}Step 1: Installing Certbot...${NC}"
if ! command -v certbot &> /dev/null; then
    apt-get update
    apt-get install -y certbot python3-certbot-nginx
else
    echo "Certbot already installed"
fi

# Step 2: Update Nginx config with domain
echo -e "\n${GREEN}Step 2: Updating Nginx configuration...${NC}"
sed -i "s/server_name _;/server_name ${DOMAIN} www.${DOMAIN};/g" /etc/nginx/sites-enabled/default || true
sed -i "s/yourdomain.com/${DOMAIN}/g" /etc/nginx/sites-enabled/default || true

# Step 3: Create webroot for Certbot
echo -e "\n${GREEN}Step 3: Creating Certbot webroot...${NC}"
mkdir -p /var/www/certbot

# Step 4: Test Nginx configuration
echo -e "\n${GREEN}Step 4: Testing Nginx configuration...${NC}"
nginx -t

# Step 5: Reload Nginx
echo -e "\n${GREEN}Step 5: Reloading Nginx...${NC}"
systemctl reload nginx

# Step 6: Obtain SSL certificate
echo -e "\n${GREEN}Step 6: Obtaining SSL certificate...${NC}"
certbot --nginx \
    --non-interactive \
    --agree-tos \
    --email ${EMAIL} \
    -d ${DOMAIN} \
    -d www.${DOMAIN} \
    --redirect \
    --hsts \
    --staple-ocsp

# Step 7: Verify certificate
echo -e "\n${GREEN}Step 7: Verifying certificate...${NC}"
if certbot certificates | grep -q "${DOMAIN}"; then
    echo -e "${GREEN}✓ Certificate successfully installed${NC}"
else
    echo -e "${RED}✗ Certificate installation failed${NC}"
    exit 1
fi

# Step 8: Setup auto-renewal
echo -e "\n${GREEN}Step 8: Setting up auto-renewal...${NC}"
systemctl enable certbot.timer
systemctl start certbot.timer

# Step 9: Test auto-renewal
echo -e "\n${GREEN}Step 9: Testing auto-renewal...${NC}"
certbot renew --dry-run

# Step 10: Create renewal hook for Docker
echo -e "\n${GREEN}Step 10: Creating renewal hook...${NC}"
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh << 'EOF'
#!/bin/bash
# Reload Nginx after certificate renewal
docker exec docintel-nginx nginx -s reload || true
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

echo -e "\n${GREEN}============================================${NC}"
echo -e "${GREEN}SSL Setup Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo -e "Domain: ${DOMAIN}"
echo -e "Certificate: /etc/letsencrypt/live/${DOMAIN}/"
echo -e "Auto-renewal: Enabled"
echo -e "\nTest your site: https://${DOMAIN}"
