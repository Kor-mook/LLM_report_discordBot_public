Option Explicit

Dim shell, fileSystem, scriptDir, pythonExe, trayScript, command
Dim logsDir, trayPidPath, botPidPath, trayRunning, botRunning, message, iconType
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")
scriptDir = fileSystem.GetParentFolderName(WScript.ScriptFullName)
logsDir = scriptDir & "\logs"
trayPidPath = logsDir & "\llm_report_tray.pid"
botPidPath = logsDir & "\llm_report_bot.pid"

If fileSystem.FileExists(scriptDir & "\.venv\Scripts\pythonw.exe") Then
    pythonExe = scriptDir & "\.venv\Scripts\pythonw.exe"
Else
    pythonExe = "pythonw.exe"
End If

trayScript = scriptDir & "\llm_report_tray.py"
command = """" & pythonExe & """ -B """ & trayScript & """"
shell.CurrentDirectory = scriptDir
shell.Run command, 0, False

WScript.Sleep 2500

trayRunning = IsPidForScript(ReadPid(trayPidPath), "llm_report_tray.py")
botRunning = IsPidForScript(ReadPid(botPidPath), "llm_report_bot.py")

If trayRunning And botRunning Then
    message = "LLM_report_bot is running." & vbCrLf & _
        "Tray icon: AI" & vbCrLf & _
        "Use the tray menu to open logs or stop the bot."
    iconType = 64
ElseIf botRunning Then
    message = "The Discord bot is running, but the tray icon was not confirmed." & vbCrLf & _
        "Run run_llm_report_tray_debug.bat to inspect the tray manager."
    iconType = 48
Else
    message = "LLM_report_bot did not start." & vbCrLf & _
        "Run run_llm_report_tray_debug.bat and check logs\llm_report_bot.log."
    iconType = 16
End If

shell.Popup message, 5, "LLM_report_bot", iconType

Function ReadPid(path)
    Dim handle, value
    ReadPid = ""
    If Not fileSystem.FileExists(path) Then
        Exit Function
    End If

    On Error Resume Next
    Set handle = fileSystem.OpenTextFile(path, 1, False)
    If Err.Number <> 0 Then
        Err.Clear
        Exit Function
    End If

    value = Trim(handle.ReadLine)
    handle.Close
    If IsNumeric(value) Then
        ReadPid = value
    End If
    On Error GoTo 0
End Function

Function IsPidForScript(pid, scriptName)
    Dim wmi, processes, process, query, commandLine
    IsPidForScript = False
    If Len(pid) = 0 Then
        Exit Function
    End If

    On Error Resume Next
    Set wmi = GetObject("winmgmts:\\.\root\cimv2")
    If Err.Number <> 0 Then
        Err.Clear
        Exit Function
    End If

    query = "SELECT CommandLine FROM Win32_Process WHERE ProcessId = " & CLng(pid)
    Set processes = wmi.ExecQuery(query)
    If Err.Number <> 0 Then
        Err.Clear
        Exit Function
    End If

    For Each process In processes
        commandLine = ""
        If Not IsNull(process.CommandLine) Then
            commandLine = process.CommandLine
        End If
        If InStr(1, LCase(commandLine), LCase(scriptName), vbTextCompare) > 0 Then
            IsPidForScript = True
            Exit Function
        End If
    Next
    On Error GoTo 0
End Function
