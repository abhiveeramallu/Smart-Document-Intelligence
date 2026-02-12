# 🚀 Production Deployment Guide - Ubuntu VPS + Domain + SSL

Complete step-by-step guide to deploy Smart Document Intelligence Platform on Ubuntu VPS with HTTPS.

## 📋 Prerequisites

- Ubuntu 22.04/24.04 VPS (8GB+ RAM, 50GB+ storage, 4+ cores)
- Domain name pointed to server IP (A record)
- SSH access to server
- Sudo privileges

---

## Step 1: Create VPS and Configure Domain

### 1.1 Create VPS

**Recommended Providers:**
- **DigitalOcean**: Droplet with 8GB RAM ($48/month)
- **Hetzner**: CPX31 (8GB RAM, €12.40/month) - Best value
- **AWS EC2**: t3.large or g4dn.xlarge with GPU
- **Vultr**: Cloud Compute with 8GB RAM

**Minimum Requirements:**
- 4 CPU cores
- 8GB RAM (16GB recommended)
- 50GB SSD storage
- Ubuntu 22.04 LTS

### 1.2 Point Domain to Server

**DNS Configuration:**
```
Type: A
Name: @ (root)
Value: YOUR_SERVER_IP
TTL: 3600
```

```
Type: A
Name: www
Value: YOUR_SERVER_IP
TTL: 3600
```

Wait 5-10 minutes for DNS propagation.

---

## Step 2: Initial Server Setup

### 2.1 SSH into Server

```bash
ssh root@YOUR_SERVER_IP
```

### 2.2 Update System

```bash
apt update && apt upgrade -y
apt install -y curl wget git htop nano ufw fail2ban
```

### 2.3 Configure Firewall (UFW)

```bash
# Reset and configure firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP
ufw allow 443/tcp     # HTTPS
# DO NOT open 11434 - Ollama stays internal
ufw enable
```

Verify:
```bash
ufw status
```

### 2.4 Configure Fail2Ban (Security)

```bash
# Already installed, just ensure it's running
systemctl enable fail2ban
systemctl start fail2ban
```

---

## Step 3: Install Docker Engine

### 3.1 Install Official Docker

```bash
# Remove old versions if any
apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Install prerequisites
apt install -y ca-certificates gnupg lsb-release

# Add Docker's official GPG key
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update and install Docker
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

### 3.2 Configure Docker

```bash
# Add user to docker group (optional - for non-root access)
usermod -aG docker root

# Enable Docker service
systemctl enable docker
systemctl start docker

# Test Docker
docker run hello-world
```

---

## Step 4: Clone and Deploy Application

### 4.1 Clone Repository

```bash
cd /opt
git clone https://github.com/abhiveeramallu/Smart-Document-Intelligence.git
cd Smart-Document-Intelligence
```

### 4.2 Optional: Harden docker-compose (Remove Public Ollama Port)

```bash
# The production compose already has this, but verify:
cat docker-compose.prod.yml | grep -A5 "ollama:"
```

**Key security points in `docker-compose.prod.yml`:**
- ❌ No `ports:` section for Ollama service
- ✅ Only internal network access: `http://ollama:11434`
- ✅ Web service binds to localhost only: `127.0.0.1:8080:80`

### 4.3 Start the Stack

```bash
# Build and start all services
docker compose -f docker-compose.prod.yml up -d --build

# Verify services are running
docker compose -f docker-compose.prod.yml ps
```

### 4.4 Pull AI Model (First Time)

```bash
# Pull llama3.2 model into Ollama
docker compose -f docker-compose.prod.yml exec ollama ollama pull llama3.2:3b

# Or for larger model (better quality, slower)
# docker compose -f docker-compose.prod.yml exec ollama ollama pull llama3.2

# Restart backend to connect to Ollama
docker compose -f docker-compose.prod.yml restart backend
```

### 4.5 Verify Local Health

```bash
# Check backend health
curl http://127.0.0.1:8080/api/health

# Check frontend
curl -I http://127.0.0.1:8080
```

You should see:
- Backend: JSON response with Ollama status
- Frontend: HTTP 200 OK

---

## Step 5: Install Nginx Reverse Proxy + SSL

### 5.1 Install Nginx and Certbot

```bash
apt install -y nginx certbot python3-certbot-nginx

# Stop Nginx temporarily (if needed)
systemctl stop nginx
```

### 5.2 Configure Nginx

Copy the provided config:

```bash
cp deploy/nginx-docintel.conf /etc/nginx/sites-available/docintel

# Edit with your actual domain
nano /etc/nginx/sites-available/docintel
# Change: yourdomain.com to your actual domain
```

Enable site:
```bash
# Enable the site
ln -s /etc/nginx/sites-available/docintel /etc/nginx/sites-enabled/

# Remove default site
rm /etc/nginx/sites-enabled/default

# Test configuration
nginx -t

# Start Nginx
systemctl start nginx
systemctl enable nginx
```

### 5.3 Obtain SSL Certificate

```bash
# Get certificate (replace with your domain)
certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Follow prompts:
# - Enter email
# - Agree to terms
# - Choose redirect HTTP to HTTPS (recommended)
```

Verify auto-renewal:
```bash
certbot renew --dry-run
```

### 5.4 Final Nginx Test

```bash
# Test configuration
nginx -t

# Reload Nginx
systemctl reload nginx

# Check status
systemctl status nginx
```

---

## Step 6: Final Testing

### 6.1 Test HTTPS Access

