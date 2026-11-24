FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

ARG DEBIAN_FRONTEND=noninteractive

# Firewall tooling. Third-party apt sources baked into the base image (e.g. Yarn)
# sometimes have expired signing keys, which makes apt-get update fail.
RUN grep -rl yarnpkg /etc/apt/sources.list.d/ 2>/dev/null | xargs -r rm -f \
 && apt-get update && apt-get install -y --no-install-recommends \
      iptables ipset bind9-dnsutils curl \
 && rm -rf /var/lib/apt/lists/*

# uv (same source as the production Dockerfile)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Node 20 (matches the production frontend build). Copied in here rather than
# installed by a dev container feature, because features run after this file
# and could re-grant sudo after the lockdown below.
COPY --from=node:20-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:20-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && node --version && npm --version

# Root helpers. The base image gives "vscode" passwordless sudo for everything,
# which would let the agent simply turn the firewall off. Remove that and allow
# sudo for these two fixed scripts only. To add system packages later, edit this
# Dockerfile and rebuild rather than apt-installing from inside the container.
# (Firewall installed under its own name: the Claude Code dev container feature
# ships a different init-firewall.sh and would overwrite one at that path.)
COPY init-firewall.sh /usr/local/bin/sandbox-firewall.sh
COPY fix-volume-owners.sh /usr/local/bin/fix-volume-owners.sh
RUN chmod 755 /usr/local/bin/sandbox-firewall.sh /usr/local/bin/fix-volume-owners.sh \
 && rm -f /etc/sudoers.d/vscode \
 && printf '%s\n' \
      "vscode ALL=(root) NOPASSWD: /usr/local/bin/sandbox-firewall.sh" \
      "vscode ALL=(root) NOPASSWD: /usr/local/bin/fix-volume-owners.sh" \
      > /etc/sudoers.d/sandbox \
 && chmod 0440 /etc/sudoers.d/sandbox \
 && ! grep -rqsE 'NOPASSWD:[[:space:]]*ALL' /etc/sudoers /etc/sudoers.d

# Pre-create the Claude config dir so the named volume is owned by vscode
RUN mkdir -p /home/vscode/.claude && chown vscode:vscode /home/vscode/.claude

# Claude Code via the native installer. Installed at build time, before the
# firewall exists; to update it, rebuild the container.
USER vscode
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/home/vscode/.local/bin:${PATH}"
USER root
