# Titan Finance: VPS Deployment Guide

Because Titan Finance uses a multi-container architecture (Postgres, QuestDB, Redis, multiple Python backend workers, and a Next.js frontend with WebSockets), the **best, most standard, and most cost-effective way** to deploy this is on a Virtual Private Server (VPS) via Docker Compose.

We recommend a provider like **DigitalOcean (Droplet)**, **AWS (EC2)**, **Linode**, or **Hetzner**.

## 1. Provision a Server
1. Create a new Linux VM on your preferred provider. (Ubuntu 22.04 or 24.04 LTS recommended).
2. Choose a size with at least **2GB RAM** (4GB recommended for QuestDB and the Next.js build process).
3. Ensure ports `80`, `443`, and `3000` are open in your provider's firewall.

## 2. Connect to the Server
SSH into your new server as `root` (or the default user like `ubuntu`):
```bash
ssh root@<your_server_ip>
```

## 3. Run the Setup Script
We've prepared a simple initialization script that installs Docker and Git for you. Run this command on your server:

```bash
curl -sL https://raw.githubusercontent.com/jacattac314/Titan-Finance-/main/scripts/deploy_vps.sh | bash
```
*(Note: Ensure your code is pushed to your `main` branch on GitHub so this script is accessible to `curl`).*

## 4. Launch Titan Finance
Once Docker is installed, follow these steps:

1. Clone your repository:
   ```bash
   git clone https://github.com/jacattac314/Titan-Finance-.git
   cd Titan-Finance-
   ```
2. Set up your `.env` file with your API keys:
   ```bash
   cp .env.example .env
   nano .env
   ```
   *Make sure you add `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`*.

3. Start the application:
   ```bash
   docker compose up --build -d
   ```

## 5. Access the Dashboard
Your Next.js dashboard will be accessible at:
`http://<your_server_ip>:3000`

### Optional: Set up a Domain Name and HTTPS
If you want to use a domain name (like `app.titanfinance.com`) securely:
1. Point your domain's A-record to your server's IP address.
2. We highly recommend installing **Caddy** or **Nginx** on the server to act as a reverse proxy that automatically provides SSL/HTTPS.

Here is a quick Caddy setup:
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https 
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy
```
Then create a `Caddyfile` that points your domain to port 3000:
```caddyfile
yourdomain.com {
    reverse_proxy localhost:3000
}
```
Run `sudo systemctl restart caddy`.
