# Deployment

**Today:** paper and shadow run on the Windows PC, restarted by the scheduled launchers below. Sleep and power loss still interrupt both.

**Docker:** `Dockerfile` + `docker-compose.yml` define paper/shadow with `restart: unless-stopped`, state in mounted folders, UTC timezone and pinned dependencies. They do not load `.env` or need exchange keys. See AUDIT_REPORT.md for build/smoke evidence; a 48-hour always-on soak remains a separate requirement.

**Hosting options (prices unverified):** an always-free cloud VM (e.g. Oracle, Mumbai/Hyderabad) for paper/testnet; a small paid VPS with a static IP for anything live (the exchange API key's IP whitelist needs a fixed IP).

**Gates before live** (master prompt gates 9-12): 30-90 days real-time paper trading, shadow trading, testnet checklist (`testnet-check`) passing, manual authorization, small capital. None are complete.


## Windows scheduled tasks (re-created 2026-11-25, active)
| Task | Runs | Trigger | Time limit |
|---|---|---|---|
| `IndiaCryptoBot-paper` | `wscript.exe deploy\start_bot_hidden.vbs paper` | at your logon, and every 10 minutes | none |
| `IndiaCryptoBot-shadow` | `wscript.exe deploy\start_bot_hidden.vbs shadow` | same | none |
| `IndiaCryptoBot-backup` (added 2026-11-27) | `pythonw.exe -m bot.backup --drill` (no window), in the project folder | daily 09:00 local; runs at the next chance if missed | 30 min |

* The backup task zips each bot's state database and ledger into `backups\state_<UTC>.zip` (consistent SQLite copy while the bots run), checks every file's hash, test-restores into a temporary folder, compares row counts and writes `reports/backup_drill.json`. It keeps the newest 14 zips. Copy `backups\` off this PC weekly; a dead disk takes the backups with it.

* `start_bot_hidden.vbs` starts `run_bot.cmd <mode>` with no window, and exits quietly if that bot is already running. So the 10-minute check only restarts a bot that has died, and it fills no logs.
* `run_bot.cmd` and the launcher accept only `paper` or `shadow`; live cannot be started from either.
* A lock file (`state/<mode>/bot.lock`) makes a second copy refuse to start, so a manual start cannot double-trade one account.
* Bots started by the tasks are not children of the desktop app session that started them, so an app restart no longer kills them (that stopped both bots at about 06:05 on 2026-11-25).
* Limits: the tasks run only while you are logged in (running before login needs administrator rights, which were not used) and only while the PC is awake. **Sleep pauses the bots**: on 2026-11-25 the lid or power button put the PC to sleep from 07:17 to 17:12 and about 40 candles were missed. For unbroken forward-testing, set "When I close the lid" and "Sleep" to "Do nothing"/"Never" on mains power, or use the cloud server below.
* Stop: `Stop-ScheduledTask -TaskName IndiaCryptoBot-paper` (and `-shadow`) stops the launcher only; to stop a running bot, end its `python ... bot.main paper` process. Disable restarts: `Disable-ScheduledTask -TaskName IndiaCryptoBot-paper`. Remove: `Unregister-ScheduledTask -TaskName IndiaCryptoBot-paper -Confirm:$false`.


## 24/7 on a cloud server (prepared 2026-11-24, not yet deployed)
The PC setup above stops when the PC sleeps or you log out. A small Linux server runs around the clock. Everything below is paper and shadow only; no exchange keys go to the server.

**What is ready:** `docker-compose.yml` (paper/shadow only, restart policy, completed-step health checks, no `.env` loaded), `.dockerignore`, `deploy/setup_vps.sh`, and `deploy/make_bundle.py` / its Bash wrapper. The bundler excludes credentials and holds both bot locks during state migration. The full offline suite and a Docker build/network-disabled smoke check were exercised in the full audit; exact results are in AUDIT_REPORT.md.
**What is NOT verified:** deployment on your chosen server, its market-data connectivity and a 48-hour always-on soak. A local image build and import smoke check do not prove production uptime.

### Steps (you do 1-2; the rest is copy-paste)
1. Create a free cloud account (for example Oracle Cloud "Always Free", home region Mumbai or Hyderabad). This needs your identity and card for verification; I cannot do it for you.
2. Create a VM: Ubuntu 24.04, shape "VM.Standard.A1.Flex" (ARM, free; 1 OCPU / 6 GB is plenty) or "VM.Standard.E2.1.Micro". Download the SSH private key it offers. Note the public IP. Free ARM capacity is sometimes "out of capacity"; retry later or use the E2 micro.
3. On this PC, **disable the paper/shadow restart tasks first**, then stop the actual bot processes so the account cannot fork:
   `Disable-ScheduledTask -TaskName IndiaCryptoBot-paper; Disable-ScheduledTask -TaskName IndiaCryptoBot-shadow`
   `Stop-ScheduledTask` only stops the short-lived launcher; it does not stop the already-running Python bots. List the paper/shadow Python PIDs, confirm they belong to this project, and stop those confirmed PIDs (both the venv launcher and child). Do not stop unrelated Python processes or the backup task. Recheck that neither bot remains running.
   then build the bundle with the current state (Git Bash, in `C:	b\india-crypto-ai-bot`):
   `bash deploy/make_bundle.sh --with-state`
   Activate the project Python environment first, or set `PYTHON` to its executable. PowerShell can instead run `C:\tb\venv\Scripts\python.exe deploy\make_bundle.py --with-state`. The bundler refuses state migration while either bot's lock is held and holds both locks throughout archiving. Keep the PC launchers disabled afterwards: lock files cannot prevent a copy on another machine.
4. Upload and install (PowerShell; replace KEY and IP):
   `scp -i KEY deploy/bundle.tar.gz ubuntu@IP:~/`
   `ssh -i KEY ubuntu@IP "tar xzf bundle.tar.gz -C ~/ && sudo bash ~/india-crypto-ai-bot/deploy/setup_vps.sh"`
5. Check it is alive (after about 20 minutes): `ssh -i KEY ubuntu@IP "cd ~/india-crypto-ai-bot && sudo docker compose ps && tail -n 3 state/paper.log"`. You want both containers "healthy" and a fresh `candle ... | equity` line.
6. Confirm the PC launchers remain disabled. If migration fails, stop both server services first and reconcile which state is authoritative before re-enabling any PC launcher. Never resume both copies.

### Risks and checks
* **Market data access:** signals use Binance's public API. Some providers' IP ranges are blocked by some exchanges. If the logs show repeated fetch errors, the bot will stay in cash (fail-safe), but no forward evidence accrues; report it.
* **One account, one place:** never run paper on both the PC and the server; the lock file only works on one machine.
* **Backups:** copy `state/` off the server weekly: `scp -r -i KEY ubuntu@IP:~/india-crypto-ai-bot/state ./state_backup_YYYYMMDD`.
* **Updates:** rebuild the bundle (without `--with-state`), upload, then on the server `tar xzf bundle.tar.gz -C ~/ && cd ~/india-crypto-ai-bot && sudo docker compose up -d --build`. The server's `state/` is not overwritten by a code-only bundle.
* **Cost:** Oracle Always Free is 0 INR if you stay within free shapes; set a budget alert of a small amount in the console anyway.
