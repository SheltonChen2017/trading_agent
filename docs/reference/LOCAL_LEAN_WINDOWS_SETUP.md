# Local LEAN on Windows — installation and authentication guide

Status: current setup reference, created 2026-08-21.

Verified on this machine, 2026-08-21:

- LEAN CLI `1.0.228` returns successfully from its installed executable;
- `lean whoami` returns successfully without exposing or recording its output;
- the isolated `C:\QuantConnect\ACER` workspace contains `lean.json`, `data\`,
  and the generated `InstallationTest` project;
- Docker Desktop is running from its per-user installation under
  `C:\Users\<username>\AppData\Local\Programs\DockerDesktop`; and
- the Docker client and server both report version `29.7.2`.

The generated five-day SPY `InstallationTest` also ran successfully through
local LEAN Engine `2.5.0.0` using the official image with digest
`sha256:817716616e7a5875964fc111a1ddd898cead5151c4d46e2007977fd03370ee24`.
It processed 3,943 sample data points; all 13 data requests succeeded and none
failed. This was an installation check, not an ACER signal/outcome execution
or research look.

The Codex desktop process was already open when LEAN and Docker were installed,
so its inherited `PATH` does not expose the `lean` or `docker` command names.
Their full executable paths work. A newly opened PowerShell should inherit the
new paths; if it does not, use the repair steps below. Successful sample
execution does not establish that ACER's required market datasets are present.

This guide installs the QuantConnect LEAN engine locally on Windows through
the LEAN CLI and Docker. It also covers the Windows problems encountered in
the first installation on this project: a missing `lean` command, the
invisible API-token prompt, embedded whitespace copied from email, command-
line parsing when a token begins with option-like characters, and a stopped
Windows Time service.

Installing LEAN installs an execution environment. It does **not** purchase or
download full historical market data, grant dataset entitlements, or authorize
a backtest. Keep the LEAN organization workspace separate from this Git
repository.

## 1. Components and requirements

Local LEAN has two separate components:

1. **Docker Desktop** runs the official LEAN engine image in an isolated Linux
   container.
2. **LEAN CLI** supplies commands such as `lean login`, `lean init`, and
   `lean backtest`.

Installing Docker does not install the `lean` command, and installing the CLI
does not install Docker.

Windows requirements documented by QuantConnect:

- 64-bit processor;
- Windows 10 version 1903 or newer;
- hardware virtualization enabled;
- at least 4 GB RAM; and
- approximately 60 GB or more of available disk space.

Official references:

- [QuantConnect: Install on Windows](https://www.quantconnect.com/docs/v2/local-platform/installation/install-on-windows)
- [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
- [LEAN CLI getting started](https://www.quantconnect.com/docs/v2/lean-cli/key-concepts/getting-started)

## 2. Install Docker Desktop

1. Install Docker Desktop for Windows from Docker's official site.
2. Enable the WSL 2 backend during installation.
3. Restart Windows.
4. If Docker reports an incomplete WSL installation, open **Administrator
   PowerShell** and run:

   ```powershell
   wsl --update
   ```

5. Start Docker Desktop.
6. Verify that both the client and engine respond:

   ```powershell
   docker version
   ```

Docker must be running whenever a local LEAN engine command executes. If
`docker` is not recognized immediately after installation, close and reopen
PowerShell so it inherits the updated `PATH`.

The optional image pre-download is:

```powershell
docker pull quantconnect/lean
```

The image is large and can take a substantial time to download. LEAN can also
pull it when first needed.

## 3. Install a supported Python and the LEAN CLI

QuantConnect states that the Microsoft Store Python distribution is not
supported for LEAN CLI. Prefer 64-bit Miniconda, Anaconda, or a standard
python.org installation. Installing a supported Python does not require
removing another Python used by this repository.

From the supported Python's terminal:

```powershell
python --version
python -m pip install --upgrade pip
python -m pip install --upgrade lean
lean --version
```

Official reference:
[QuantConnect: Installing pip](https://www.quantconnect.com/docs/v2/lean-cli/installation/installing-pip).

### Repair `lean is not recognized`

If `python -m pip show lean` reports an installed package but PowerShell cannot
find `lean`, locate the Python scripts directory:

```powershell
python -m pip show lean

$pythonTag = python -c "import sys; print(f'Python{sys.version_info.major}{sys.version_info.minor}')"
$userBase = (python -m site --user-base).Trim()
$leanScripts = Join-Path $userBase "$pythonTag\Scripts"
$leanExe = Join-Path $leanScripts "lean.exe"

$leanExe
Test-Path $leanExe
& $leanExe --version
```

If `Test-Path` returns `True`, enable the command for the current terminal:

```powershell
$env:Path = "$env:Path;$leanScripts"
lean --version
```

To add the folder to the user's future terminal sessions without overwriting
the existing user path:

```powershell
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")

