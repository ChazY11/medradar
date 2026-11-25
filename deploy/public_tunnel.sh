#!/bin/sh
# Public HTTPS access without touching the cloud firewall.
#
# What was measured, and by whom
# ------------------------------
# Tencent Lighthouse (this host, 170.106.142.49) exposes only port 22 to the internet. A third-party
# datacentre fetching http://IP:8791, http://IP/, https://IP/ and http://IP:8787/ timed out on all
# four, while ssh on 22 answers. So inbound 80/443 cannot be used without a console change that this
# deployment cannot make.
#
# A Cloudflare quick tunnel (trycloudflare.com) resolves to anycast addresses that the operator's
# network in China cannot reach; verified earlier from that network.
#
# localhost.run works because it is an OUTBOUND ssh connection. The relay terminates TLS on its own
# domain and forwards to 127.0.0.1:8791 here. Verified 2026-11-24 from two vantage points:
#   - operator network in China: 401 in 0.67 s (the alpha gate answering, so the path is real)
#   - third-party datacentre:    401 as well
# DNS resolves to AWS us-east-1.
#
# Caveats, stated rather than hidden
# ----------------------------------
# The free tier rotates the subdomain periodically, so a bookmarked URL eventually dies. The current
# address is written to URL_FILE after every reconnect; read it there rather than remembering one.
# A stable address needs a custom domain plan, or a named Cloudflare tunnel plus a domain, or the
# Lighthouse firewall opened for 443 - all of which are operator actions.
#
# The alpha gate stays in front: the tunnel is transport only, and an anonymous request still gets
# 401 (measured through the public URL, not just on loopback).
set -u
TARGET=${TARGET:-127.0.0.1:8791}
URL_FILE=${URL_FILE:-/srv/medradar/data/radar/public_url.txt}

ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes -o BatchMode=yes \
    -R "80:$TARGET" nokey@localhost.run 2>&1 | while IFS= read -r line; do
  printf '%s %s\n' "$(date -Is)" "$line"
  case "$line" in
    *https://*.lhr.life*)
      printf '%s\n' "$(printf '%s' "$line" | grep -oE 'https://[a-z0-9]+\.app\.lhr\.life' | head -1)" > "$URL_FILE"
      ;;
  esac
done
