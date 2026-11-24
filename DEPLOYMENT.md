# Deployment

**Today:** the paper bot runs as a plain Python process on a Windows PC (`python -m bot.main paper`). It stops if the PC sleeps or reboots.

**Docker (written, NOT built or run):** `Dockerfile` + `docker-compose.yml` run the same command with `restart: unless-stopped`, secrets from `.env`, state in mounted folders, UTC timezone. Build and a 48 h soak test are required before trusting it.

**Hosting options (prices unverified):** an always-free cloud VM (e.g. Oracle, Mumbai/Hyderabad) for paper/testnet; a small paid VPS with a static IP for anything live (the exchange API key's IP whitelist needs a fixed IP).

**Gates before live** (master prompt gates 9-12): 30-90 days real-time paper trading, shadow trading, testnet checklist (`testnet-check`) passing, manual authorization, small capital. None are complete.


## Windows scheduled tasks (set up 2026-11-24; later found removed, and left removed by the user's choice - kept here for re-creation)
| Task | Runs | Trigger | On failure | Time limit |
|---|---|---|---|---|
| `IndiaCryptoBot-paper` | `conhost --headless cmd /c run_bot.cmd paper` | at your logon | restart every 1 min, up to 999 times | none |
| `IndiaCryptoBot-shadow` | `conhost --headless cmd /c run_bot.cmd shadow` | at your logon | same | none |

* `run_bot.cmd` only accepts `paper` or `shadow`; live cannot be started from it.
* A lock file (`state/<mode>/bot.lock`) makes a second copy refuse to start, so a manual start cannot double-trade one account.
* Limits: tasks run only while you are logged in (running before login needs administrator rights, which were not used) and only while the PC is awake. Sleep pauses the bots; set Windows sleep to "Never" on mains power if you want unbroken forward-testing.
* Stop: `Stop-ScheduledTask -TaskName IndiaCryptoBot-paper` (and `-shadow`). Remove: `Unregister-ScheduledTask -TaskName IndiaCryptoBot-paper -Confirm:$false`.


## 24/7 on a cloud server (prepared 2026-11-24, not yet deployed)
The PC setup above stops when the PC sleeps or you log out. A small Linux server runs around the clock. Everything below is paper and shadow only; no exchange keys go to the server.

**What is ready:** `docker-compose.yml` (two containers, `paper` and `shadow`, `restart: unless-stopped`, heartbeat health checks, no `.env` loaded), `.dockerignore` (keeps `.env` and state out of the image), `deploy/setup_vps.sh` (one-command server setup), `deploy/make_bundle.sh` (upload bundle, refuses to include `.env`). The bundle's 57 tests pass from a clean copy.
**What is NOT verified:** the Docker image has never been built (Docker Desktop cannot run on this PC: WSL has no Linux installed). The first build will happen on the server; watch its output.

### Steps (you do 1-2; the rest is copy-paste)
1. Create a free cloud account (for example Oracle Cloud "Always Free", home region Mumbai or Hyderabad). This needs your identity and card for verification; I cannot do it for you.
2. Create a VM: Ubuntu 24.04, shape "VM.Standard.A1.Flex" (ARM, free; 1 OCPU / 6 GB is plenty) or "VM.Standard.E2.1.Micro". Download the SSH private key it offers. Note the public IP. Free ARM capacity is sometimes "out of capacity"; retry later or use the E2 micro.
3. On this PC, **stop the local bots first** so the paper account does not fork into two copies:
   `Stop-ScheduledTask -TaskName IndiaCryptoBot-paper; Stop-ScheduledTask -TaskName IndiaCryptoBot-shadow`
   then build the bundle with the current state (Git Bash, in `C:	b\india-crypto-ai-bot`):
   `bash deploy/make_bundle.sh --with-state`
4. Upload and install (PowerShell; replace KEY and IP):
   `scp -i KEY deploy/bundle.tar.gz ubuntu@IP:~/`
   `ssh -i KEY ubuntu@IP "tar xzf bundle.tar.gz -C ~/ && sudo bash ~/india-crypto-ai-bot/deploy/setup_vps.sh"`
5. Check it is alive (after about 20 minutes): `ssh -i KEY ubuntu@IP "cd ~/india-crypto-ai-bot && sudo docker compose ps && tail -n 3 state/paper.log"`. You want both containers "healthy" and a fresh `candle ... | equity` line.
6. Only when the server is confirmed healthy, disable the PC tasks so they cannot restart at your next logon:
   `Disable-ScheduledTask -TaskName IndiaCryptoBot-paper; Disable-ScheduledTask -TaskName IndiaCryptoBot-shadow`

### Risks and checks
* **Market data access:** signals use Binance's public API. Some providers' IP ranges are blocked by some exchanges. If the logs show repeated fetch errors, the bot will stay in cash (fail-safe), but no forward evidence accrues; report it.
* **One account, one place:** never run paper on both the PC and the server; the lock file only works on one machine.
* **Backups:** copy `state/` off the server weekly: `scp -r -i KEY ubuntu@IP:~/india-crypto-ai-bot/state ./state_backup_YYYYMMDD`.
* **Updates:** rebuild the bundle (without `--with-state`), upload, then on the server `tar xzf bundle.tar.gz -C ~/ && cd ~/india-crypto-ai-bot && sudo docker compose up -d --build`. The server's `state/` is not overwritten by a code-only bundle.
* **Cost:** Oracle Always Free is 0 INR if you stay within free shapes; set a budget alert of a small amount in the console anyway.
