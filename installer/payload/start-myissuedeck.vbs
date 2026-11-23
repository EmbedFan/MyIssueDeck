' Starts the MyIssueDeck server in the background and reports the result.
Option Explicit
Dim shell, folder, code
Set shell = CreateObject("WScript.Shell")
folder = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
code = shell.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & folder & "start-server.ps1""", 0, True)
If code = 0 Then
  MsgBox "MyIssueDeck server started." & vbCrLf & "Open the dashboard in your browser.", vbInformation, "MyIssueDeck"
ElseIf code = 2 Then
  MsgBox "The port is already in use, so the server was not started." & vbCrLf & "Stop the other server first. See logs\start.log.", vbExclamation, "MyIssueDeck"
Else
  MsgBox "The server did not start." & vbCrLf & "See logs\server.err.log and logs\start.log.", vbCritical, "MyIssueDeck"
End If
