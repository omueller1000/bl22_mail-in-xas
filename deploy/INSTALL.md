# Installing the portal on the app VM

First-time setup of the BL22 mail-in XAS portal on the Rocky Linux 9 app VM: the **dev**
environment first, then **production**. Later updates use only step 10 (`deploy.sh`).

Run the commands as your own account with `sudo`. Every step can be repeated safely; steps that
create something first check whether it already exists.

## What runs where

| What | Where |
|---|---|
| Service account | `htxas` (system user, no login) |
| uv | `/usr/local/bin/uv` |
| Python 3.12 (installed by uv), caches | `/SSRL_LOCAL_OM/ht-xas/python`, `/SSRL_LOCAL_OM/ht-xas/cache` |
| Code, one git checkout per environment | `/SSRL_LOCAL_OM/ht-xas/prod`, `/SSRL_LOCAL_OM/ht-xas/dev` |
| Built frontends | `/SSRL_LOCAL_OM/ht-xas/www/prod`, `/SSRL_LOCAL_OM/ht-xas/www/dev` |
| Settings, with passwords | `/etc/ht-xas/prod.env`, `/etc/ht-xas/dev.env` |
| Backends (systemd) | `ht-xas@prod` on 127.0.0.1:8008, `ht-xas@dev` on 127.0.0.1:8009 |
| Web server | nginx, port 80, `/etc/nginx/conf.d/mail-in-xas.conf` |

Known facts about the VM: system Python 3.9 (left alone), Node 22.20, nginx 1.20.1,
SELinux **enforcing**, **no** host firewall (so the backends listen on 127.0.0.1 only),
outbound HTTPS works, MongoDB and the SMTP relay are reachable.

## 1. Check that /SSRL_LOCAL_OM is on local disk

```bash
findmnt -T /SSRL_LOCAL_OM
```

The `FSTYPE` must be a local filesystem (`xfs`, `ext4`), not `nfs`. A networked folder would take
the portal down whenever the file server has a problem.

## 2. Tools

```bash
sudo dnf install -y git nginx policycoreutils-python-utils
node --version     # must be 22.12 or newer (only needed to build the frontend)
```

uv, installed for the whole system (not into a home directory):

```bash
[ -x /usr/local/bin/uv ] || curl -LsSf https://astral.sh/uv/install.sh \
    | sudo env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
/usr/local/bin/uv --version
```

## 3. Service account

```bash
id htxas 2>/dev/null || sudo useradd --system --home-dir /SSRL_LOCAL_OM/ht-xas \
    --no-create-home --shell /sbin/nologin htxas
```

## 4. Directories

```bash
sudo mkdir -p /SSRL_LOCAL_OM/ht-xas/{prod,dev,python,cache} /SSRL_LOCAL_OM/ht-xas/www/{prod,dev}
sudo chown -R htxas:htxas /SSRL_LOCAL_OM/ht-xas
sudo chmod 755 /SSRL_LOCAL_OM /SSRL_LOCAL_OM/ht-xas /SSRL_LOCAL_OM/ht-xas/www
sudo mkdir -p /etc/ht-xas
```

The checkout directories must be empty before step 6 (git clones only into empty directories):

```bash
for d in prod dev; do
    [ -z "$(sudo ls -A /SSRL_LOCAL_OM/ht-xas/$d)" ] && echo "$d: empty" || echo "$d: NOT empty"
done
```

## 5. SELinux labels

New folders outside the standard locations get the generic label `default_t`, which systemd
and nginx may not use. Label the portal's folders once; the rules are stored permanently and
`restorecon` (also run by `deploy.sh`) applies them to new files:

```bash
sudo semanage fcontext -a -t usr_t '/SSRL_LOCAL_OM'
sudo semanage fcontext -a -t usr_t '/SSRL_LOCAL_OM/ht-xas(/.*)?'
sudo semanage fcontext -a -t httpd_sys_content_t '/SSRL_LOCAL_OM/ht-xas/www(/.*)?'
sudo restorecon -Rv /SSRL_LOCAL_OM/ht-xas
sudo restorecon -v /SSRL_LOCAL_OM
```

- `usr_t`: installed software (like `/opt`), which systemd may run and nginx may pass through.
- `httpd_sys_content_t`: web content that nginx may read.

(`semanage fcontext -a` reports an error if a rule already exists; that is fine.)

nginx must also be allowed to connect to the backend ports. Check whether 8008 and 8009 are
already web ports:

```bash
sudo semanage port -l | grep -w http_port_t
```

If 8008 or 8009 is missing from that line, add it:

```bash
sudo semanage port -a -t http_port_t -p tcp 8008
sudo semanage port -a -t http_port_t -p tcp 8009
```

## 6. Code

```bash
for d in dev prod; do
    sudo -u htxas git clone --quiet https://github.com/omueller1000/bl22_mail-in-xas.git \
        /SSRL_LOCAL_OM/ht-xas/$d
done
```

## 7. Settings

Start from the templates in the repository and fill in the values (MongoDB passwords, SMTP
relay, sender address; for production also the ORCID client id and secret):

