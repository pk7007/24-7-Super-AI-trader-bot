' Hidden launcher for the Windows scheduled tasks IndiaCryptoBot-paper / IndiaCryptoBot-shadow.
' Usage: wscript.exe start_bot_hidden.vbs paper|shadow
' Starts run_bot.cmd with no console window, unless that bot is already running (then exits quietly).
' The bot's own lock (state\<mode>\bot.lock) is the real guard against two bots; this check only keeps
' the 10-minute re-check from writing "refusing to start" lines into the logs.
Option Explicit
Dim mode, wmi, procs, shell, root
If WScript.Arguments.Count <> 1 Then WScript.Quit 2
mode = LCase(WScript.Arguments(0))
If mode <> "paper" And mode <> "shadow" Then WScript.Quit 2   ' live is never started from here

Set wmi = GetObject("winmgmts:\\.\root\cimv2")
Set procs = wmi.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE CommandLine LIKE '%bot.main " & mode & "%' AND Name LIKE 'python%'")
If procs.Count > 0 Then WScript.Quit 0

root = "C:\tb\india-crypto-ai-bot"
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = root
shell.Run "cmd.exe /c """ & root & "\run_bot.cmd"" " & mode, 0, False
WScript.Quit 0