```bash
# Test from your local machine
curl -I https://yourdomain.com

# Should return HTTP 200 with SSL info
```

Open browser:
- **Website:** `https://yourdomain.com`
- **API Health:** `https://yourdomain.com/api/health`

### 6.2 Verify Security

```bash
# Check firewall - only 22, 80, 443 should be open
ufw status

# Verify Ollama is NOT exposed externally
nc -zv YOUR_SERVER_IP 11434
# Should fail (connection refused)

# Verify Ollama works internally
docker compose -f docker-compose.prod.yml exec backend curl http://ollama:11434/api/tags
```

### 6.3 Upload Test Document

1. Open `https://yourdomain.com`
2. Upload a PDF or document
3. Verify AI analysis completes
4. Check entities and summaries are generated

---

## Step 7: Setup Automated Backups

### 7.1 Create Backup Directory

```bash
mkdir -p /opt/backups/docintel
chmod 755 /opt/backups/docintel
```

### 7.2 Copy Backup Script

```bash
cp deploy/backup.sh /opt/backups/docintel/
chmod +x /opt/backups/docintel/backup.sh
```

### 7.3 Setup Cron Job

```bash
# Edit crontab
crontab -e

# Add these lines:
# Daily backup at 2 AM
0 2 * * * /opt/backups/docintel/backup.sh daily >> /var/log/docintel-backup.log 2>&1

# Weekly backup on Sundays at 3 AM
0 3 * * 0 /opt/backups/docintel/backup.sh weekly >> /var/log/docintel-backup.log 2>&1

# Monthly backup on 1st at 4 AM
0 4 1 * * /opt/backups/docintel/backup.sh monthly >> /var/log/docintel-backup.log 2>&1
```

### 7.4 Test Backup

```bash
/opt/backups/docintel/backup.sh daily
ls -la /opt/backups/docintel/daily/
```

---

## Step 8: Monitoring & Maintenance

### 8.1 View Logs

```bash
# All services logs
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f ollama
```

### 8.2 Update Application

```bash
cd /opt/Smart-Document-Intelligence

# Pull latest changes
git pull origin main

# Rebuild and restart
docker compose -f docker-compose.prod.yml up -d --build

# Pull model if changed
docker compose -f docker-compose.prod.yml exec ollama ollama pull llama3.2:3b
```

### 8.3 Resource Monitoring

```bash
# System resources
htop

# Docker stats
docker stats

# Disk usage
df -h
du -sh /var/lib/docker
```

### 8.4 Restart Services

```bash
# Restart all
docker compose -f docker-compose.prod.yml restart

# Restart specific service
docker compose -f docker-compose.prod.yml restart backend
```

---

## 🔒 Security Checklist

- [ ] Firewall only allows 22, 80, 443 (check: `ufw status`)
- [ ] Ollama port 11434 NOT exposed publicly (check: `nc -zv IP 11434`)
- [ ] HTTPS enabled with valid SSL certificate (check: `https://yourdomain.com`)
- [ ] HTTP redirects to HTTPS
- [ ] Fail2Ban is running (check: `systemctl status fail2ban`)
- [ ] Docker containers running as non-root (built-in)
- [ ] Automatic backups configured
- [ ] SSL auto-renewal working (check: `certbot renew --dry-run`)

---

## 🆘 Troubleshooting

### Issue: Cannot connect to website

```bash
# Check services
docker compose -f docker-compose.prod.yml ps

# Check Nginx
systemctl status nginx
nginx -t

# Check firewall
ufw status
```

### Issue: Ollama not responding

```bash
# Check Ollama logs
docker compose -f docker-compose.prod.yml logs ollama

# Test Ollama internally
docker compose -f docker-compose.prod.yml exec backend curl http://ollama:11434/api/tags

# Restart Ollama
docker compose -f docker-compose.prod.yml restart ollama
```

### Issue: SSL certificate errors

```bash
# Renew certificate manually
certbot renew --force-renewal

# Check certificate status
certbot certificates
```

### Issue: Disk space full

```bash
# Check space
df -h

# Clean Docker
docker system prune -a --volumes

# Check backup size
du -sh /opt/backups/docintel
```

---

## 📊 Cost Breakdown

| Provider | Server Spec | Monthly Cost |
|----------|-------------|--------------|
| Hetzner | CPX31 (8GB RAM, 4 vCPU) | €12.40 |
| DigitalOcean | 8GB RAM, 4 vCPU | $48 |
| AWS EC2 | t3.large | ~$65 |
| Vultr | 8GB RAM, 4 vCPU | $40 |

**SSL Certificate:** Free (Let's Encrypt)

---

## 🎉 Deployment Complete!

Your Smart Document Intelligence Platform is now:
- ✅ Running on HTTPS with valid SSL
- ✅ Secured with firewall (ports 22, 80, 443 only)
- ✅ Ollama NOT exposed publicly (internal only)
- ✅ Automatic daily backups configured
- ✅ Auto-updating SSL certificates
- ✅ Production-ready with monitoring

**Access your app:** `https://yourdomain.com`

---

## 🔗 Additional Resources

- [Docker Engine Ubuntu Install](https://docs.docker.com/engine/install/ubuntu/)
- [Docker Compose Reference](https://docs.docker.com/compose/)
- [Certbot Instructions](https://certbot.eff.org/instructions)
- [Ollama Docker Docs](https://hub.docker.com/r/ollama/ollama)

**Need help?** Open an issue on GitHub: https://github.com/abhiveeramallu/Smart-Document-Intelligence/issues
