' Starts the MyIssueDesk server in the background and reports the result.
Option Explicit
Dim shell, folder, code
Set shell = CreateObject("WScript.Shell")
folder = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
code = shell.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & folder & "start-server.ps1""", 0, True)
If code = 0 Then
  MsgBox "MyIssueDesk server started." & vbCrLf & "Open the dashboard in your browser.", vbInformation, "MyIssueDesk"
ElseIf code = 2 Then
  MsgBox "The port is already in use, so the server was not started." & vbCrLf & "Stop the other server first. See logs\start.log.", vbExclamation, "MyIssueDesk"
Else
  MsgBox "The server did not start." & vbCrLf & "See logs\server.err.log and logs\start.log.", vbCritical, "MyIssueDesk"
End If
