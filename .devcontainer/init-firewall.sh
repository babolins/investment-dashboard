#!/usr/bin/env bash
# Outbound allowlist firewall for the dev container.
# Runs as root from postStartCommand. If a CDN rotates IPs and something stops
# working, re-run:  sudo /usr/local/bin/sandbox-firewall.sh
set -euo pipefail

ALLOWED_DOMAINS=(
  # Claude Code: API and sign-in
  api.anthropic.com
  console.anthropic.com
  platform.claude.com
  claude.ai
  # Python packages
  pypi.org
  files.pythonhosted.org
  # npm packages
  registry.npmjs.org
  # VS Code server + the extensions listed in devcontainer.json
  update.code.visualstudio.com
  marketplace.visualstudio.com
  vscode.blob.core.windows.net
  gallery.vsassets.io
  ms-python.gallerycdn.vsassets.io
  charliermarsh.gallerycdn.vsassets.io
  dbaeumer.gallerycdn.vsassets.io
  anthropic.gallerycdn.vsassets.io
)

# Open up first so a re-run can resolve DNS, then clear the filter table.
# (The nat table is left alone so Docker's internal DNS keeps working.)
iptables -P INPUT ACCEPT
iptables -P OUTPUT ACCEPT
iptables -P FORWARD ACCEPT
iptables -F
iptables -X
ipset destroy allowed-domains 2>/dev/null || true
ipset create allowed-domains hash:net

echo "Resolving allowlist..."
for domain in "${ALLOWED_DOMAINS[@]}"; do
  ips=$(dig +short A "$domain" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' || true)
  if [ -z "$ips" ]; then
    echo "  WARN: could not resolve $domain"
    continue
  fi
  while read -r ip; do
    ipset add allowed-domains "$ip" -exist
  done <<< "$ips"
done

# Loopback (VS Code port forwarding and the Vite -> FastAPI proxy use it)
# and replies to connections we started
iptables -A INPUT  -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A INPUT  -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# DNS, then HTTPS to allowlisted IPs only. Everything else is rejected.
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 443 -m set --match-set allowed-domains dst -j ACCEPT
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

# Block IPv6 entirely (allowlist is IPv4-only); ignore errors if IPv6 is absent.
ip6tables -F 2>/dev/null || true
ip6tables -A INPUT  -i lo -j ACCEPT 2>/dev/null || true
ip6tables -A OUTPUT -o lo -j ACCEPT 2>/dev/null || true
ip6tables -P INPUT DROP 2>/dev/null || true
ip6tables -P FORWARD DROP 2>/dev/null || true
ip6tables -P OUTPUT DROP 2>/dev/null || true

# Verify
if curl -s --max-time 5 -o /dev/null https://example.com; then
  echo "FIREWALL CHECK FAILED: example.com is reachable" >&2
  exit 1
fi
if curl -s --max-time 5 -o /dev/null https://github.com; then
  echo "FIREWALL CHECK FAILED: github.com is reachable" >&2
  exit 1
fi
if ! curl -s --max-time 5 -o /dev/null https://api.anthropic.com; then
  echo "WARN: api.anthropic.com is not reachable; Claude Code won't work" >&2
fi
echo "Firewall active: outbound HTTPS limited to the allowlist."
