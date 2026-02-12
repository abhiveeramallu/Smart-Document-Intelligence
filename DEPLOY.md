# Production Deployment Guide - Ubuntu VPS + Docker + SSL

Complete guide for deploying Smart Document Intelligence Platform in production.

## 📋 Prerequisites

- Ubuntu 22.04/24.04 VPS (8GB RAM, 4 vCPU, 50GB SSD minimum)
- Domain name with A record pointing to server IP
- SSH access with root or sudo privileges

---

## 🚀 Quick Deploy (5 minutes)

```bash
# 1. SSH to your server
ssh root@YOUR_SERVER_IP

# 2. Download and run the deploy script
curl -fsSL https://raw.githubusercontent.com/abhiveeramallu/Smart-Document-Intelligence/main/deploy/install.sh | bash

# 3. Configure environment
nano /opt/Smart-Document-Intelligence/.env
# Edit: DOMAIN=yourdomain.com, SSL_EMAIL=admin@yourdomain.com

# 4. Deploy
cd /opt/Smart-Document-Intelligence
docker compose -f docker-compose.fullstack.yml up -d

# 5. Setup SSL
./deploy/setup-ssl.sh yourdomain.com admin@yourdomain.com
```

---

## 📖 Detailed Deployment Steps

### Step 1: Server Preparation

```bash
# Update system
apt update && apt upgrade -y

# Install essential packages
apt install -y curl wget git htop ufw fail2ban nano

# Configure firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw --force enable
```

### Step 2: Install Docker

```bash
# Remove old Docker versions
apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Install Docker
apt install -y ca-certificates gnupg lsb-release
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Enable Docker
systemctl enable docker
systemctl start docker
```

### Step 3: Deploy Application

```bash
# Clone repository
git clone https://github.com/abhiveeramallu/Smart-Document-Intelligence.git /opt/Smart-Document-Intelligence
cd /opt/Smart-Document-Intelligence

# Create environment file
cp .env.example .env
nano .env
# Edit these values:
# - DOMAIN=yourdomain.com
# - SSL_EMAIL=admin@yourdomain.com
# - OLLAMA_MODEL=llama3.2:3b

# Start services
docker compose -f docker-compose.fullstack.yml up -d --build

# Pull AI model
docker compose -f docker-compose.fullstack.yml exec ollama ollama pull llama3.2:3b

# Verify health
curl http://localhost:8000/health
```

### Step 4: Install Nginx & SSL

```bash
# Install Nginx and Certbot
apt install -y nginx certbot python3-certbot-nginx

# Run SSL setup
./deploy/setup-ssl.sh yourdomain.com admin@yourdomain.com
```

### Step 5: Enable Systemd Service

```bash
# Copy systemd service
cp deploy/docintel.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable docintel
systemctl start docintel

# Check status
systemctl status docintel
docker compose -f docker-compose.fullstack.yml ps
```

---

## 🔧 Maintenance Commands

```bash
# View logs
docker compose -f docker-compose.fullstack.yml logs -f

# Update application
cd /opt/Smart-Document-Intelligence
git pull
docker compose -f docker-compose.fullstack.yml up -d --build

# Backup data
./deploy/backup.sh daily

# Restart services
docker compose -f docker-compose.fullstack.yml restart

# Check resource usage
docker stats
```

---

## 🔒 Security Checklist

- [ ] Firewall configured (ufw status)
- [ ] Ollama NOT exposed publicly (port 11434 closed)
- [ ] SSL certificate installed (https works)
- [ ] Fail2Ban running (systemctl status fail2ban)
- [ ] Automatic backups configured
- [ ] Auto-renewal enabled (certbot renew --dry-run)

---

## 📞 Support

- GitHub Issues: https://github.com/abhiveeramallu/Smart-Document-Intelligence/issues