if (($userPath -split ";") -notcontains $leanScripts) {
    [Environment]::SetEnvironmentVariable(
        "Path",
        "$userPath;$leanScripts",
        "User"
    )
}
```

Close and reopen PowerShell after making the persistent change.

## 4. Log in safely

The LEAN CLI requires membership in a paid QuantConnect organization tier.
Request the API credentials from QuantConnect **My Account → Security →
Request Email With Token and Your User-Id for API Requests**.

Run:

```powershell
lean login
```

The user-id prompt echoes normally. The API-token prompt deliberately echoes
**nothing**: no characters, dots, asterisks, or visible cursor movement. This
is normal. Typing, backspace, and paste may all appear to do nothing.

Never paste the API token into a chat, document, source file, test, log, or Git
commit. Do not use `--show-secrets` for ordinary setup.

### Remove copied email whitespace without displaying the token

Email clients may insert spaces or line breaks into a long token. `Trim()`
only removes whitespace at the beginning and end; it does not remove an
embedded line break. Copy **only** the token, then immediately run:

```powershell
$qcToken = (Get-Clipboard -Raw) -replace '\s', ''

"Contains whitespace: $($qcToken -match '\s')"
"Looks like URL: $([Uri]::IsWellFormedUriString($qcToken, 'Absolute'))"
```

The first result must be `False`, and the second should be `False`. These
checks do not print the token. Copying another command before creating
`$qcToken` replaces the token in the clipboard, so preserve the order.

Use one quoted option argument. The `=` prevents token characters from being
parsed as another command-line option:

```powershell
lean login --user-id=<YOUR_USER_ID> "--api-token=$qcToken"
```

Then immediately remove the temporary variable and verify the account:

```powershell
Remove-Variable qcToken
lean whoami
```

PowerShell history stores the literal variable name in this procedure, not
the expanded token. The expanded value is still supplied briefly to the local
LEAN process, so use this only on a trusted personal computer.

## 5. Correct invalid-credential errors

QuantConnect authentication is time-sensitive. If LEAN says the credentials
are invalid, first synchronize Windows time. In **Administrator PowerShell**:

```powershell
Set-Service -Name W32Time -StartupType Automatic
Start-Service W32Time
w32tm /resync /force
w32tm /query /status
```

If `Set-Service` reports access denied, reopen PowerShell with **Run as
administrator**.

After the clock is synchronized:

1. request the current credentials again from the QuantConnect account page;
2. copy only the API token;
3. remove embedded whitespace as shown above; and
4. retry login.

Do not reset the API token as the first response. Resetting invalidates the
token used by other computers, environment variables, scripts, and agent
sessions. If a reset is eventually necessary, update every authorized secret
store separately and never commit the new value.

Official references:

- [QuantConnect authentication](https://www.quantconnect.com/docs/v2/lean-cli/initialization/authentication)
- [QuantConnect token request/reset](https://www.quantconnect.com/docs/v2/cloud-platform/community/profile#08-Request-API-Token)
- [LEAN CLI troubleshooting](https://www.quantconnect.com/docs/v2/lean-cli/key-concepts/troubleshooting)

## 6. Create a separate organization workspace

Do not run `lean init` inside `C:\git\customizedAgent\trading_agent`. LEAN
creates its own configuration, data, storage, and project directories that do
not belong in this repository.

Create and initialize a separate workspace:

```powershell
New-Item -ItemType Directory -Path C:\QuantConnect\ACER -Force
Set-Location C:\QuantConnect\ACER
lean init --language python
```

Select the intended QuantConnect organization. A successful initialization
creates at least `lean.json` and `data\` in the workspace. LEAN stores global
CLI credentials under `C:\Users\<username>\.lean`; do not edit or commit those
files manually.

## 7. Verify the installation with sample data

With Docker Desktop running:

```powershell
Set-Location C:\QuantConnect\ACER
lean whoami
lean project-create InstallationTest --language python
lean backtest InstallationTest
```

A successful sample backtest proves that:

- the CLI runs;
- authentication works;
- Docker can launch the LEAN container; and
- the organization workspace is valid.

It does **not** prove that ACER's historical datasets are installed, licensed,
complete, point-in-time, or suitable for delisted securities.

## 8. Cloud data versus local data

QuantConnect Cloud provides cloud access to core US Equity prices, corporate
actions, mappings, and fundamentals. The `$600/year` US Equity Security Master
listing is the local/on-premise download licence, not evidence that cloud
access is absent.

Local LEAN needs local data. For QuantConnect-hosted US Equity downloads, the
Security Master is a prerequisite and the underlying US Equity price files are
separate. Installing Docker, LEAN CLI, or `lean init` does not purchase them.

Do not purchase data merely to validate this installation. First decide
whether the research contract requires local LEAN or can use QuantConnect
Cloud, then perform a narrow entitlement/coverage audit. For ACER specifically,
ETF constituent history is not required for the decisive stock-level ACER-2
test; it becomes relevant only if ACER-2 passes and the owner later authorizes
ACER-3.

Official references:

- [US Equity Security Master](https://www.quantconnect.com/data/quantconnect-us-equity-security-master)
- [Local US Equity data and prerequisites](https://www.quantconnect.com/docs/v2/lean-cli/datasets/quantconnect/us-equity)
- [QuantConnect dataset licensing](https://www.quantconnect.com/docs/v2/cloud-platform/datasets/licensing)

## 9. Security and repository boundaries

- Never commit `.lean/credentials`, `lean.json` containing local configuration,
  downloaded licensed datasets, API tokens, or copied vendor rows.
- Keep `C:\QuantConnect\ACER` outside this repository.
- Do not upload reconstructable licensed data without verified permission.
- Installation and sample-data validation do not authorize a real research
  look, production backtest, broker connection, deployment, or trade.
- Record only credential-presence booleans and non-sensitive paths/versions in
  repository documentation.