```bash
sudo install -m 640 -o root -g htxas /SSRL_LOCAL_OM/ht-xas/dev/deploy/env/dev.env.example /etc/ht-xas/dev.env
sudo install -m 640 -o root -g htxas /SSRL_LOCAL_OM/ht-xas/prod/deploy/env/prod.env.example /etc/ht-xas/prod.env
sudo vi /etc/ht-xas/dev.env
```

(Only if the files do not exist yet: `install` overwrites them.) The files stay outside the
code, so deploys never touch them. Never commit them; the repository is public.

## 8. Backend service

```bash
sudo cp /SSRL_LOCAL_OM/ht-xas/dev/deploy/systemd/ht-xas@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ht-xas@dev
```

## 9. nginx

The portal's configuration replaces whatever nginx served before. Disable other site
configurations by renaming them (nginx only reads `/etc/nginx/conf.d/*.conf`), so they can be
restored later:

```bash
ls /etc/nginx/conf.d/
sudo mv /etc/nginx/conf.d/<old>.conf /etc/nginx/conf.d/<old>.conf.off
grep -n "include" /etc/nginx/nginx.conf     # is sites-enabled included? (not by default)
```

`/etc/nginx/sites-available/` is only used if `nginx.conf` includes `sites-enabled/` and the file
is linked there; then remove the link in `sites-enabled/` (the file in `sites-available/` can
stay). Also check that `nginx.conf` itself has no `server` block with `listen 80 default_server`
(`sudo nginx -t` reports the conflict); comment it out if it has.

```bash
sudo cp /SSRL_LOCAL_OM/ht-xas/dev/deploy/nginx/mail-in-xas.conf /etc/nginx/conf.d/
sudo vi /etc/nginx/conf.d/mail-in-xas.conf     # replace PROXY_IP (see below)
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

`PROXY_IP` is the address the SLAC reverse proxy connects from (the `client` shown by
`tools/proxy_probe.py`, see requirements §12.1); SLAC's HAProxy is load balanced, so list every
address its owners name, one line each, or their range in CIDR form. Do not commit the address:
the repository is public. Requests from it, and any request carrying `X-Forwarded-Host` (which the
proxy always adds), may not reach the dev environment or the instrument API; the header check
keeps them closed even if the proxy's addresses change.

Check that the block works (both must print 404 and 403):

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Forwarded-Host: test" http://localhost/mail-in-xas/dev/
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Forwarded-Host: test" http://localhost/mail-in-xas/api/instrument/queue
```

## 10. Deploy

```bash
sudo bash /SSRL_LOCAL_OM/ht-xas/dev/deploy/deploy.sh dev
```

This updates the code to the latest `main`, installs the backend (the first run downloads
Python 3.12), builds the frontend, applies the SELinux labels, restarts `ht-xas@dev` and checks
that it answers. It ends with `deployed <commit>, backend answers` and the health status.

A specific version: `sudo bash /SSRL_LOCAL_OM/ht-xas/dev/deploy/deploy.sh dev <tag-or-commit>`.

## 11. Check

```bash
curl -s http://127.0.0.1:8009/mail-in-xas/dev/api/health      # backend directly
curl -s http://localhost/mail-in-xas/dev/api/health           # through nginx
```

Both should print `"status":"ok","database":"ok"`. Then open
`http://<vm-internal-hostname>/mail-in-xas/dev/` in a browser and sign in with the dev login.

## 12. Production

The SLAC proxy already forwards `/mail-in-xas/` to port 80 of the VM (tested 2026-10-17,
requirements §12.1). Once its owners have confirmed the proxy addresses, they are set in step 9
and `/etc/ht-xas/prod.env` is filled in:

```bash
sudo systemctl enable ht-xas@prod
sudo bash /SSRL_LOCAL_OM/ht-xas/prod/deploy/deploy.sh prod
curl -s http://localhost/mail-in-xas/api/health
```

Then sign in at `https://www-ssrl.slac.stanford.edu/mail-in-xas/` with ORCID; the iD listed in
`HT_XAS_BOOTSTRAP_ADMIN_ORCIDS` becomes Admin.

## Troubleshooting

| Symptom | Look at |
|---|---|
| `deploy.sh` says the backend does not answer | `sudo journalctl -u ht-xas@dev -n 50` |
| Service fails with `status=203/EXEC` | SELinux labels (step 5): `ls -Z /SSRL_LOCAL_OM/ht-xas/dev/backend/.venv/bin/` |
| Browser shows 502 Bad Gateway | backend not running, or SELinux blocks nginx → backend (step 5, ports) |
| Browser shows 403 Forbidden for pages | SELinux labels of `www` (step 5) |
| Any of the SELinux cases | `sudo ausearch -m avc -ts recent` lists what SELinux refused |
| nginx errors | `sudo tail -n 50 /var/log/nginx/error.log` |
| Health shows `"database":"error"` | MongoDB user, password or `authSource` in `/etc/ht-xas/<env>.env` |
| No emails | Admin → Email: the recent emails and their errors |
