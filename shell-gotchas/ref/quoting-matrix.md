# Quoting matrix: pwsh7 → pwsh7 / pwsh5 / cmd / python / bash / dotnet

Scope: variable-value transmission across runtime boundary only, not keystroke parsing. Payload lives in a PowerShell variable (single-quote literal), passed as arg to a helper, helper echoes back `[arg]`. Cell `ok` = byte-identical return.

Runtimes: `pwsh` 7.6.5 (child), `powershell` 5.1, `cmd`, `python`, `C:/Program Files/Git/bin/bash.exe`, `dotnet` 11 (`echoarg.dll`, built once from C# below).

Helpers (exact sources): `echo-arg.ps1` `param([string]$a)` → `'[' + $a + ']'`. `echo-arg.bat` `@echo off` / `echo [%1]` (raw `%1`, no tilde-strip). `echo-arg.py` `import sys` / `print('[' + sys.argv[1] + ']')`. `echo-arg.sh` `printf '[%s]' "$1"`. C# (`echoarg.csproj` net11.0 + `Program.cs`) `System.Console.Write("[" + args[0] + "]");`, run as `dotnet echoarg.dll <payload>`.

Probe: for each payload × runtime, run helper with payload, compare stdout case-sensitive against `[payload]`.

## Results

| payload                 | ps7 | ps5 | cmd                                                                                               | py | bash         | dotnet |
| ----------------------- | --- | --- | ------------------------------------------------------------------------------------------------- | -- | ------------ | ------ |
| `plain`                 | ok  | ok  | ok                                                                                                | ok | ok           | ok     |
| `it's`                  | ok  | ok  | ok                                                                                                | ok | DIFF `[its]` | ok     |
| `say "hi"`              | ok  | ok  | DIFF `["say "hi""]`                                                                               | ok | ok           | ok     |
| `C:\Users\x`            | ok  | ok  | ok                                                                                                | ok | ok           | ok     |
| `C:\\Users\\x`          | ok  | ok  | ok                                                                                                | ok | ok           | ok     |
| `C:/Users/x`            | ok  | ok  | ok                                                                                                | ok | ok           | ok     |
| `"C:\path with spaces"` | ok  | ok  | ok                                                                                                | ok | ok           | ok     |
| `a?b=c`                 | ok  | ok  | DIFF `[a?b]`                                                                                      | ok | ok           | ok     |
| `$HOME`                 | ok  | ok  | ok                                                                                                | ok | ok           | ok     |
| `a,b;c\|d&e`            | ok  | ok  | DIFF `'C:' is not recognized as an internal or external command, operable program or batch file.` | ok | ok           | ok     |
| `100%`                  | ok  | ok  | ok                                                                                                | ok | ok           | ok     |
| `trailing\`             | ok  | ok  | ok                                                                                                | ok | ok           | ok     |

## Findings

- ps5 blocks script by default (`UnauthorizedAccess`); probe needs `-ExecutionPolicy Bypass`.
- bash eats single quote (`it's` → `[its]`); all other payloads survive bash fine.
- cmd keeps inner double quote and adds outer ones too (`["say "hi""]`).
- cmd treats `=` as arg splitter (`a?b=c` → `[a?b]`).
- cmd metachars `;||&` split/pipe even with caller quoting (`/c` strips quote) — payload runs as a command, bad.
