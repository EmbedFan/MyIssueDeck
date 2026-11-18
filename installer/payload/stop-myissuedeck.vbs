' Stops the MyIssueDesk server started from this folder and reports the result.
Option Explicit
Dim shell, folder, code
Set shell = CreateObject("WScript.Shell")
folder = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
code = shell.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & folder & "stop-server.ps1""", 0, True)
If code = 0 Then
  MsgBox "MyIssueDesk server stopped.", vbInformation, "MyIssueDesk"
ElseIf code = 4 Then
  MsgBox "No MyIssueDesk server from this folder was running.", vbInformation, "MyIssueDesk"
Else
  MsgBox "The server could not be stopped. See logs\start.log.", vbCritical, "MyIssueDesk"
End If
